"""Coach TTS route and runtime contract tests."""

import asyncio
import base64
import gc
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.user import User
from app.services.ai import tts_runtime
from app.services.ai.tts_service import QwenTTSAPIError, SynthesizedSpeech
from app.services.user.api_key_service import ApiKeyService

TEST_USER_QWEN_KEY = "sk-test-user-qwen-123456"


def make_pcm_wav(frames: bytes = b"\x00\x00" * 8) -> bytes:
    """Build a tiny mono PCM WAV used as a synthesis fixture."""
    import wave
    from io import BytesIO

    buffer = BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(24000)
        wav_file.writeframes(frames)
    return buffer.getvalue()


@pytest_asyncio.fixture
async def session_factory(tmp_path: Path):
    """Create an isolated SQLite database for coach TTS route tests."""
    db_path = tmp_path / "coach-tts.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded_user(session_factory):
    """Seed one normal user with a user-owned Qwen key for TTS calls."""
    async with session_factory() as session:
        user = User(openid="tts-user-1", nickname="TTS User", is_admin=False)
        session.add(user)
        await session.flush()
        await ApiKeyService(session).save_key(user.id, "qwen", TEST_USER_QWEN_KEY)
        await session.commit()
        await session.refresh(user)
        return user


@pytest_asyncio.fixture
async def client(session_factory):
    """Create an app client backed by the isolated test database."""

    async def override_get_db():
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


