"""Rhubarb mouth-cue alignment contract tests."""

from __future__ import annotations

import asyncio
import importlib
import json
import math
import struct
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

try:
    lip_sync = importlib.import_module("app.services.ai.lip_sync")
except ModuleNotFoundError:
    lip_sync = None


def require_symbol(name: str):
    """Return a lip-sync symbol while keeping RED failures as assertions."""
    assert lip_sync is not None, "lip_sync module is missing"
    symbol = getattr(lip_sync, name, None)
    assert symbol is not None, f"lip_sync.{name} is missing"
    return symbol


def make_pcm_wav(frames: bytes = b"\x00\x00" * 2400) -> bytes:
    """Build a short mono WAV fixture for real duration validation."""
    import wave
    from io import BytesIO

    buffer = BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(24000)
        wav_file.writeframes(frames)
    return buffer.getvalue()


def make_streaming_wav() -> bytes:
    """Replace finite RIFF sizes with the sentinels emitted by Qwen streaming WAV."""
    audio = bytearray(make_pcm_wav())
    struct.pack_into("<I", audio, 4, 0x7FFFFFBF)
    struct.pack_into("<I", audio, 40, 0x7FFFFF9B)
    return bytes(audio)


def test_recognizer_uses_phonetic_for_cjk_and_pocketsphinx_for_english():
    """Select the language-independent recognizer whenever CJK text appears."""
    recognizer_for_text = require_symbol("recognizer_for_text")

    assert recognizer_for_text("再来两个，homie!") == "phonetic"
    assert recognizer_for_text("Two more reps, homie!") == "pocketSphinx"


def test_wav_duration_uses_actual_pcm_bytes_for_streaming_sentinel():
    """Ignore Qwen's open-ended WAV length sentinel when measuring audio."""
    duration = require_symbol("wav_duration")(make_streaming_wav())

    assert math.isclose(duration, 0.1)


def test_parse_rhubarb_result_accepts_ordered_a_to_x_cues():
    """Parse validated Rhubarb JSON into typed mouth cues."""
    parse_rhubarb_result = require_symbol("parse_rhubarb_result")
    payload = {
        "metadata": {"duration": 0.1},
        "mouthCues": [
            {"start": 0.0, "end": 0.04, "value": "X"},
            {"start": 0.04, "end": 0.08, "value": "C"},
            {"start": 0.08, "end": 0.1, "value": "X"},
        ],
    }

    result = parse_rhubarb_result(payload, wav_duration=0.1)

    assert math.isclose(result.duration_seconds, 0.1)
    assert [cue.value for cue in result.mouth_cues] == ["X", "C", "X"]


def test_parse_rhubarb_result_requires_resting_boundary_cues():
    """Reject timelines that could start or finish with a visible mouth pop."""
    parse_rhubarb_result = require_symbol("parse_rhubarb_result")
    LipSyncError = require_symbol("LipSyncError")
    payload = {
        "metadata": {"duration": 0.1},
        "mouthCues": [
            {"start": 0.0, "end": 0.05, "value": "C"},
            {"start": 0.05, "end": 0.1, "value": "X"},
        ],
    }

    with pytest.raises(LipSyncError):
        parse_rhubarb_result(payload, wav_duration=0.1)


@pytest.mark.parametrize(
    "payload",
    [
        {"metadata": {"duration": 0.1}, "mouthCues": []},
        {
            "metadata": {"duration": 0.1},
            "mouthCues": [{"start": 0.0, "end": 0.1, "value": "Z"}],
        },
        {
            "metadata": {"duration": 0.1},
            "mouthCues": [
                {"start": 0.05, "end": 0.1, "value": "C"},
                {"start": 0.0, "end": 0.05, "value": "X"},
            ],
        },
    ],
)
def test_parse_rhubarb_result_rejects_unsafe_timelines(payload):
    """Reject empty, unknown, or out-of-order mouth timelines."""
    parse_rhubarb_result = require_symbol("parse_rhubarb_result")
    LipSyncError = require_symbol("LipSyncError")

    with pytest.raises(LipSyncError):
        parse_rhubarb_result(payload, wav_duration=0.1)


