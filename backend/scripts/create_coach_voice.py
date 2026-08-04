"""Create the original Lianleme coach voice and save evaluation WAV files."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.core.config import settings
from app.services.ai.tts_service import (
    DesignedVoice,
    QwenVoiceDesignClient,
    SynthesizedSpeech,
)

COACH_VOICE_PROMPT = (
    "An original male coach voice in his late twenties with a bright, powerful tone. "
    "Use New York City English with an AAVE-influenced rhythm, cocky swagger, and "
    "playful sarcasm. Mix mild street slang with crisp, clear enunciation, like a "
    "confident Brooklyn trainer who can explain form and roast the listener at the "
    "same time. The voice must not resemble any real person, actor, celebrity, or "
    "known character."
)
PREVIEW_TEXT = (
    "Get your ass up, homie! You ready to work? "
    "Lock in, bro! I ain't hear them plates clankin'. Let's go!"
)
EVALUATION_TEXT = (
    "Ayy yo, what's good, bro? Chest up. Brace that core. "
    "This shit ain't gonna lift itself. Two more reps. "
    "Don't fold on me now."
)
WILD_COACH_TEXT = (
    "Yo yo yo! Get your ass up, homie! "
    "Lock in, bro! Move that weight! "
    "This shit ain't gonna lift itself. Two more reps! "
    "Don't fold on me now!"
)
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "generated" / "tts"


@dataclass(frozen=True)
class AudioArtifacts:
    """Identify the isolated local artifacts written for one designed voice."""

    voice_dir: Path
    manifest_path: Path
    preview_path: Path
    evaluation_path: Path


def _voice_output_dir(output_dir: Path, voice_id: str) -> Path:
    """Resolve a safe output directory from a DashScope voice identifier."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", voice_id):
        raise ValueError("Qwen voice ID contains unsupported path characters")
    return output_dir / voice_id


def _write_manifest(
    artifacts: AudioArtifacts,
    designed_voice: DesignedVoice,
    *,
    target_model: str,
    evaluation_request_id: str | None,
) -> None:
    """Persist the remote voice identity before any later network step can fail."""
    manifest = {
        "design_request_id": designed_voice.request_id,
        "evaluation_request_id": evaluation_request_id,
        "target_model": target_model,
        "voice_id": designed_voice.voice_id,
    }
    artifacts.manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def initialize_audio_artifacts(
    output_dir: Path,
    designed_voice: DesignedVoice,
    *,
    target_model: str,
) -> AudioArtifacts:
    """Save a new voice's preview and identity before evaluation synthesis."""
    voice_dir = _voice_output_dir(output_dir, designed_voice.voice_id)
    voice_dir.mkdir(parents=True, exist_ok=True)
    artifacts = AudioArtifacts(
        voice_dir=voice_dir,
        manifest_path=voice_dir / "voice.json",
        preview_path=voice_dir / "lianleme-coach-preview.wav",
        evaluation_path=voice_dir / "lianleme-coach-evaluation.wav",
    )
    artifacts.preview_path.write_bytes(designed_voice.preview_audio)
    _write_manifest(
        artifacts,
        designed_voice,
        target_model=target_model,
        evaluation_request_id=None,
    )
    return artifacts


def write_audio_artifacts(
    output_dir: Path,
    designed_voice: DesignedVoice,
    speech: SynthesizedSpeech,
    *,
    target_model: str,
) -> AudioArtifacts:
    """Complete one voice directory with evaluation audio and request metadata."""
    artifacts = initialize_audio_artifacts(
        output_dir,
        designed_voice,
        target_model=target_model,
    )
    artifacts.evaluation_path.write_bytes(speech.audio)
    _write_manifest(
        artifacts,
        designed_voice,
        target_model=target_model,
        evaluation_request_id=speech.request_id,
    )
    return artifacts


