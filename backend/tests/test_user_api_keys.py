"""Mandatory user-owned provider key policy and encryption tests."""

import base64
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from httpx import ASGITransport, AsyncClient
from jose import jwt
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import coach as coach_api
from app.api import plan as plan_api
from app.api import vision as vision_api
from app.core.config import Settings, settings
from app.core.database import Base, get_db
from app.main import app
from app.models.user import User
from app.schemas.user import ApiKeyConfigRequest
from app.services.ai import tts_runtime
from app.services.ai.llm_factory import LLMClientFactory
from app.services.user.api_key_service import ApiKeyService


def encrypt_legacy_cbc(plaintext: str, secret: str) -> str:
    """Build the pre-GCM ciphertext format for migration compatibility tests."""
    aes_key = secret.encode("utf-8")[:32].ljust(32, b"\x00")
    cipher = AES.new(aes_key, AES.MODE_CBC)
    ciphertext = cipher.encrypt(pad(plaintext.encode("utf-8"), AES.block_size))
    return ":".join(
        (
            base64.b64encode(cipher.iv).decode(),
            base64.b64encode(ciphertext).decode(),
        )
    )


@pytest_asyncio.fixture
async def session_factory(tmp_path: Path):
    """Create an isolated user database for provider-key policy tests."""
    db_path = tmp_path / "user-api-keys.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def keyless_user(session_factory):
    """Seed a normal account without a provider API key."""
    async with session_factory() as session:
        user = User(openid="byok-user", email="byok@example.com", nickname="BYOK User")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest_asyncio.fixture
async def client(session_factory):
    """Create an app client backed by the isolated BYOK test database."""

    async def override_get_db():
        """Commit each request or roll it back when the route raises."""
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as async_client:
        yield async_client
    app.dependency_overrides.clear()