def _auth_headers(user_id: int) -> dict[str, str]:
    """Build bearer auth headers for a specific user id."""
    token = jwt.encode({"sub": str(user_id)}, settings.SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def test_tts_is_configured_requires_voice_and_key(monkeypatch):
    """TTS is available only when both voice id and an API key are present."""
    monkeypatch.setattr(settings, "QWEN_AUDIO_TTS_VOICE", "")
    monkeypatch.setattr(settings, "QWEN_AUDIO_API_KEY", "")
    monkeypatch.setattr(settings, "QWEN_API_KEY", "")
    assert tts_runtime.tts_is_configured() is False

    monkeypatch.setattr(settings, "QWEN_AUDIO_TTS_VOICE", "voice-abc")
    monkeypatch.setattr(settings, "QWEN_AUDIO_API_KEY", "")
    monkeypatch.setattr(settings, "QWEN_API_KEY", "fallback-key")
    assert tts_runtime.tts_is_configured() is True

    monkeypatch.setattr(settings, "QWEN_AUDIO_API_KEY", "audio-key")
    assert tts_runtime.tts_is_configured() is True


@pytest.mark.asyncio
async def test_synthesize_speech_uses_configured_voice_and_caches(monkeypatch):
    """Runtime synthesis should hit Qwen once and reuse cached WAV for same text."""
    monkeypatch.setattr(settings, "QWEN_AUDIO_TTS_VOICE", "voice-abc")
    monkeypatch.setattr(settings, "QWEN_AUDIO_API_KEY", "audio-key")
    monkeypatch.setattr(settings, "QWEN_AUDIO_API_BASE", "https://example.test/api/v1")
    monkeypatch.setattr(settings, "QWEN_AUDIO_TTS_MODEL", "qwen3-tts-vd-2026-01-26")

    wav = make_pcm_wav()
    synthesize = AsyncMock(return_value=SynthesizedSpeech(audio=wav, request_id="req-1"))
    fake_client = type("FakeClient", (), {"synthesize": synthesize})()

    monkeypatch.setattr(tts_runtime, "_build_client", lambda http_client: fake_client)
    tts_runtime.clear_tts_cache()

    first = await tts_runtime.synthesize_speech("Hello coach")
    second = await tts_runtime.synthesize_speech("Hello coach")

    assert first == wav
    assert second == wav
    synthesize.assert_awaited_once_with(text="Hello coach", voice_id="voice-abc")


@pytest.mark.asyncio
async def test_synthesize_animated_speech_caches_energy_fallback(monkeypatch):
    """Alignment failure should preserve audio and cache the fallback response."""
    wav = make_pcm_wav(b"\x00\x00" * 2400)
    monkeypatch.setattr(settings, "QWEN_AUDIO_TTS_VOICE", "voice-abc")
    monkeypatch.setattr(tts_runtime, "tts_is_configured", lambda *args, **kwargs: True)
    monkeypatch.setattr(tts_runtime, "lip_sync_is_configured", lambda: True)
    synthesize = AsyncMock(return_value=wav)
    alignment_error = getattr(tts_runtime, "LipSyncError", RuntimeError)
    align = AsyncMock(side_effect=alignment_error("malformed timeline"))
    monkeypatch.setattr(tts_runtime, "synthesize_speech", synthesize)
    monkeypatch.setattr(tts_runtime, "align_wav", align, raising=False)
    tts_runtime.clear_tts_cache()

    first = await tts_runtime.synthesize_animated_speech("Again!")
    second = await tts_runtime.synthesize_animated_speech("Again!")

    assert first == second
    assert first.audio == wav
    assert first.alignment == "energy"
    assert first.mouth_cues == ()
    synthesize.assert_awaited_once_with("Again!")
    align.assert_awaited_once()


@pytest.mark.asyncio
async def test_synthesize_animated_speech_coalesces_concurrent_requests(monkeypatch):
    """Share one Qwen synthesis and Rhubarb analysis for an identical in-flight key."""
    wav = make_pcm_wav(b"\x00\x00" * 2400)
    synthesis_started = asyncio.Event()
    synthesis_release = asyncio.Event()
    alignment_started = asyncio.Event()
    alignment_release = asyncio.Event()

    async def synthesize_once(*, text: str, voice_id: str):
        """Hold Qwen open so a second request can join the same work."""
        synthesis_started.set()
        await synthesis_release.wait()
        return SynthesizedSpeech(audio=wav, request_id=f"{voice_id}:{text}")

    async def align_once(audio: bytes, text: str, **kwargs):
        """Hold Rhubarb open so concurrent analysis is observable."""
        alignment_started.set()
        await alignment_release.wait()
        return SimpleNamespace(duration_seconds=0.1, mouth_cues=())

    synthesize = AsyncMock(side_effect=synthesize_once)
    align = AsyncMock(side_effect=align_once)
    fake_client = type("FakeClient", (), {"synthesize": synthesize})()
    monkeypatch.setattr(settings, "QWEN_AUDIO_TTS_VOICE", "voice-abc")
    monkeypatch.setattr(settings, "QWEN_AUDIO_API_KEY", "audio-key")
    monkeypatch.setattr(tts_runtime, "_build_client", lambda http_client: fake_client)
    monkeypatch.setattr(tts_runtime, "lip_sync_is_configured", lambda: True)
    monkeypatch.setattr(tts_runtime, "align_wav", align)
    tts_runtime.clear_tts_cache()

    first = asyncio.create_task(tts_runtime.synthesize_animated_speech("Again!"))
    second = asyncio.create_task(tts_runtime.synthesize_animated_speech("Again!"))
    await synthesis_started.wait()
    await asyncio.sleep(0)
    synthesis_release.set()
    await alignment_started.wait()
    alignment_release.set()
    results = await asyncio.gather(first, second)

    assert results[0] == results[1]
    synthesize.assert_awaited_once_with(text="Again!", voice_id="voice-abc")
    align.assert_awaited_once()


@pytest.mark.asyncio
async def test_single_flight_observes_failure_after_all_waiters_cancel():
    """Consume a shared producer failure even after every shielded waiter leaves."""
    registry: dict[str, asyncio.Task[bytes]] = {}
    release = asyncio.Event()
    finished = asyncio.Event()
    loop = asyncio.get_running_loop()
    previous_handler = loop.get_exception_handler()
    reported: list[dict[str, object]] = []

    async def fail_after_release() -> bytes:
        """Fail only after the sole waiter has cancelled its shielded await."""
        try:
            await release.wait()
            raise RuntimeError("orphaned producer")
        finally:
            finished.set()

    loop.set_exception_handler(lambda _loop, context: reported.append(context))
    try:
        waiter = asyncio.create_task(
            tts_runtime._run_single_flight("same-key", registry, fail_after_release)
        )
        await asyncio.sleep(0)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter

        release.set()
        await finished.wait()
        await asyncio.sleep(0)
        gc.collect()
        await asyncio.sleep(0)

        assert registry == {}
        assert reported == []
    finally:
        loop.set_exception_handler(previous_handler)


@pytest.mark.asyncio
async def test_tts_status_reports_availability(client: AsyncClient, seeded_user, monkeypatch):
    """Status endpoint should reflect runtime configuration for authenticated users."""
    monkeypatch.setattr(tts_runtime, "tts_is_configured", lambda *args, **kwargs: True)
    monkeypatch.setattr(tts_runtime, "lip_sync_is_configured", lambda: True, raising=False)
    ok = await client.get("/api/coach/tts/status", headers=_auth_headers(seeded_user.id))
    assert ok.status_code == 200
    assert ok.json() == {"available": True, "lip_sync_available": True}

    monkeypatch.setattr(tts_runtime, "tts_is_configured", lambda *args, **kwargs: False)
    monkeypatch.setattr(tts_runtime, "lip_sync_is_configured", lambda: False, raising=False)
    disabled = await client.get("/api/coach/tts/status", headers=_auth_headers(seeded_user.id))
    assert disabled.status_code == 200
    assert disabled.json() == {"available": False, "lip_sync_available": False}


@pytest.mark.asyncio
async def test_tts_status_requires_auth(client: AsyncClient):
    """Status endpoint should reject anonymous callers."""
    response = await client.get("/api/coach/tts/status")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_tts_synthesize_returns_wav_bytes(client: AsyncClient, seeded_user, monkeypatch):
    """POST /tts should return audio/wav bytes from the runtime synthesizer."""
    wav = make_pcm_wav()
    monkeypatch.setattr(tts_runtime, "tts_is_configured", lambda *args, **kwargs: True)
    monkeypatch.setattr(tts_runtime, "synthesize_speech", AsyncMock(return_value=wav))

    response = await client.post(
        "/api/coach/tts",
        headers=_auth_headers(seeded_user.id),
        json={"text": "Keep your core tight, bro."},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.content == wav


@pytest.mark.asyncio
async def test_tts_animated_returns_audio_and_mouth_cues(
    client: AsyncClient, seeded_user, monkeypatch
):
    """Animated TTS should return one synchronized JSON payload."""
    wav = make_pcm_wav()
    speech = SimpleNamespace(
        audio=wav,
        duration_seconds=0.1,
        mouth_cues=(
            SimpleNamespace(start=0.0, end=0.05, value="X"),
            SimpleNamespace(start=0.05, end=0.08, value="D"),
            SimpleNamespace(start=0.08, end=0.1, value="X"),
        ),
        alignment="rhubarb",
    )
    synthesize = AsyncMock(return_value=speech)
    monkeypatch.setattr(tts_runtime, "tts_is_configured", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        tts_runtime,
        "synthesize_animated_speech",
        synthesize,
        raising=False,
    )

    response = await client.post(
        "/api/coach/tts/animated",
        headers=_auth_headers(seeded_user.id),
        json={"text": "再来两个！"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert base64.b64decode(payload["audio_base64"]) == wav
    assert payload["mime_type"] == "audio/wav"
    assert payload["duration_seconds"] == 0.1
    assert payload["alignment"] == "rhubarb"
    assert [cue["value"] for cue in payload["mouth_cues"]] == ["X", "D", "X"]
    synthesize.assert_awaited_once_with(
        "再来两个！",
        api_key=TEST_USER_QWEN_KEY,
        voice_id="Ryan",
    )


@pytest.mark.asyncio
async def test_tts_animated_requires_auth(client: AsyncClient):
    """Animated speech data should remain private to authenticated users."""
    response = await client.post("/api/coach/tts/animated", json={"text": "Let's go."})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_tts_animated_rejects_whitespace_text(
    client: AsyncClient, seeded_user, monkeypatch
):
    """Reject text that becomes empty after trimming before starting synthesis."""
    synthesize = AsyncMock()
    monkeypatch.setattr(tts_runtime, "tts_is_configured", lambda *args, **kwargs: True)
    monkeypatch.setattr(tts_runtime, "synthesize_animated_speech", synthesize)

    response = await client.post(
        "/api/coach/tts/animated",
        headers=_auth_headers(seeded_user.id),
        json={"text": "   \n\t"},
    )

    assert response.status_code == 400
    synthesize.assert_not_awaited()


@pytest.mark.asyncio
async def test_tts_synthesize_rejects_empty_text(client: AsyncClient, seeded_user, monkeypatch):
    """Empty synthesis text should fail validation with 422."""
    monkeypatch.setattr(tts_runtime, "tts_is_configured", lambda *args, **kwargs: True)
    response = await client.post(
        "/api/coach/tts",
        headers=_auth_headers(seeded_user.id),
        json={"text": ""},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_tts_synthesize_returns_503_when_unconfigured(
    client: AsyncClient, seeded_user, monkeypatch
):
    """Unconfigured voice/key should surface as 503 instead of calling Qwen."""
    monkeypatch.setattr(tts_runtime, "tts_is_configured", lambda *args, **kwargs: False)
    response = await client.post(
        "/api/coach/tts",
        headers=_auth_headers(seeded_user.id),
        json={"text": "Let's go."},
    )
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_tts_synthesize_returns_502_on_provider_failure(
    client: AsyncClient, seeded_user, monkeypatch
):
    """Provider failures should map to 502 without leaking secrets."""
    monkeypatch.setattr(tts_runtime, "tts_is_configured", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        tts_runtime,
        "synthesize_speech",
        AsyncMock(side_effect=QwenTTSAPIError("upstream failed")),
    )

    response = await client.post(
        "/api/coach/tts",
        headers=_auth_headers(seeded_user.id),
        json={"text": "One more set."},
    )

    assert response.status_code == 502
    assert "audio-key" not in response.text
    assert "api_key" not in response.text.lower()
