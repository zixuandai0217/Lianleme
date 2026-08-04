"""Runtime helpers for coach TTS configuration, synthesis, and short-lived cache."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeVar

import httpx

from app.core.config import settings
from app.services.ai.lip_sync import LipSyncError, MouthCue, align_wav, wav_duration
from app.services.ai.tts_service import QwenVoiceDesignClient

logger = logging.getLogger(__name__)

# Small in-process cache so demo replay does not re-bill identical coach lines.
_CACHE_MAX = 32
_tts_cache: OrderedDict[str, bytes] = OrderedDict()
_animated_cache: OrderedDict[str, "AnimatedSpeech"] = OrderedDict()
_tts_inflight: dict[str, asyncio.Task[bytes]] = {}
_animated_inflight: dict[str, asyncio.Task["AnimatedSpeech"]] = {}
_ResultT = TypeVar("_ResultT")


@dataclass(frozen=True, slots=True)
class AnimatedSpeech:
    """Bundle synthesized audio with its synchronized facial animation data."""

    audio: bytes
    duration_seconds: float
    mouth_cues: tuple[MouthCue, ...]
    alignment: Literal["rhubarb", "energy"]


def tts_is_configured(
    api_key: str | None = None,
    voice_id: str | None = None,
) -> bool:
    """Return True when a voice and API key are available for synthesis."""
    resolved_voice = (
        voice_id if voice_id is not None else settings.QWEN_AUDIO_TTS_VOICE
    ).strip()
    resolved_key = api_key.strip() if api_key is not None else _resolve_api_key()
    return bool(resolved_voice and resolved_key)


def _rhubarb_path() -> Path:
    """Resolve the configured Rhubarb path relative to the backend directory."""
    configured = Path((settings.RHUBARB_BIN or "").strip()).expanduser()
    if configured.is_absolute():
        return configured
    backend_dir = Path(__file__).resolve().parents[3]
    return backend_dir / configured


def lip_sync_is_configured() -> bool:
    """Return True when the configured Rhubarb executable is installed."""
    configured = (settings.RHUBARB_BIN or "").strip()
    if not configured:
        return False
    binary_path = _rhubarb_path()
    return binary_path.is_file() and binary_path.stat().st_mode & 0o111 != 0


def clear_tts_cache() -> None:
    """Drop cached WAV payloads (used by tests and optional runtime resets)."""
    _tts_cache.clear()
    _animated_cache.clear()


def _resolve_api_key() -> str:
    """Prefer the audio-specific key, then fall back to the general Qwen key."""
    return (settings.QWEN_AUDIO_API_KEY or settings.QWEN_API_KEY or "").strip()


def _build_client(
    http_client: httpx.AsyncClient,
    api_key: str | None = None,
) -> QwenVoiceDesignClient:
    """Construct the Qwen voice client from application settings."""
    return QwenVoiceDesignClient(
        api_key=api_key.strip() if api_key is not None else _resolve_api_key(),
        api_base=settings.QWEN_AUDIO_API_BASE,
        http_client=http_client,
        target_model=settings.QWEN_AUDIO_TTS_MODEL,
    )


def _cache_key(text: str, voice_id: str, api_key: str | None = None) -> str:
    """Build an account-scoped cache key without retaining provider credentials."""
    credential_scope = hashlib.sha256(
        (api_key if api_key is not None else "system").encode("utf-8")
    ).hexdigest()
    digest = hashlib.sha256(
        f"{credential_scope}\n{voice_id}\n{text}".encode("utf-8")
    ).hexdigest()
    return digest


async def _run_single_flight(
    key: str,
    registry: dict[str, asyncio.Task[_ResultT]],
    operation: Callable[[], Awaitable[_ResultT]],
) -> _ResultT:
    """Share one keyed async operation without letting one caller cancel it for peers."""
    task = registry.get(key)
    if task is None:

        async def run_and_clear() -> _ResultT:
            """Remove only this producer after it finishes or raises."""
            try:
                return await operation()
            finally:
                if registry.get(key) is asyncio.current_task():
                    registry.pop(key, None)

        def observe_completion(completed: asyncio.Task[_ResultT]) -> None:
            """Retrieve orphaned failures without changing what active waiters receive."""
            if not completed.cancelled():
                completed.exception()

        task = asyncio.create_task(run_and_clear())
        task.add_done_callback(observe_completion)
        registry[key] = task
    return await asyncio.shield(task)


async def synthesize_speech(
    text: str,
    *,
    api_key: str | None = None,
    voice_id: str | None = None,
) -> bytes:
    """Synthesize coach speech as WAV bytes, reusing a short in-memory cache."""
    resolved_voice = (
        voice_id if voice_id is not None else settings.QWEN_AUDIO_TTS_VOICE
    ).strip()
    configured = (
        tts_is_configured()
        if api_key is None and voice_id is None
        else tts_is_configured(api_key, voice_id=resolved_voice)
    )
    if not configured:
        raise RuntimeError("Coach TTS is not configured")

    key = _cache_key(text, resolved_voice, api_key)
    cached = _tts_cache.get(key)
    if cached is not None:
        _tts_cache.move_to_end(key)
        return cached

    async def produce() -> bytes:
        """Call Qwen once and publish the completed WAV to the LRU cache."""
        async with httpx.AsyncClient(timeout=60.0) as http_client:
            client = (
                _build_client(http_client)
                if api_key is None
                else _build_client(http_client, api_key)
            )
            result = await client.synthesize(text=text, voice_id=resolved_voice)

        audio = result.audio
        _tts_cache[key] = audio
        _tts_cache.move_to_end(key)
        while len(_tts_cache) > _CACHE_MAX:
            _tts_cache.popitem(last=False)
        return audio

    return await _run_single_flight(key, _tts_inflight, produce)


async def synthesize_animated_speech(
    text: str,
    *,
    api_key: str | None = None,
    voice_id: str | None = None,
) -> AnimatedSpeech:
    """Synthesize one utterance and attach Rhubarb cues or an energy fallback."""
    resolved_voice = (
        voice_id if voice_id is not None else settings.QWEN_AUDIO_TTS_VOICE
    ).strip()
    configured = (
        tts_is_configured()
        if api_key is None and voice_id is None
        else tts_is_configured(api_key, voice_id=resolved_voice)
    )
    if not configured:
        raise RuntimeError("Coach TTS is not configured")

    key = _cache_key(text, resolved_voice, api_key)
    cached = _animated_cache.get(key)
    if cached is not None:
        _animated_cache.move_to_end(key)
        return cached

    async def produce() -> AnimatedSpeech:
        """Create audio and alignment once before publishing the animated cache entry."""
        audio = (
            await synthesize_speech(text)
            if api_key is None and voice_id is None
            else await synthesize_speech(
                text,
                api_key=api_key,
                voice_id=resolved_voice,
            )
        )
        duration = wav_duration(audio)
        result = AnimatedSpeech(
            audio=audio,
            duration_seconds=duration,
            mouth_cues=(),
            alignment="energy",
        )
        if lip_sync_is_configured():
            try:
                aligned = await align_wav(
                    audio,
                    text,
                    binary_path=_rhubarb_path(),
                    timeout_seconds=settings.RHUBARB_TIMEOUT_SECONDS,
                )
                result = AnimatedSpeech(
                    audio=audio,
                    duration_seconds=aligned.duration_seconds,
                    mouth_cues=aligned.mouth_cues,
                    alignment="rhubarb",
                )
            except LipSyncError as exc:
                logger.warning("Rhubarb alignment unavailable; using energy fallback: %s", exc)
            except Exception:
                logger.exception("Unexpected Rhubarb failure; using energy fallback")

        _animated_cache[key] = result
        _animated_cache.move_to_end(key)
        while len(_animated_cache) > _CACHE_MAX:
            _animated_cache.popitem(last=False)
        return result

    return await _run_single_flight(key, _animated_inflight, produce)
