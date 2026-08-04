# Qwen3-TTS Voice Design Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a reusable original male fitness-coach voice with `qwen3-tts-vd-2026-01-26` and generate verified WAV previews without depending on a human reference recording.

**Architecture:** Add a small async client around the two official DashScope REST endpoints: voice design and multimodal TTS generation. Keep the voice workflow separate from the existing coach chat route so the candidate can be reviewed before it becomes application behavior. An explicit CLI subcommand creates the voice, saves the returned preview and metadata in a voice-specific directory, synthesizes the evaluation lines, and prints the voice ID for secure `.env` storage.

**Tech Stack:** Python 3.11, httpx, Pydantic Settings, pytest, pytest-asyncio, DashScope Qwen3-TTS API

---

### Task 1: Define the Qwen Voice Design client contract

**Files:**
- Create: `backend/tests/test_qwen_tts.py`
- Create: `backend/app/services/ai/tts_service.py`

**Step 1: Write the failing tests**

Test that the client sends the documented voice-design payload, decodes the base64 WAV preview, sends the designed voice ID to the matching synthesis model, and downloads the returned audio URL. Cover malformed API responses with a readable exception.

**Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_qwen_tts.py -v`

Expected: FAIL because `app.services.ai.tts_service` does not exist.

**Step 3: Write the minimal implementation**

Implement `QwenVoiceDesignClient`, `DesignedVoice`, and `QwenTTSAPIError`. Inject an `httpx.AsyncClient` so tests use `MockTransport` at the external HTTP boundary.

**Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_qwen_tts.py -v`

Expected: all client tests pass.

### Task 2: Add configuration and a repeatable voice-generation command

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env.example`
- Create: `backend/scripts/create_coach_voice.py`
- Modify: `backend/tests/test_qwen_tts.py`

**Step 1: Write the failing CLI/configuration tests**

Test the default model, original-character prompt, evaluation text, and WAV output paths without making a network call.

**Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_qwen_tts.py -v`

Expected: FAIL because the script and TTS settings are not present.

**Step 3: Implement the command**

Add the existing `QWEN_AUDIO_*` variables to typed settings. Create a CLI that uses the configured Beijing API base, requires an explicit `create` command before making a paid API call, writes both preview and synthesized WAV files, and emits the voice ID without printing the API key.

**Step 4: Run focused and full tests**

Run: `cd backend && uv run pytest tests/test_qwen_tts.py -v && uv run pytest -q`

Expected: focused and backend regression suites pass.

### Task 3: Create and verify the first original coach voice

**Files:**
- Modify locally: `backend/.env`
- Generate locally: `backend/generated/tts/<voice-id>/*.wav`
- Generate locally: `backend/generated/tts/<voice-id>/voice.json`

**Step 1: Run the real voice-design command**

Run: `cd backend && uv run python scripts/create_coach_voice.py create`

Expected: the API returns a voice ID and two non-empty WAV files.

**Step 2: Save the selected model and voice ID**

Set `QWEN_AUDIO_TTS_MODEL=qwen3-tts-vd-2026-01-26` and store the returned voice ID in the ignored local `.env` file.

**Step 3: Verify the artifacts**

Run audio metadata inspection and a non-silence check, then execute Ruff and the full backend test suite. Review the diff for accidental secrets and unrelated changes.

No commits are planned because the current worktree contains pre-existing user changes that must remain ungrouped.

### Task 4: Reuse the selected voice for a wilder gym-bro style

**Files:**
- Modify: `backend/app/services/ai/coach_graph.py`
- Modify: `backend/scripts/create_coach_voice.py`
- Modify: `backend/tests/test_qwen_tts.py`
- Create: `backend/tests/test_coach_persona.py`

**Step 1: Write failing persona and synthesis tests**

Test that coach prompts use `bro` and `homie` naturally, reserve `shit` for high-energy
reactions, and keep the tone supportive rather than personally degrading. Test that an
explicit `synthesize` command reuses `QWEN_AUDIO_TTS_VOICE`, writes a WAV plus metadata,
and never calls voice design.

**Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_coach_persona.py tests/test_qwen_tts.py -q`

Expected: FAIL because the persona is still gentle and the existing-voice synthesis
workflow does not exist.

**Step 3: Implement the minimal behavior**

Update the shared coach prompt with short gym-bro phrasing and contextual slang. Add a
`synthesize` subcommand whose default copy includes `homie`, `bro`, and `shit`, uses the
configured voice ID, and saves an isolated local preview without creating a new voice.

**Step 4: Verify and generate one real preview**

Run focused tests, Ruff, Mypy, compileall, and the full backend suite. Then run:

`cd backend && uv run python scripts/create_coach_voice.py synthesize`

Expected: one non-empty WAV under the current voice directory; the configured voice ID
and previously created voice count remain unchanged.
