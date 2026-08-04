"""Validate WAV audio and produce Rhubarb mouth-cue timelines safely."""

from __future__ import annotations

import asyncio
import json
import math
import struct
import tempfile
import wave
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Literal

CoachViseme = Literal["A", "B", "C", "D", "E", "F", "G", "H", "X"]
_ALLOWED_VISEMES = frozenset("ABCDEFGHX")
_TIMING_TOLERANCE_SECONDS = 0.04
_STREAMING_SIZE_FLOOR = 0x7FFF0000


class LipSyncError(RuntimeError):
    """Report an invalid or failed lip-sync analysis."""


class LipSyncUnavailable(LipSyncError):
    """Report that the configured Rhubarb executable cannot be started."""


@dataclass(frozen=True, slots=True)
class MouthCue:
    """Represent one validated mouth shape over an audio time interval."""

    start: float
    end: float
    value: CoachViseme


@dataclass(frozen=True, slots=True)
class LipSyncResult:
    """Hold a validated WAV duration and its ordered mouth timeline."""

    duration_seconds: float
    mouth_cues: tuple[MouthCue, ...]


def recognizer_for_text(text: str) -> str:
    """Select phonetic recognition whenever the dialog contains CJK text."""
    for character in text:
        codepoint = ord(character)
        if (
            0x3400 <= codepoint <= 0x4DBF
            or 0x4E00 <= codepoint <= 0x9FFF
            or 0xF900 <= codepoint <= 0xFAFF
            or 0x3040 <= codepoint <= 0x30FF
            or 0xAC00 <= codepoint <= 0xD7AF
        ):
            return "phonetic"
    return "pocketSphinx"


def _wav_data_span(audio: bytes) -> tuple[int, int]:
    """Locate actual PCM bytes while accepting Qwen's open-ended size sentinel."""
    if len(audio) < 12 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        raise LipSyncError("TTS payload is not a valid WAV file")
    riff_size = struct.unpack_from("<I", audio, 4)[0]
    if riff_size < _STREAMING_SIZE_FLOOR and riff_size + 8 > len(audio):
        raise LipSyncError("TTS WAV payload is truncated")

    offset = 12
    while offset + 8 <= len(audio):
        chunk_name = audio[offset : offset + 4]
        declared_size = struct.unpack_from("<I", audio, offset + 4)[0]
        chunk_start = offset + 8
        available_size = len(audio) - chunk_start
        if chunk_name == b"data":
            if declared_size >= _STREAMING_SIZE_FLOOR:
                return chunk_start, available_size
            if declared_size > available_size:
                raise LipSyncError("TTS WAV data chunk is truncated")
            return chunk_start, declared_size
        if declared_size > available_size:
            raise LipSyncError("TTS WAV chunk is truncated")
        offset = chunk_start + declared_size + (declared_size % 2)
    raise LipSyncError("TTS WAV payload has no data chunk")


def _normalized_wav(audio: bytes) -> bytes:
    """Replace streaming RIFF sentinels with finite sizes for Rhubarb."""
    data_start, data_size = _wav_data_span(audio)
    normalized = bytearray(audio)
    struct.pack_into("<I", normalized, 4, len(normalized) - 8)
    struct.pack_into("<I", normalized, data_start - 4, data_size)
    return bytes(normalized)


def wav_duration(audio: bytes) -> float:
    """Calculate duration from actual PCM bytes instead of sentinel frame counts."""
    try:
        with wave.open(BytesIO(audio), "rb") as wav_file:
            frame_rate = wav_file.getframerate()
            frame_width = wav_file.getnchannels() * wav_file.getsampwidth()
    except (EOFError, wave.Error) as exc:
        raise LipSyncError("TTS payload is not a valid WAV file") from exc
    _, data_size = _wav_data_span(audio)
    if frame_rate <= 0 or frame_width <= 0 or data_size < frame_width or data_size % frame_width:
        raise LipSyncError("WAV PCM format is invalid")
    duration = data_size / frame_width / frame_rate
    if not math.isfinite(duration) or duration <= 0:
        raise LipSyncError("WAV duration must be positive and finite")
    return duration