async def create_coach_voice(output_dir: Path = DEFAULT_OUTPUT_DIR) -> tuple[str, AudioArtifacts]:
    """Create one Qwen voice, synthesize evaluation copy, and save both WAV files."""
    api_key = settings.QWEN_AUDIO_API_KEY or settings.QWEN_API_KEY
    if not api_key:
        raise RuntimeError("Set QWEN_AUDIO_API_KEY or QWEN_API_KEY before creating a voice")

    timeout = httpx.Timeout(120.0, connect=15.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as http_client:
        client = QwenVoiceDesignClient(
            api_key=api_key,
            api_base=settings.QWEN_AUDIO_API_BASE,
            target_model=settings.QWEN_AUDIO_VOICE_DESIGN_MODEL,
            http_client=http_client,
        )
        designed_voice = await client.create_voice(
            voice_prompt=COACH_VOICE_PROMPT,
            preview_text=PREVIEW_TEXT,
            preferred_name="lianleme_coach",
        )
        artifacts: AudioArtifacts | None = None
        try:
            artifacts = initialize_audio_artifacts(
                output_dir,
                designed_voice,
                target_model=settings.QWEN_AUDIO_VOICE_DESIGN_MODEL,
            )
            speech = await client.synthesize(
                text=EVALUATION_TEXT,
                voice_id=designed_voice.voice_id,
            )
            artifacts = write_audio_artifacts(
                output_dir,
                designed_voice,
                speech,
                target_model=settings.QWEN_AUDIO_VOICE_DESIGN_MODEL,
            )
        except Exception as exc:
            recovery = (
                "local artifacts could not be initialized"
                if artifacts is None
                else f"metadata is saved at {artifacts.manifest_path}"
            )
            raise RuntimeError(
                f"Voice {designed_voice.voice_id} was created, but a later local or "
                f"synthesis step failed; {recovery}"
            ) from exc

    if artifacts is None:
        raise RuntimeError(f"Voice {designed_voice.voice_id} did not produce local artifacts")
    return designed_voice.voice_id, artifacts


async def synthesize_existing_coach(
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    text: str = WILD_COACH_TEXT,
) -> Path:
    """Synthesize wild coaching copy with the configured reusable voice."""
    api_key = settings.QWEN_AUDIO_API_KEY or settings.QWEN_API_KEY
    if not api_key:
        raise RuntimeError("Set QWEN_AUDIO_API_KEY or QWEN_API_KEY before synthesizing")
    voice_id = settings.QWEN_AUDIO_TTS_VOICE.strip()
    if not voice_id:
        raise RuntimeError("Set QWEN_AUDIO_TTS_VOICE before synthesizing an existing voice")
    if not text.strip():
        raise ValueError("Synthesis text must not be empty")

    timeout = httpx.Timeout(120.0, connect=15.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as http_client:
        client = QwenVoiceDesignClient(
            api_key=api_key,
            api_base=settings.QWEN_AUDIO_API_BASE,
            target_model=settings.QWEN_AUDIO_TTS_MODEL,
            http_client=http_client,
        )
        speech = await client.synthesize(text=text, voice_id=voice_id)

    voice_dir = _voice_output_dir(output_dir, voice_id)
    voice_dir.mkdir(parents=True, exist_ok=True)
    audio_path = voice_dir / "lianleme-coach-wild-preview.wav"
    audio_path.write_bytes(speech.audio)
    audio_path.with_suffix(".json").write_text(
        json.dumps(
            {
                "request_id": speech.request_id,
                "target_model": settings.QWEN_AUDIO_TTS_MODEL,
                "text": text,
                "voice_id": voice_id,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return audio_path


def build_parser() -> argparse.ArgumentParser:
    """Build an explicit CLI so inspection commands can never create a paid voice."""
    parser = argparse.ArgumentParser(
        description="Create or reuse the original Lianleme Qwen coach voice.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    create_parser = commands.add_parser(
        "create",
        help="create a new remote voice and local evaluation artifacts",
    )
    create_parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="directory that will contain one subdirectory per voice",
    )
    synthesize_parser = commands.add_parser(
        "synthesize",
        help="synthesize copy with the configured existing voice",
    )
    synthesize_parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="directory that contains the configured voice subdirectory",
    )
    synthesize_parser.add_argument(
        "--text",
        default=WILD_COACH_TEXT,
        help="coaching copy to synthesize",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """Parse an explicit command before running any network-backed operation."""
    args = build_parser().parse_args(argv)
    if args.command == "create":
        voice_id, artifacts = asyncio.run(create_coach_voice(args.output_dir))
        print(f"QWEN_AUDIO_TTS_VOICE={voice_id}")
        print(f"Preview: {artifacts.preview_path}")
        print(f"Evaluation: {artifacts.evaluation_path}")
        return
    if args.command == "synthesize":
        audio_path = asyncio.run(synthesize_existing_coach(args.output_dir, args.text))
        print(f"Synthesized: {audio_path}")
        return
    raise RuntimeError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