@pytest.mark.asyncio
async def test_align_wav_runs_rhubarb_without_a_shell_and_supplies_dialog(monkeypatch):
    """Invoke Rhubarb with a dialog file and parse its JSON output."""
    align_wav = require_symbol("align_wav")
    captured: dict[str, object] = {}

    class FakeProcess:
        """Mimic a successful asyncio subprocess."""

        returncode = 0

        async def communicate(self):
            return b"", b""

        def kill(self):
            captured["killed"] = True

    async def fake_create_subprocess_exec(*args, **kwargs):
        """Capture arguments and write the requested Rhubarb output file."""
        captured["args"] = args
        captured["kwargs"] = kwargs
        captured["wav"] = Path(args[-1]).read_bytes()
        output_path = Path(args[args.index("-o") + 1])
        output_path.write_text(
            json.dumps(
                {
                    "metadata": {"duration": 0.1},
                    "mouthCues": [
                        {"start": 0.0, "end": 0.05, "value": "X"},
                        {"start": 0.05, "end": 0.08, "value": "D"},
                        {"start": 0.08, "end": 0.1, "value": "X"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        return FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    result = await align_wav(
        make_streaming_wav(),
        "再来两个！",
        binary_path=Path("/opt/rhubarb/rhubarb"),
        timeout_seconds=2,
    )

    args = captured["args"]
    assert isinstance(args, tuple)
    assert args[0] == "/opt/rhubarb/rhubarb"
    assert args[args.index("--recognizer") + 1] == "phonetic"
    assert args[args.index("--extendedShapes") + 1] == "GHX"
    assert "--dialogFile" in args
    assert captured["kwargs"] == {
        "stdout": asyncio.subprocess.PIPE,
        "stderr": asyncio.subprocess.PIPE,
    }
    normalized_wav = captured["wav"]
    assert isinstance(normalized_wav, bytes)
    assert struct.unpack_from("<I", normalized_wav, 4)[0] == len(normalized_wav) - 8
    assert struct.unpack_from("<I", normalized_wav, 40)[0] == len(normalized_wav) - 44
    assert [cue.value for cue in result.mouth_cues] == ["X", "D", "X"]


@pytest.mark.asyncio
async def test_align_wav_kills_rhubarb_after_timeout(monkeypatch):
    """Terminate a stalled Rhubarb process and report a typed alignment error."""
    align_wav = require_symbol("align_wav")
    LipSyncError = require_symbol("LipSyncError")

    class SlowProcess:
        """Expose the subprocess methods used by the timeout branch."""

        returncode = None
        killed = False

        async def communicate(self):
            await asyncio.sleep(60)

        def kill(self):
            self.killed = True

        wait = AsyncMock(return_value=-9)

    process = SlowProcess()
    monkeypatch.setattr(
        asyncio,
        "create_subprocess_exec",
        AsyncMock(return_value=process),
    )

    with pytest.raises(LipSyncError, match="timed out"):
        await align_wav(
            make_pcm_wav(),
            "Keep moving.",
            binary_path=Path("/opt/rhubarb/rhubarb"),
            timeout_seconds=0.001,
        )

    assert process.killed is True
    process.wait.assert_awaited_once()


@pytest.mark.asyncio
async def test_align_wav_kills_rhubarb_when_caller_is_cancelled(monkeypatch):
    """Reap Rhubarb before propagating cancellation from a disconnected caller."""

    class SlowProcess:
        """Expose a cancellable subprocess that records cleanup calls."""

        returncode = None
        killed = False
        communicating = asyncio.Event()

        async def communicate(self):
            self.communicating.set()
            await asyncio.sleep(60)

        def kill(self):
            self.killed = True

        wait = AsyncMock(return_value=-9)

    process = SlowProcess()
    monkeypatch.setattr(
        asyncio,
        "create_subprocess_exec",
        AsyncMock(return_value=process),
    )
    task = asyncio.create_task(
        require_symbol("align_wav")(
            make_pcm_wav(),
            "Keep moving.",
            binary_path=Path("/opt/rhubarb/rhubarb"),
            timeout_seconds=30,
        )
    )
    await process.communicating.wait()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert process.killed is True
    process.wait.assert_awaited_once()


@pytest.mark.asyncio
async def test_align_wav_reports_missing_binary(monkeypatch):
    """Convert an unavailable executable into a typed fallback signal."""
    align_wav = require_symbol("align_wav")
    LipSyncUnavailable = require_symbol("LipSyncUnavailable")
    monkeypatch.setattr(
        asyncio,
        "create_subprocess_exec",
        AsyncMock(side_effect=FileNotFoundError),
    )

    with pytest.raises(LipSyncUnavailable):
        await align_wav(
            make_pcm_wav(),
            "Keep moving.",
            binary_path=Path("/missing/rhubarb"),
            timeout_seconds=1,
        )