def _finite_number(value: Any, field_name: str) -> float:
    """Convert one Rhubarb timing field to a finite float."""
    if isinstance(value, bool):
        raise LipSyncError(f"{field_name} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise LipSyncError(f"{field_name} must be numeric") from exc
    if not math.isfinite(number):
        raise LipSyncError(f"{field_name} must be finite")
    return number


def parse_rhubarb_result(payload: Any, wav_duration: float) -> LipSyncResult:
    """Validate Rhubarb JSON against the source WAV and return typed cues."""
    if not isinstance(payload, dict):
        raise LipSyncError("Rhubarb output must be a JSON object")
    if not math.isfinite(wav_duration) or wav_duration <= 0:
        raise LipSyncError("WAV duration must be positive and finite")

    metadata = payload.get("metadata")
    raw_cues = payload.get("mouthCues")
    if not isinstance(metadata, dict) or not isinstance(raw_cues, list) or not raw_cues:
        raise LipSyncError("Rhubarb output is missing metadata or mouth cues")

    reported_duration = _finite_number(metadata.get("duration"), "metadata.duration")
    if abs(reported_duration - wav_duration) > _TIMING_TOLERANCE_SECONDS:
        raise LipSyncError("Rhubarb duration does not match the WAV payload")

    cues: list[MouthCue] = []
    previous_end = 0.0
    for index, raw_cue in enumerate(raw_cues):
        if not isinstance(raw_cue, dict):
            raise LipSyncError(f"mouthCues[{index}] must be an object")
        start = _finite_number(raw_cue.get("start"), f"mouthCues[{index}].start")
        end = _finite_number(raw_cue.get("end"), f"mouthCues[{index}].end")
        value = raw_cue.get("value")
        if value not in _ALLOWED_VISEMES:
            raise LipSyncError(f"mouthCues[{index}].value is unsupported")
        if start < 0 or end <= start or end > wav_duration + _TIMING_TOLERANCE_SECONDS:
            raise LipSyncError(f"mouthCues[{index}] is outside the WAV duration")
        if index and start < previous_end - 0.001:
            raise LipSyncError("mouth cues overlap or are out of order")
        cues.append(MouthCue(start=start, end=end, value=value))
        previous_end = end

    if cues[0].value != "X" or cues[-1].value != "X":
        raise LipSyncError("mouth timeline must start and end at rest")
    if cues[0].start > _TIMING_TOLERANCE_SECONDS:
        raise LipSyncError("mouth timeline does not begin with the WAV")
    if abs(cues[-1].end - wav_duration) > _TIMING_TOLERANCE_SECONDS:
        raise LipSyncError("mouth timeline does not cover the complete WAV")
    return LipSyncResult(duration_seconds=wav_duration, mouth_cues=tuple(cues))


async def _kill_and_wait(process: asyncio.subprocess.Process) -> None:
    """Terminate and reap a Rhubarb child process that cannot finish normally."""
    try:
        process.kill()
    except ProcessLookupError:
        pass
    await process.wait()


async def align_wav(
    audio: bytes,
    text: str,
    *,
    binary_path: Path,
    timeout_seconds: float,
) -> LipSyncResult:
    """Run Rhubarb without a shell and validate its generated JSON timeline."""
    duration = wav_duration(audio)
    with tempfile.TemporaryDirectory(prefix="lianleme-rhubarb-") as temp_dir:
        work_dir = Path(temp_dir)
        audio_path = work_dir / "speech.wav"
        dialog_path = work_dir / "dialog.txt"
        output_path = work_dir / "mouth-cues.json"
        audio_path.write_bytes(_normalized_wav(audio))
        dialog_path.write_text(text, encoding="utf-8")

        args = (
            str(binary_path),
            "-f",
            "json",
            "-o",
            str(output_path),
            "--recognizer",
            recognizer_for_text(text),
            "--extendedShapes",
            "GHX",
            "--dialogFile",
            str(dialog_path),
            str(audio_path),
        )
        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except (FileNotFoundError, PermissionError, OSError) as exc:
            raise LipSyncUnavailable("Rhubarb executable is unavailable") from exc

        try:
            _, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=max(timeout_seconds, 0.1),
            )
        except asyncio.CancelledError:
            await _kill_and_wait(process)
            raise
        except TimeoutError as exc:
            await _kill_and_wait(process)
            raise LipSyncError("Rhubarb analysis timed out") from exc

        if process.returncode != 0:
            detail = stderr.decode("utf-8", errors="replace").strip()[:500]
            raise LipSyncError(f"Rhubarb analysis failed: {detail or 'unknown error'}")
        try:
            payload = json.loads(output_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise LipSyncError("Rhubarb returned malformed JSON") from exc
        return parse_rhubarb_result(payload, wav_duration=duration)
