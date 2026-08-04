"""Contract tests for Qwen voice design and speech synthesis."""

import base64
import json
import struct
import wave
from io import BytesIO
from types import SimpleNamespace

import httpx
import pytest

from app.core.config import Settings
from app.services.ai.tts_service import (
    DesignedVoice,
    QwenTTSAPIError,
    QwenVoiceDesignClient,
    SynthesizedSpeech,
)
from scripts import create_coach_voice as voice_script
from scripts.create_coach_voice import (
    COACH_VOICE_PROMPT,
    EVALUATION_TEXT,
    PREVIEW_TEXT,
    write_audio_artifacts,
)


def make_pcm_wav(frames: bytes = b"\x00\x00") -> bytes:
    """Build a minimal mono PCM WAV fixture with at least one audio frame."""
    buffer = BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(24000)
        wav_file.writeframes(frames)
    return buffer.getvalue()


def make_qwen_streaming_wav(frames: bytes = b"\x00\x00") -> bytes:
    """Build the sentinel-sized streaming WAV header returned by Qwen TTS."""
    wav_bytes = bytearray(make_pcm_wav(frames))
    data_offset = wav_bytes.index(b"data")
    struct.pack_into("<I", wav_bytes, 4, 0x7FFFFFBF)
    struct.pack_into("<I", wav_bytes, data_offset + 4, 0x7FFFFF9B)
    return bytes(wav_bytes)


