"""Qwen Voice Design and speech synthesis REST client."""

from __future__ import annotations

import base64
import struct
import wave
from dataclasses import dataclass
from io import BytesIO
from typing import Any

import httpx


class QwenTTSAPIError(RuntimeError):
    """Describe a failed or malformed Qwen TTS API operation."""


@dataclass(frozen=True)
class DesignedVoice:
    """Hold a reusable designed voice and its generated preview audio."""

    voice_id: str
    preview_audio: bytes
    request_id: str | None = None


@dataclass(frozen=True)
class SynthesizedSpeech:
    """Hold synthesized speech bytes and the originating request ID."""

    audio: bytes
    request_id: str | None = None


class QwenVoiceDesignClient:
    """Create original Qwen voices and synthesize system or custom voices."""

    VOICE_DESIGN_PATH = "/services/audio/tts/customization"
    SYNTHESIS_PATH = "/services/aigc/multimodal-generation/generation"

    def __init__(
        self,
        *,
        api_key: str,
        api_base: str,
        http_client: httpx.AsyncClient,
        target_model: str = "qwen3-tts-vd-2026-01-26",
    ) -> None:
        """Configure the API credentials, endpoint, and matching TTS model."""
        if not api_key.strip():
            raise ValueError("Qwen TTS API key is required")
        self._api_key = api_key
        self._api_base = api_base.rstrip("/")
        self._http_client = http_client
        self.target_model = target_model

    async def create_voice(
        self,
        *,
        voice_prompt: str,
        preview_text: str,
        preferred_name: str = "lianleme_coach",
    ) -> DesignedVoice:
        """Create an original voice and decode the returned WAV preview."""
        payload = {
            "model": "qwen-voice-design",
            "input": {
                "action": "create",
                "target_model": self.target_model,
                "preferred_name": preferred_name,
                "voice_prompt": voice_prompt,
                "preview_text": preview_text,
            },
            "parameters": {"sample_rate": 24000, "response_format": "wav"},
        }
        result = await self._post_json(self.VOICE_DESIGN_PATH, payload)
        output = result.get("output")
        if not isinstance(output, dict) or not isinstance(output.get("voice"), str):
            raise QwenTTSAPIError("Qwen voice design response did not include a voice ID")

        preview = output.get("preview_audio")
        encoded_audio = preview.get("data") if isinstance(preview, dict) else None
        if not isinstance(encoded_audio, str):
            raise QwenTTSAPIError("Qwen voice design response did not include preview audio")
        try:
            preview_audio = base64.b64decode(encoded_audio, validate=True)
        except ValueError as exc:
            raise QwenTTSAPIError("Qwen voice design returned invalid preview audio") from exc
        _validate_wav(preview_audio, source="Qwen voice design preview")

        request_id = result.get("request_id")
        return DesignedVoice(
            voice_id=output["voice"],
            preview_audio=preview_audio,
            request_id=request_id if isinstance(request_id, str) else None,
        )

    async def synthesize(self, *, text: str, voice_id: str) -> SynthesizedSpeech:
        """Generate speech and download the temporary WAV artifact."""
        payload = {
            "model": self.target_model,
            "input": {"text": text, "voice": voice_id},
        }
        result = await self._post_json(self.SYNTHESIS_PATH, payload)
        output = result.get("output")
        audio = output.get("audio") if isinstance(output, dict) else None
        audio_url = audio.get("url") if isinstance(audio, dict) else None
        if not isinstance(audio_url, str):
            raise QwenTTSAPIError("Qwen TTS response did not include an audio URL")

        try:
            response = await self._http_client.get(audio_url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise QwenTTSAPIError("Failed to download synthesized Qwen audio") from exc
        _validate_wav(response.content, source="Downloaded Qwen audio")

        request_id = result.get("request_id")
        return SynthesizedSpeech(
            audio=response.content,
            request_id=request_id if isinstance(request_id, str) else None,
        )

    async def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Post an authenticated JSON request and validate its response envelope."""
        try:
            response = await self._http_client.post(
                f"{self._api_base}{path}",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            result = response.json()
        except httpx.HTTPStatusError as exc:
            raise QwenTTSAPIError(_format_http_error(exc.response)) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise QwenTTSAPIError("Qwen TTS API request failed") from exc

        if not isinstance(result, dict):
            raise QwenTTSAPIError("Qwen TTS API returned a malformed response")
        return result


def _validate_wav(audio: bytes, *, source: str) -> None:
    """Require a readable, complete WAV while accepting Qwen streaming sentinels."""
    try:
        with wave.open(BytesIO(audio), "rb") as wav_file:
            if wav_file.getnchannels() < 1 or wav_file.getframerate() < 1:
                raise QwenTTSAPIError(f"{source} was not a valid WAV file")
            frame_width = wav_file.getnchannels() * wav_file.getsampwidth()
            data_size = _wav_data_size(audio, source=source)
            if frame_width < 1 or data_size < frame_width:
                raise QwenTTSAPIError(f"{source} was not a valid WAV file")
            if data_size % frame_width != 0:
                raise QwenTTSAPIError(f"{source} was not a valid WAV file")
    except (EOFError, wave.Error) as exc:
        raise QwenTTSAPIError(f"{source} was not a valid WAV file") from exc


def _wav_data_size(audio: bytes, *, source: str) -> int:
    """Return actual PCM bytes and distinguish stream sentinels from truncation."""
    streaming_size_floor = 0x7FFF0000
    if len(audio) < 12 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        raise QwenTTSAPIError(f"{source} was not a valid WAV file")

    riff_size = struct.unpack_from("<I", audio, 4)[0]
    if riff_size < streaming_size_floor and riff_size + 8 > len(audio):
        raise QwenTTSAPIError(f"{source} was not a valid WAV file")

    offset = 12
    while offset + 8 <= len(audio):
        chunk_name = audio[offset : offset + 4]
        declared_size = struct.unpack_from("<I", audio, offset + 4)[0]
        chunk_start = offset + 8
        available_size = len(audio) - chunk_start
        if chunk_name == b"data":
            if declared_size >= streaming_size_floor:
                return available_size
            if declared_size > available_size:
                raise QwenTTSAPIError(f"{source} was not a valid WAV file")
            return declared_size
        if declared_size > available_size:
            raise QwenTTSAPIError(f"{source} was not a valid WAV file")
        offset = chunk_start + declared_size + (declared_size % 2)

    raise QwenTTSAPIError(f"{source} was not a valid WAV file")


def _format_http_error(response: httpx.Response) -> str:
    """Preserve structured DashScope diagnostics in a safe integration error."""
    message = f"Qwen TTS API returned HTTP {response.status_code}"
    try:
        payload = response.json()
    except ValueError:
        return message
    if not isinstance(payload, dict):
        return message

    details = [
        f"{label}={payload[key]}"
        for key, label in (
            ("code", "code"),
            ("message", "message"),
            ("request_id", "request_id"),
        )
        if isinstance(payload.get(key), str) and payload[key]
    ]
    return f"{message} ({', '.join(details)})" if details else message