def auth_headers(user_id: int) -> dict[str, str]:
    """Build bearer headers for one isolated test user."""
    token = jwt.encode({"sub": str(user_id)}, settings.SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


async def configure_user_key(session_factory, user_id: int, provider: str, api_key: str) -> None:
    """Persist one encrypted provider key for a route-level test user."""
    async with session_factory() as session:
        await ApiKeyService(session).save_key(user_id, provider, api_key)
        await session.commit()


@pytest.mark.asyncio
async def test_registration_does_not_issue_a_provider_key(client, session_factory):
    """A new account starts keyless and must obtain credentials from a provider."""
    response = await client.post(
        "/api/user/register",
        json={
            "email": "new-byok-user@example.com",
            "password": "secure-password",
            "nickname": "New BYOK User",
        },
    )
    assert response.status_code == 200
    login = response.json()

    profile_response = await client.get(
        "/api/user/me",
        headers={"Authorization": f"Bearer {login['token']}"},
    )
    assert profile_response.status_code == 200
    assert profile_response.json()["api_key_status"] == {
        "has_key": False,
        "provider": None,
        "masked_key": None,
    }

    async with session_factory() as session:
        user = await session.get(User, login["user_id"])
        assert user is not None
        assert user.llm_provider is None
        assert user.llm_api_key is None


def test_api_key_request_rejects_unknown_provider():
    """Only providers supported by the LLM factory may be persisted."""
    with pytest.raises(ValidationError):
        ApiKeyConfigRequest(provider="other", api_key="provider-secret-key")


def test_api_key_request_rejects_whitespace_only_secret():
    """Whitespace must be stripped before enforcing the minimum key length."""
    with pytest.raises(ValidationError):
        ApiKeyConfigRequest(provider="qwen", api_key="          ")


@pytest.mark.parametrize(
    "weak_secret",
    ("", "short-key", "default-32-byte-secret-key!!!!!!"),
)
def test_non_development_startup_rejects_weak_aes_keys(weak_secret: str):
    """Non-development processes must not start with public or weak key encryption."""
    with pytest.raises(ValidationError, match="AES_SECRET_KEY"):
        Settings(_env_file=None, APP_ENV="production", AES_SECRET_KEY=weak_secret)


def test_non_development_startup_accepts_a_unique_32_byte_aes_key():
    """A sufficiently long deployment-specific encryption secret remains valid."""
    configured = Settings(
        _env_file=None,
        APP_ENV="production",
        AES_SECRET_KEY="unique-deployment-secret-32-bytes!",
    )

    assert configured.APP_ENV == "production"


def test_api_key_ciphertext_uses_authenticated_versioned_encryption():
    """New provider secrets must use a versioned authenticated ciphertext envelope."""
    service = ApiKeyService(AsyncMock())

    ciphertext = service._encrypt("sk-user-owned-123456")

    assert ciphertext.startswith("v1:gcm:")
    assert service._decrypt(ciphertext) == "sk-user-owned-123456"


def test_api_key_ciphertext_rejects_tampering():
    """Authenticated decryption must reject a modified provider secret."""
    service = ApiKeyService(AsyncMock())
    ciphertext = service._encrypt("sk-user-owned-123456")
    parts = ciphertext.split(":")
    encrypted = bytearray(base64.b64decode(parts[-1]))
    encrypted[-1] ^= 1
    parts[-1] = base64.b64encode(encrypted).decode()

    with pytest.raises(ValueError):
        service._decrypt(":".join(parts))


def test_api_key_ciphertext_reads_legacy_cbc_rows():
    """Existing CBC rows remain readable while all new writes use AES-GCM."""
    service = ApiKeyService(AsyncMock())
    ciphertext = encrypt_legacy_cbc("sk-legacy-user-123456", settings.AES_SECRET_KEY)

    assert service._decrypt(ciphertext) == "sk-legacy-user-123456"


@pytest.mark.asyncio
async def test_user_key_is_trimmed_encrypted_and_only_returned_masked(
    session_factory,
    keyless_user,
):
    """Normalize the secret before encrypted storage and never expose it in status."""
    async with session_factory() as session:
        service = ApiKeyService(session)
        status = await service.save_key(
            keyless_user.id,
            "qwen",
            "  sk-user-owned-123456  ",
        )
        decrypted = await service.get_decrypted_key(keyless_user.id)
        stored_user = await session.get(User, keyless_user.id)

    assert decrypted == ("qwen", "sk-user-owned-123456")
    assert stored_user is not None
    assert stored_user.llm_api_key != "sk-user-owned-123456"
    assert status.masked_key == "sk-...****3456"
    assert "sk-user-owned" not in status.model_dump_json()


@pytest.mark.parametrize("stored_provider", (None, "QWEN", "legacy-provider"))
@pytest.mark.asyncio
async def test_invalid_stored_provider_never_unlocks_ai_features(
    session_factory,
    keyless_user,
    stored_provider,
):
    """Legacy or corrupt provider values must fail the BYOK gate instead of becoming OpenAI."""
    async with session_factory() as session:
        service = ApiKeyService(session)
        user = await session.get(User, keyless_user.id)
        assert user is not None
        user.llm_provider = stored_provider
        user.llm_api_key = service._encrypt("sk-corrupt-provider-123456")
        await session.flush()

        decrypted = await service.get_decrypted_key(keyless_user.id)
        status = await service.get_status(keyless_user.id)

    assert decrypted is None
    assert status.has_key is False
    assert status.provider is None


@pytest.mark.asyncio
async def test_empty_decrypted_secret_never_unlocks_ai_features(
    session_factory,
    keyless_user,
):
    """A decryptable but empty secret must be treated as missing configuration."""
    async with session_factory() as session:
        service = ApiKeyService(session)
        user = await session.get(User, keyless_user.id)
        assert user is not None
        user.llm_provider = "qwen"
        user.llm_api_key = service._encrypt("   ")
        await session.flush()

        decrypted = await service.get_decrypted_key(keyless_user.id)
        status = await service.get_status(keyless_user.id)

    assert decrypted is None
    assert status.has_key is False


def test_llm_factory_rejects_unknown_provider_instead_of_assuming_openai():
    """The final client factory boundary accepts only explicitly supported providers."""
    factory = LLMClientFactory()

    with pytest.raises(ValueError, match="提供商"):
        factory._build_client("legacy-provider", "sk-user-owned-123456", "chat", False)


@pytest.mark.asyncio
async def test_authenticated_user_without_key_never_falls_back_to_system_key(
    session_factory,
    keyless_user,
    monkeypatch,
):
    """A user-scoped LLM request must fail closed when BYOK setup is incomplete."""
    monkeypatch.setattr(settings, "DEFAULT_LLM_PROVIDER", "qwen")
    monkeypatch.setattr(settings, "QWEN_API_KEY", "system-provider-key")

    async with session_factory() as session:
        factory = LLMClientFactory(session)
        with pytest.raises(ValueError, match="API Key"):
            await factory._resolve_key(keyless_user.id)


@pytest.mark.asyncio
async def test_internal_request_without_user_identity_can_use_system_key(monkeypatch):
    """Explicit internal jobs without a user identity retain server-key support."""
    monkeypatch.setattr(settings, "DEFAULT_LLM_PROVIDER", "qwen")
    monkeypatch.setattr(settings, "QWEN_API_KEY", "system-provider-key")

    provider, api_key = await LLMClientFactory()._resolve_key(None)

    assert (provider, api_key) == ("qwen", "system-provider-key")


@pytest.mark.asyncio
async def test_internal_request_without_system_key_raises_useful_error(monkeypatch):
    """Internal jobs must fail loudly when no server-managed credentials exist."""
    monkeypatch.setattr(settings, "DEFAULT_LLM_PROVIDER", "qwen")
    monkeypatch.setattr(settings, "QWEN_API_KEY", "")

    with pytest.raises(ValueError, match="系统 LLM 凭据"):
        await LLMClientFactory()._resolve_key(None)


@pytest.mark.asyncio
async def test_llm_factory_falls_back_to_system_key_when_enabled(
    session_factory,
    keyless_user,
    monkeypatch,
):
    """With the opt-in flag, a keyless user may use server-managed credentials."""
    monkeypatch.setattr(settings, "ALLOW_SYSTEM_LLM_FALLBACK", True)
    monkeypatch.setattr(settings, "DEFAULT_LLM_PROVIDER", "qwen")
    monkeypatch.setattr(settings, "QWEN_API_KEY", "system-provider-key")

    async with session_factory() as session:
        factory = LLMClientFactory(session)
        provider, api_key = await factory._resolve_key(keyless_user.id)

    assert (provider, api_key) == ("qwen", "system-provider-key")


@pytest.mark.asyncio
async def test_llm_factory_personal_key_priority_over_system_fallback(
    session_factory,
    keyless_user,
    monkeypatch,
):
    """A personal key always wins over server-managed fallback credentials."""
    await configure_user_key(
        session_factory,
        keyless_user.id,
        "openai",
        "sk-user-openai-123456",
    )
    monkeypatch.setattr(settings, "ALLOW_SYSTEM_LLM_FALLBACK", True)
    monkeypatch.setattr(settings, "DEFAULT_LLM_PROVIDER", "qwen")
    monkeypatch.setattr(settings, "QWEN_API_KEY", "system-provider-key")

    async with session_factory() as session:
        provider, api_key = await LLMClientFactory(session)._resolve_key(keyless_user.id)

    assert (provider, api_key) == ("openai", "sk-user-openai-123456")


@pytest.mark.asyncio
async def test_llm_factory_fallback_still_fails_closed_without_system_key(
    session_factory,
    keyless_user,
    monkeypatch,
):
    """The flag alone never unlocks a keyless user without usable system credentials."""
    monkeypatch.setattr(settings, "ALLOW_SYSTEM_LLM_FALLBACK", True)
    monkeypatch.setattr(settings, "DEFAULT_LLM_PROVIDER", "qwen")
    monkeypatch.setattr(settings, "QWEN_API_KEY", "")

    async with session_factory() as session:
        factory = LLMClientFactory(session)
        with pytest.raises(ValueError, match="API Key"):
            await factory._resolve_key(keyless_user.id)


@pytest.mark.asyncio
async def test_ai_generation_routes_require_a_user_owned_key(
    client,
    keyless_user,
    monkeypatch,
):
    """Reject every provider-consuming route before downstream AI work starts."""
    coach_chat = AsyncMock(
        return_value={"reply": "ok", "coach_state": "guide", "suggested_actions": []}
    )
    monkeypatch.setattr(
        coach_api,
        "CoachGraph",
        lambda user_id, db: SimpleNamespace(chat=coach_chat),
    )

    generated_plan = SimpleNamespace(
        id=1,
        user_id=keyless_user.id,
        week_start="2026-08-03",
        weekly_plan=[],
        difficulty_factor=1.0,
        status="active",
    )
    monkeypatch.setattr(
        plan_api.PlanService,
        "generate_plan",
        AsyncMock(return_value=generated_plan),
    )

    run_analysis = AsyncMock()
    monkeypatch.setattr(vision_api, "_run_analysis", run_analysis)

    requests = (
        ("/api/coach/chat", {"user_id": keyless_user.id, "message": "hello"}),
        ("/api/vision/analyze", {"user_id": keyless_user.id, "image_base64": "aW1hZ2U="}),
        ("/api/plan/generate", {"user_id": keyless_user.id}),
    )
    for path, payload in requests:
        response = await client.post(path, json=payload, headers=auth_headers(keyless_user.id))
        assert response.status_code == 428, (path, response.text)
        assert response.json()["detail"] == {
            "code": "api_key_required",
            "message": "使用 AI 功能前，请先在个人资料中配置你自己的 API Key",
        }

    coach_chat.assert_not_awaited()
    run_analysis.assert_not_awaited()


@pytest.mark.asyncio
async def test_keyless_user_passes_ai_route_with_fallback_enabled(
    client,
    keyless_user,
    monkeypatch,
):
    """The AI gate admits a keyless user only when opt-in fallback is usable."""
    monkeypatch.setattr(settings, "ALLOW_SYSTEM_LLM_FALLBACK", True)
    monkeypatch.setattr(settings, "DEFAULT_LLM_PROVIDER", "qwen")
    monkeypatch.setattr(settings, "QWEN_API_KEY", "system-provider-key")

    coach_chat = AsyncMock(
        return_value={"reply": "ok", "coach_state": "guide", "suggested_actions": []}
    )
    monkeypatch.setattr(
        coach_api,
        "CoachGraph",
        lambda user_id, db: SimpleNamespace(chat=coach_chat),
    )

    response = await client.post(
        "/api/coach/chat",
        json={"user_id": keyless_user.id, "message": "hello"},
        headers=auth_headers(keyless_user.id),
    )

    assert response.status_code == 200
    assert response.json()["reply"] == "ok"
    coach_chat.assert_awaited_once()


@pytest.mark.asyncio
async def test_keyless_user_ai_route_still_fails_closed_without_system_key(
    client,
    keyless_user,
    monkeypatch,
):
    """The flag alone never unlocks an AI route when system credentials are absent."""
    monkeypatch.setattr(settings, "ALLOW_SYSTEM_LLM_FALLBACK", True)
    monkeypatch.setattr(settings, "DEFAULT_LLM_PROVIDER", "qwen")
    monkeypatch.setattr(settings, "QWEN_API_KEY", "")

    response = await client.post(
        "/api/coach/chat",
        json={"user_id": keyless_user.id, "message": "hello"},
        headers=auth_headers(keyless_user.id),
    )

    assert response.status_code == 428
    assert response.json()["detail"]["code"] == "api_key_required"


@pytest.mark.asyncio
async def test_user_with_key_can_reach_ai_generation_route(
    client,
    session_factory,
    keyless_user,
    monkeypatch,
):
    """A configured user should pass the BYOK dependency to downstream AI work."""
    await configure_user_key(
        session_factory,
        keyless_user.id,
        "qwen",
        "sk-user-qwen-123456",
    )
    coach_chat = AsyncMock(
        return_value={"reply": "ready", "coach_state": "guide", "suggested_actions": []}
    )
    monkeypatch.setattr(
        coach_api,
        "CoachGraph",
        lambda user_id, db: SimpleNamespace(chat=coach_chat),
    )

    response = await client.post(
        "/api/coach/chat",
        json={"user_id": keyless_user.id, "message": "hello"},
        headers=auth_headers(keyless_user.id),
    )

    assert response.status_code == 200
    assert response.json()["reply"] == "ready"
    coach_chat.assert_awaited_once()


@pytest.mark.asyncio
async def test_keyless_user_cannot_use_coach_voice(
    client,
    keyless_user,
    monkeypatch,
):
    """Coach speech must not consume the server Qwen key for a keyless user."""
    synthesize = AsyncMock(return_value=b"voice")
    monkeypatch.setattr(tts_runtime, "tts_is_configured", lambda *args, **kwargs: True)
    monkeypatch.setattr(tts_runtime, "synthesize_speech", synthesize)

    response = await client.post(
        "/api/coach/tts",
        json={"text": "hello"},
        headers=auth_headers(keyless_user.id),
    )

    assert response.status_code == 428
    assert response.json()["detail"]["code"] == "api_key_required"
    synthesize.assert_not_awaited()


@pytest.mark.asyncio
async def test_qwen_user_key_is_injected_into_coach_voice(
    client,
    session_factory,
    keyless_user,
    monkeypatch,
):
    """Qwen voice synthesis must receive the authenticated user's own key."""
    await configure_user_key(
        session_factory,
        keyless_user.id,
        "qwen",
        "sk-user-qwen-123456",
    )
    synthesize = AsyncMock(return_value=b"voice")
    configured_with: list[tuple[str | None, str | None]] = []

    def is_configured(api_key=None, voice_id=None):
        """Capture the credential used for route availability checks."""
        configured_with.append((api_key, voice_id))
        return api_key == "sk-user-qwen-123456" and voice_id == "Ryan"

    monkeypatch.setattr(tts_runtime, "tts_is_configured", is_configured)
    monkeypatch.setattr(tts_runtime, "synthesize_speech", synthesize)

    response = await client.post(
        "/api/coach/tts",
        json={"text": "hello"},
        headers=auth_headers(keyless_user.id),
    )

    assert response.status_code == 200
    assert configured_with == [("sk-user-qwen-123456", "Ryan")]
    synthesize.assert_awaited_once_with(
        "hello",
        api_key="sk-user-qwen-123456",
        voice_id="Ryan",
    )


@pytest.mark.asyncio
async def test_openai_user_does_not_receive_system_qwen_voice(
    client,
    session_factory,
    keyless_user,
    monkeypatch,
):
    """An OpenAI key cannot authorize the Qwen-only custom coach voice."""
    await configure_user_key(
        session_factory,
        keyless_user.id,
        "openai",
        "sk-user-openai-123456",
    )
    monkeypatch.setattr(settings, "QWEN_AUDIO_TTS_VOICE", "voice-abc")
    monkeypatch.setattr(settings, "QWEN_AUDIO_API_KEY", "system-audio-key")

    response = await client.get(
        "/api/coach/tts/status",
        headers=auth_headers(keyless_user.id),
    )

    assert response.status_code == 200
    assert response.json()["available"] is False


@pytest.mark.asyncio
async def test_keyless_user_tts_falls_back_to_system_qwen_key_when_enabled(
    client,
    keyless_user,
    monkeypatch,
):
    """Coach voice may use the system Qwen key for a keyless user when opted in."""
    monkeypatch.setattr(settings, "ALLOW_SYSTEM_LLM_FALLBACK", True)
    monkeypatch.setattr(settings, "QWEN_AUDIO_API_KEY", "")
    monkeypatch.setattr(settings, "QWEN_API_KEY", "system-qwen-key")

    synthesize = AsyncMock(return_value=b"voice")
    configured_with: list[tuple[str | None, str | None]] = []

    def is_configured(api_key=None, voice_id=None):
        """Capture the credential used for route availability checks."""
        configured_with.append((api_key, voice_id))
        return api_key == "system-qwen-key" and voice_id == "Ryan"

    monkeypatch.setattr(tts_runtime, "tts_is_configured", is_configured)
    monkeypatch.setattr(tts_runtime, "synthesize_speech", synthesize)

    response = await client.post(
        "/api/coach/tts",
        json={"text": "hello"},
        headers=auth_headers(keyless_user.id),
    )

    assert response.status_code == 200
    assert configured_with == [("system-qwen-key", "Ryan")]
    synthesize.assert_awaited_once_with(
        "hello",
        api_key="system-qwen-key",
        voice_id="Ryan",
    )


@pytest.mark.asyncio
async def test_personal_qwen_key_priority_over_system_tts_fallback(
    client,
    session_factory,
    keyless_user,
    monkeypatch,
):
    """A user-owned Qwen key must still win over the system TTS fallback key."""
    await configure_user_key(
        session_factory,
        keyless_user.id,
        "qwen",
        "sk-user-qwen-123456",
    )
    monkeypatch.setattr(settings, "ALLOW_SYSTEM_LLM_FALLBACK", True)
    monkeypatch.setattr(settings, "QWEN_API_KEY", "system-qwen-key")

    synthesize = AsyncMock(return_value=b"voice")
    configured_with: list[tuple[str | None, str | None]] = []

    def is_configured(api_key=None, voice_id=None):
        """Capture the credential used for route availability checks."""
        configured_with.append((api_key, voice_id))
        return api_key == "sk-user-qwen-123456" and voice_id == "Ryan"

    monkeypatch.setattr(tts_runtime, "tts_is_configured", is_configured)
    monkeypatch.setattr(tts_runtime, "synthesize_speech", synthesize)

    response = await client.post(
        "/api/coach/tts",
        json={"text": "hello"},
        headers=auth_headers(keyless_user.id),
    )

    assert response.status_code == 200
    assert configured_with == [("sk-user-qwen-123456", "Ryan")]
    synthesize.assert_awaited_once_with(
        "hello",
        api_key="sk-user-qwen-123456",
        voice_id="Ryan",
    )


@pytest.mark.asyncio
async def test_system_openai_key_never_powers_qwen_tts(
    client,
    keyless_user,
    monkeypatch,
):
    """Even with fallback enabled, a system OpenAI key cannot authorize coach voice."""
    monkeypatch.setattr(settings, "ALLOW_SYSTEM_LLM_FALLBACK", True)
    monkeypatch.setattr(settings, "DEFAULT_LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-system-openai-123456")
    monkeypatch.setattr(settings, "QWEN_AUDIO_API_KEY", "")
    monkeypatch.setattr(settings, "QWEN_API_KEY", "")

    synthesize = AsyncMock(return_value=b"voice")
    monkeypatch.setattr(tts_runtime, "tts_is_configured", lambda *args, **kwargs: True)
    monkeypatch.setattr(tts_runtime, "synthesize_speech", synthesize)

    response = await client.post(
        "/api/coach/tts",
        json={"text": "hello"},
        headers=auth_headers(keyless_user.id),
    )

    assert response.status_code == 409
    assert "通义千问" in response.json()["detail"]
    synthesize.assert_not_awaited()


@pytest.mark.asyncio
async def test_tts_status_reflects_system_fallback_when_enabled(
    client,
    keyless_user,
    monkeypatch,
):
    """TTS status advertises the system Qwen key for a keyless user when opted in."""
    monkeypatch.setattr(settings, "ALLOW_SYSTEM_LLM_FALLBACK", True)
    monkeypatch.setattr(settings, "QWEN_API_KEY", "system-qwen-key")

    monkeypatch.setattr(tts_runtime, "tts_is_configured", lambda *args, **kwargs: True)
    monkeypatch.setattr(tts_runtime, "lip_sync_is_configured", lambda: False)

    response = await client.get(
        "/api/coach/tts/status",
        headers=auth_headers(keyless_user.id),
    )

    assert response.status_code == 200
    assert response.json()["available"] is True


@pytest.mark.asyncio
async def test_tts_status_still_disabled_for_keyless_user_without_fallback(
    client,
    keyless_user,
    monkeypatch,
):
    """Without the opt-in flag, TTS status must stay disabled for a keyless user."""
    monkeypatch.setattr(settings, "QWEN_API_KEY", "system-qwen-key")

    monkeypatch.setattr(tts_runtime, "tts_is_configured", lambda *args, **kwargs: True)
    monkeypatch.setattr(tts_runtime, "lip_sync_is_configured", lambda: False)

    response = await client.get(
        "/api/coach/tts/status",
        headers=auth_headers(keyless_user.id),
    )

    assert response.status_code == 200
    assert response.json()["available"] is False