@pytest.mark.asyncio
async def test_create_voice_sends_documented_payload_and_decodes_preview():
    """Create a reusable voice and decode its WAV preview from the API response."""
    preview_wav = make_pcm_wav()

    async def handler(request: httpx.Request) -> httpx.Response:
        """Validate the outbound API contract and return a designed voice."""
        assert request.url.path == "/api/v1/services/audio/tts/customization"
        assert request.headers["Authorization"] == "Bearer test-key"
        payload = json.loads(request.content)
        assert payload == {
            "model": "qwen-voice-design",
            "input": {
                "action": "create",
                "target_model": "qwen3-tts-vd-2026-01-26",
                "preferred_name": "lianleme_coach",
                "voice_prompt": "original coach voice",
                "preview_text": "Get your ass up!",
            },
            "parameters": {"sample_rate": 24000, "response_format": "wav"},
        }
        return httpx.Response(
            200,
            json={
                "output": {
                    "voice": "lianleme_coach_123",
                    "preview_audio": {
                        "data": base64.b64encode(preview_wav).decode("ascii")
                    },
                },
                "request_id": "request-123",
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = QwenVoiceDesignClient(
            api_key="test-key",
            api_base="https://example.test/api/v1",
            http_client=http_client,
        )
        result = await client.create_voice(
            voice_prompt="original coach voice",
            preview_text="Get your ass up!",
            preferred_name="lianleme_coach",
        )

    assert result.voice_id == "lianleme_coach_123"
    assert result.preview_audio == preview_wav
    assert result.request_id == "request-123"


@pytest.mark.asyncio
async def test_create_voice_accepts_qwen_streaming_wav_header():
    """Accept Qwen's sentinel chunk lengths when complete PCM frames reach EOF."""
    preview_wav = make_qwen_streaming_wav(b"\x01\x00\x02\x00")

    async def handler(request: httpx.Request) -> httpx.Response:
        """Return the streaming-style WAV observed from the live Qwen endpoint."""
        return httpx.Response(
            200,
            json={
                "output": {
                    "voice": "lianleme_coach_123",
                    "preview_audio": {
                        "data": base64.b64encode(preview_wav).decode("ascii")
                    },
                }
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = QwenVoiceDesignClient(
            api_key="test-key",
            api_base="https://example.test/api/v1",
            http_client=http_client,
        )
        result = await client.create_voice(
            voice_prompt="original coach voice",
            preview_text="Get up!",
        )

    assert result.preview_audio == preview_wav


@pytest.mark.asyncio
async def test_synthesize_downloads_audio_for_the_designed_voice():
    """Synthesize speech with the designed voice and download the audio artifact."""
    synthesized_wav = make_pcm_wav()

    async def handler(request: httpx.Request) -> httpx.Response:
        """Return metadata for generation and bytes for the temporary audio URL."""
        if request.method == "POST":
            assert request.url.path == (
                "/api/v1/services/aigc/multimodal-generation/generation"
            )
            payload = json.loads(request.content)
            assert payload == {
                "model": "qwen3-tts-vd-2026-01-26",
                "input": {
                    "text": "Come on! Two more!",
                    "voice": "lianleme_coach_123",
                },
            }
            return httpx.Response(
                200,
                json={
                    "output": {
                        "audio": {"url": "https://cdn.example.test/coach.wav"}
                    },
                    "request_id": "request-456",
                },
            )

        assert request.url == "https://cdn.example.test/coach.wav"
        return httpx.Response(200, content=synthesized_wav)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = QwenVoiceDesignClient(
            api_key="test-key",
            api_base="https://example.test/api/v1",
            http_client=http_client,
        )
        result = await client.synthesize(
            text="Come on! Two more!",
            voice_id="lianleme_coach_123",
        )

    assert result.audio == synthesized_wav
    assert result.request_id == "request-456"


@pytest.mark.asyncio
async def test_create_voice_rejects_success_response_without_voice_id():
    """Raise a readable integration error when DashScope omits the voice ID."""

    async def handler(request: httpx.Request) -> httpx.Response:
        """Return a structurally incomplete successful response."""
        return httpx.Response(200, json={"output": {}, "request_id": "request-bad"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = QwenVoiceDesignClient(
            api_key="test-key",
            api_base="https://example.test/api/v1",
            http_client=http_client,
        )
        with pytest.raises(QwenTTSAPIError, match="voice ID"):
            await client.create_voice(
                voice_prompt="original coach voice",
                preview_text="Get up!",
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "preview_wav",
    [b"", b"RIFF-not-a-wave", b"<html>error</html>", make_pcm_wav()[:-1]],
)
async def test_create_voice_rejects_invalid_preview_wav(preview_wav):
    """Reject empty, truncated, or non-WAV preview payloads from voice design."""

    async def handler(request: httpx.Request) -> httpx.Response:
        """Return an invalid base64-encoded preview in an otherwise valid response."""
        return httpx.Response(
            200,
            json={
                "output": {
                    "voice": "lianleme_coach_123",
                    "preview_audio": {
                        "data": base64.b64encode(preview_wav).decode("ascii")
                    },
                }
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = QwenVoiceDesignClient(
            api_key="test-key",
            api_base="https://example.test/api/v1",
            http_client=http_client,
        )
        with pytest.raises(QwenTTSAPIError, match="valid WAV"):
            await client.create_voice(
                voice_prompt="original coach voice",
                preview_text="Get up!",
            )


@pytest.mark.asyncio
async def test_synthesize_rejects_invalid_downloaded_wav():
    """Reject an HTML response downloaded from a nominally successful audio URL."""

    async def handler(request: httpx.Request) -> httpx.Response:
        """Return valid metadata followed by a non-audio download body."""
        if request.method == "POST":
            return httpx.Response(
                200,
                json={"output": {"audio": {"url": "https://cdn.example.test/a.wav"}}},
            )
        return httpx.Response(200, content=b"<html>expired</html>")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = QwenVoiceDesignClient(
            api_key="test-key",
            api_base="https://example.test/api/v1",
            http_client=http_client,
        )
        with pytest.raises(QwenTTSAPIError, match="valid WAV"):
            await client.synthesize(text="Come on!", voice_id="voice-123")


@pytest.mark.asyncio
async def test_api_error_preserves_dashscope_diagnostics():
    """Expose the DashScope error code, message, and request ID for troubleshooting."""

    async def handler(request: httpx.Request) -> httpx.Response:
        """Return a representative structured DashScope HTTP error."""
        return httpx.Response(
            400,
            json={
                "code": "InvalidParameter",
                "message": "voice and model do not match",
                "request_id": "request-error-123",
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = QwenVoiceDesignClient(
            api_key="test-key",
            api_base="https://example.test/api/v1",
            http_client=http_client,
        )
        with pytest.raises(QwenTTSAPIError) as error:
            await client.synthesize(text="Come on!", voice_id="voice-123")

    message = str(error.value)
    assert "InvalidParameter" in message
    assert "voice and model do not match" in message
    assert "request-error-123" in message


def test_tts_settings_default_to_ryan_system_voice(monkeypatch):
    """Use the Ryan system voice with its compatible Qwen3-TTS Flash model."""
    for name in (
        "QWEN_AUDIO_API_BASE",
        "QWEN_AUDIO_TTS_MODEL",
        "QWEN_AUDIO_TTS_VOICE",
        "QWEN_AUDIO_VOICE_DESIGN_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)
    configured = Settings(_env_file=None)

    assert configured.QWEN_AUDIO_API_BASE == "https://dashscope.aliyuncs.com/api/v1"
    assert configured.QWEN_AUDIO_TTS_MODEL == "qwen3-tts-flash"
    assert configured.QWEN_AUDIO_TTS_VOICE == "Ryan"
    assert configured.QWEN_AUDIO_VOICE_DESIGN_MODEL == "qwen3-tts-vd-2026-01-26"


def test_coach_voice_prompt_describes_an_original_nyc_fitness_character():
    """Keep the designed persona explicit, energetic, and independent of real people."""
    assert "New York City English" in COACH_VOICE_PROMPT
    assert "AAVE-influenced rhythm" in COACH_VOICE_PROMPT
    assert "must not resemble any real person" in COACH_VOICE_PROMPT.lower()
    assert "Get your ass up" in PREVIEW_TEXT
    assert "Don't fold on me now" in EVALUATION_TEXT
    assert "homie" in voice_script.WILD_COACH_TEXT.lower()
    assert "bro" in voice_script.WILD_COACH_TEXT.lower()
    assert "shit" in voice_script.WILD_COACH_TEXT.lower()


def test_write_audio_artifacts_isolates_each_voice(tmp_path):
    """Keep each voice's preview, evaluation, and metadata in its own directory."""
    preview_wav = make_pcm_wav(b"\x01\x00")
    evaluation_wav = make_pcm_wav(b"\x02\x00")
    designed_voice = DesignedVoice(
        voice_id="lianleme_coach_123",
        preview_audio=preview_wav,
        request_id="design-request-123",
    )
    speech = SynthesizedSpeech(
        audio=evaluation_wav,
        request_id="synthesis-request-456",
    )

    artifacts = write_audio_artifacts(
        tmp_path,
        designed_voice,
        speech,
        target_model="qwen3-tts-vd-2026-01-26",
    )

    assert artifacts.voice_dir == tmp_path / "lianleme_coach_123"
    assert artifacts.preview_path.name == "lianleme-coach-preview.wav"
    assert artifacts.evaluation_path.name == "lianleme-coach-evaluation.wav"
    assert artifacts.manifest_path.name == "voice.json"
    assert artifacts.preview_path.read_bytes() == preview_wav
    assert artifacts.evaluation_path.read_bytes() == evaluation_wav
    assert json.loads(artifacts.manifest_path.read_text()) == {
        "design_request_id": "design-request-123",
        "evaluation_request_id": "synthesis-request-456",
        "target_model": "qwen3-tts-vd-2026-01-26",
        "voice_id": "lianleme_coach_123",
    }


def test_cli_help_does_not_create_a_voice(monkeypatch, capsys):
    """Show help and exit without invoking the network-backed creation workflow."""

    async def fail_if_called(output_dir):
        """Fail the test if help unexpectedly reaches voice creation."""
        pytest.fail("voice creation must not run for --help")

    monkeypatch.setattr(voice_script, "create_coach_voice", fail_if_called)

    with pytest.raises(SystemExit) as exit_info:
        voice_script.main(["--help"])

    assert exit_info.value.code == 0
    help_text = capsys.readouterr().out
    assert "usage:" in help_text
    assert "synthesize" in help_text


def test_cli_requires_an_explicit_command(monkeypatch):
    """Refuse to call paid APIs when no explicit subcommand is supplied."""

    async def fail_if_called(output_dir):
        """Fail the test if an empty invocation reaches voice creation."""
        pytest.fail("voice creation must require an explicit command")

    monkeypatch.setattr(voice_script, "create_coach_voice", fail_if_called)

    with pytest.raises(SystemExit) as exit_info:
        voice_script.main([])

    assert exit_info.value.code == 2


class FakeAsyncClient:
    """Provide a network-free async context manager for CLI orchestration tests."""

    def __init__(self, *args, **kwargs):
        """Accept the same construction arguments as httpx.AsyncClient."""

    async def __aenter__(self):
        """Return the fake client when entering the async context."""
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        """Leave the fake client context without suppressing exceptions."""


class FailingSynthesisClient:
    """Create a known voice and then simulate evaluation synthesis failure."""

    constructor_kwargs: dict = {}

    def __init__(self, **kwargs):
        """Record the production client constructor arguments."""
        self.constructor_kwargs = kwargs
        type(self).constructor_kwargs = kwargs

    async def create_voice(self, **kwargs):
        """Return a created remote voice with a valid local preview."""
        return DesignedVoice(
            voice_id="lianleme_coach_failure_123",
            preview_audio=make_pcm_wav(),
            request_id="design-request-failure",
        )

    async def synthesize(self, **kwargs):
        """Simulate a provider failure after voice creation succeeds."""
        raise QwenTTSAPIError("evaluation failed")


class RecordingSynthesisClient:
    """Record existing-voice synthesis while forbidding voice creation."""

    calls: list[dict] = []

    def __init__(self, **kwargs):
        """Accept the production client constructor arguments."""

    async def create_voice(self, **kwargs):
        """Fail if the existing-voice workflow attempts paid voice design."""
        pytest.fail("existing-voice synthesis must not create a new voice")

    async def synthesize(self, **kwargs):
        """Record synthesis arguments and return a valid local WAV fixture."""
        self.calls.append(kwargs)
        return SynthesizedSpeech(
            audio=make_pcm_wav(b"\x01\x00\x02\x00"),
            request_id="wild-preview-request-123",
        )


@pytest.mark.asyncio
async def test_creation_error_includes_voice_id_when_local_initialization_fails(
    monkeypatch,
    tmp_path,
):
    """Keep the remote voice traceable even when its first local write fails."""
    monkeypatch.setattr(voice_script.settings, "QWEN_AUDIO_API_KEY", "test-key")
    monkeypatch.setattr(voice_script.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(
        voice_script,
        "QwenVoiceDesignClient",
        FailingSynthesisClient,
    )

    def fail_initialization(*args, **kwargs):
        """Simulate a local disk error before the manifest can be written."""
        raise OSError("disk full")

    monkeypatch.setattr(
        voice_script,
        "initialize_audio_artifacts",
        fail_initialization,
    )

    with pytest.raises(RuntimeError, match="lianleme_coach_failure_123"):
        await voice_script.create_coach_voice(tmp_path)


@pytest.mark.asyncio
async def test_synthesis_failure_keeps_created_voice_manifest(monkeypatch, tmp_path):
    """Persist the created voice ID before evaluation synthesis can fail."""
    FailingSynthesisClient.constructor_kwargs = {}
    monkeypatch.setattr(
        voice_script,
        "settings",
        SimpleNamespace(
            QWEN_AUDIO_API_KEY="test-key",
            QWEN_API_KEY="",
            QWEN_AUDIO_API_BASE="https://example.test/api/v1",
            QWEN_AUDIO_TTS_MODEL="qwen3-tts-flash",
            QWEN_AUDIO_VOICE_DESIGN_MODEL="qwen3-tts-vd-2026-01-26",
        ),
    )
    monkeypatch.setattr(voice_script.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(
        voice_script,
        "QwenVoiceDesignClient",
        FailingSynthesisClient,
    )

    with pytest.raises(RuntimeError, match="lianleme_coach_failure_123"):
        await voice_script.create_coach_voice(tmp_path)

    manifest_path = tmp_path / "lianleme_coach_failure_123" / "voice.json"
    assert json.loads(manifest_path.read_text())["voice_id"] == (
        "lianleme_coach_failure_123"
    )
    assert FailingSynthesisClient.constructor_kwargs["target_model"] == (
        "qwen3-tts-vd-2026-01-26"
    )


@pytest.mark.asyncio
async def test_synthesize_existing_voice_writes_wild_preview_and_metadata(
    monkeypatch,
    tmp_path,
):
    """Reuse the configured voice and save traceable wild-style preview artifacts."""
    RecordingSynthesisClient.calls.clear()
    monkeypatch.setattr(voice_script.settings, "QWEN_AUDIO_API_KEY", "test-key")
    monkeypatch.setattr(
        voice_script.settings,
        "QWEN_AUDIO_TTS_VOICE",
        "lianleme_coach_selected_123",
    )
    monkeypatch.setattr(voice_script.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(
        voice_script,
        "QwenVoiceDesignClient",
        RecordingSynthesisClient,
    )

    audio_path = await voice_script.synthesize_existing_coach(tmp_path)

    assert RecordingSynthesisClient.calls == [
        {
            "text": voice_script.WILD_COACH_TEXT,
            "voice_id": "lianleme_coach_selected_123",
        }
    ]
    assert audio_path == (
        tmp_path
        / "lianleme_coach_selected_123"
        / "lianleme-coach-wild-preview.wav"
    )
    assert audio_path.read_bytes() == make_pcm_wav(b"\x01\x00\x02\x00")
    assert json.loads(audio_path.with_suffix(".json").read_text()) == {
        "request_id": "wild-preview-request-123",
        "target_model": "qwen3-tts-flash",
        "text": voice_script.WILD_COACH_TEXT,
        "voice_id": "lianleme_coach_selected_123",
    }


@pytest.mark.asyncio
async def test_synthesize_existing_voice_requires_configured_voice(monkeypatch, tmp_path):
    """Refuse synthesis when no reviewed reusable voice ID is configured."""
    monkeypatch.setattr(voice_script.settings, "QWEN_AUDIO_API_KEY", "test-key")
    monkeypatch.setattr(voice_script.settings, "QWEN_AUDIO_TTS_VOICE", "")

    with pytest.raises(RuntimeError, match="QWEN_AUDIO_TTS_VOICE"):
        await voice_script.synthesize_existing_coach(tmp_path)


def test_synthesize_command_never_calls_voice_creation(monkeypatch, tmp_path):
    """Route the explicit synthesis command only to the selected existing voice."""
    calls: list[tuple] = []

    async def fail_create(output_dir):
        """Fail if the synthesis CLI accidentally reaches voice design."""
        pytest.fail("synthesize command must not create a new voice")

    async def record_synthesis(output_dir, text):
        """Record the CLI arguments without making a network request."""
        calls.append((output_dir, text))
        return output_dir / "wild.wav"

    monkeypatch.setattr(voice_script, "create_coach_voice", fail_create)
    monkeypatch.setattr(voice_script, "synthesize_existing_coach", record_synthesis)

    voice_script.main(["synthesize", "--output-dir", str(tmp_path)])

    assert calls == [(tmp_path, voice_script.WILD_COACH_TEXT)]
