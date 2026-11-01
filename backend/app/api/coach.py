"""AI 陪练路由：对话接口（流式 SSE + 普通 JSON）+ 历史记录 + TTS"""
import base64
import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.observability import mark_stream_failed
from app.core.security import (
    ensure_current_user_matches,
    get_current_user,
    require_current_user_api_key,
)
from app.models.chat_message import ChatMessageRecord
from app.models.user import User
from app.schemas.chat import (
    ChatHistoryResponse,
    ChatMessage,
    ChatMessageResponse,
    CoachAnimatedTTSResponse,
    CoachDoneEvent,
    CoachErrorCode,
    CoachErrorEvent,
    CoachFinishReason,
    CoachMessageChunkEvent,
    CoachMouthCue,
    CoachResponse,
    CoachTTSRequest,
    CoachTTSStatusResponse,
    CoachTurnStartedEvent,
    sse_frame,
)
from app.services.ai import tts_runtime
from app.services.ai.coach_graph import (
    COACH_FALLBACK_REPLY,
    CoachGraph,
    CoachTextCleaner,
)
from app.services.ai.tts_service import QwenTTSAPIError
from app.services.user.api_key_service import ApiKeyService

logger = logging.getLogger(__name__)
router = APIRouter()


def _system_qwen_tts_key() -> str | None:
    """Return the server-managed Qwen key for coach voice when opt-in fallback is enabled.

    Never returns an OpenAI key: coach voice is Qwen-only.
    """
    if not settings.ALLOW_SYSTEM_LLM_FALLBACK:
        return None
    return (settings.QWEN_AUDIO_API_KEY or settings.QWEN_API_KEY or "").strip() or None


async def _get_user_qwen_key(db: AsyncSession, user_id: int) -> str | None:
    """Return the user's Qwen key, else the system Qwen key when fallback is enabled."""
    user_key = await ApiKeyService(db).get_decrypted_key(user_id)
    if user_key is not None and user_key[0] == "qwen":
        return user_key[1]
    return _system_qwen_tts_key()


async def _require_user_qwen_key(db: AsyncSession, user_id: int) -> str:
    """Require a Qwen key for the Qwen-only coach voice runtime."""
    api_key = await _get_user_qwen_key(db, user_id)
    if api_key is None:
        raise HTTPException(
            status_code=409,
            detail="数字教练语音目前需要配置通义千问 API Key",
        )
    return api_key


# 流中失败的稳定错误码 → 用户可读文案（错误绝不伪装成正文增量帧）
_COACH_ERROR_MESSAGES: dict[str, str] = {
    "provider_unavailable": "教练的模型通道没连上，先检查一下你的 API Key 配置。",
    "rate_limited": "这会儿请求太多了，缓一下再来。",
    "upstream_timeout": "模型那边超时了，再试一次。",
    "internal": "AI 服务暂时不可用，稍后再试。",
}

_COACH_ERROR_HINTS: tuple[tuple[tuple[str, ...], CoachErrorCode], ...] = (
    (("rate limit", "ratelimit", "429", "quota", "too many requests"), "rate_limited"),
    (("timeout", "timed out", "readtimeout"), "upstream_timeout"),
    (
        ("auth", "unauthorized", "invalid api", "api key", "apikey", "401", "403"),
        "provider_unavailable",
    ),
)


def _coach_error_code(exc: Exception) -> CoachErrorCode:
    """Map an upstream failure to one stable, user-facing error code."""
    description = f"{type(exc).__name__} {exc}".lower()
    for hints, code in _COACH_ERROR_HINTS:
        if any(hint in description for hint in hints):
            return code
    return "internal"


def _coach_error_event(exc: Exception) -> CoachErrorEvent:
    """Build the error frame for an upstream failure without leaking its message."""
    code = _coach_error_code(exc)
    return CoachErrorEvent(code=code, message=_COACH_ERROR_MESSAGES[code])


@router.post("/chat", response_model=CoachResponse)
async def chat(
    msg: ChatMessage,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_current_user_api_key),
):
    """AI 教练普通对话接口（JSON 模式）"""
    ensure_current_user_matches(current_user, msg.user_id)
    graph = CoachGraph(user_id=msg.user_id, db=db)
    result = await graph.chat(
        message=msg.message,
        context={
            "current_exercise": msg.current_exercise,
            "completed_sets": msg.completed_sets,
            "total_sets": msg.total_sets,
            "plan_id": msg.plan_id,
        },
    )
    return result


@router.post("/chat/stream")
async def chat_stream(
    msg: ChatMessage,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_current_user_api_key),
):
    """AI 教练流式对话接口（SSE 事件流）

    每帧是单行 JSON：首帧 turn_started、正文增量帧 message_chunk、末帧 done。
    模型原文先过清洗环节，只有清洗后的正文进入增量帧与被持久化的内容；
    失败先发 error 帧（稳定错误码 + 可读文案），再以 done(error) 收尾。
    """
    ensure_current_user_matches(current_user, msg.user_id)
    graph = CoachGraph(user_id=msg.user_id, db=db)
    context = {
        "current_exercise": msg.current_exercise,
        "completed_sets": msg.completed_sets,
        "total_sets": msg.total_sets,
        "plan_id": msg.plan_id,
    }

    async def event_generator():
        """Emit the typed coach event stream for exactly one turn."""
        yield sse_frame(
            CoachTurnStartedEvent(turn_id=uuid4().hex, message_id=uuid4().hex)
        )
        finish_reason: CoachFinishReason = "complete"
        cleaner = CoachTextCleaner()
        visible: list[str] = []

        def frame_for(text: str) -> str:
            """Record released正文 and turn it into one delta frame."""
            visible.append(text)
            return sse_frame(CoachMessageChunkEvent(text=text))

        try:
            async for delta in graph.stream_chat(message=msg.message, context=context):
                cleaned = cleaner.feed(delta)
                if cleaned:
                    yield frame_for(cleaned)

            tail = cleaner.flush()
            if tail:
                yield frame_for(tail)

            reply = "".join(visible).strip()
            if not reply:
                reply = COACH_FALLBACK_REPLY
                yield frame_for(reply)

            await graph.save_turn(msg.message, reply)
        except Exception as exc:
            logger.exception("AI 陪练流式响应失败: user_id=%s", msg.user_id)
            finish_reason = "error"
            error_event = _coach_error_event(exc)
            # 路由把上游失败收敛成 error 帧，但结束事件仍必须是带错误类别的告警事件
            mark_stream_failed(
                request.scope,
                error_code=error_event.code,
                error_class=type(exc).__name__,
            )
            yield sse_frame(error_event)
        yield sse_frame(CoachDoneEvent(finish_reason=finish_reason))

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/tts/status", response_model=CoachTTSStatusResponse)
async def coach_tts_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Report whether the current user's Qwen key can use coach speech."""
    api_key = await _get_user_qwen_key(db, current_user.id)
    voice_id = settings.QWEN_BYOK_TTS_VOICE.strip()
    return CoachTTSStatusResponse(
        available=bool(api_key) and tts_runtime.tts_is_configured(
            api_key,
            voice_id=voice_id,
        ),
        lip_sync_available=tts_runtime.lip_sync_is_configured(),
    )


@router.post("/tts")
async def coach_tts(
    req: CoachTTSRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_current_user_api_key),
):
    """Synthesize coach speech as raw WAV audio for the authenticated user."""
    api_key = await _require_user_qwen_key(db, current_user.id)
    voice_id = settings.QWEN_BYOK_TTS_VOICE.strip()
    if not tts_runtime.tts_is_configured(api_key, voice_id=voice_id):
        raise HTTPException(status_code=503, detail="教练语音未配置")

    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="朗读文本不能为空")

    try:
        audio = await tts_runtime.synthesize_speech(
            text,
            api_key=api_key,
            voice_id=voice_id,
        )
    except QwenTTSAPIError:
        logger.exception("Coach TTS provider failure")
        raise HTTPException(status_code=502, detail="语音合成暂时不可用") from None
    except Exception:
        logger.exception("Coach TTS unexpected failure")
        raise HTTPException(status_code=502, detail="语音合成暂时不可用") from None

    return Response(content=audio, media_type="audio/wav")


@router.post("/tts/animated", response_model=CoachAnimatedTTSResponse)
async def coach_tts_animated(
    req: CoachTTSRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_current_user_api_key),
):
    """Synthesize authenticated coach audio and return synchronized mouth cues."""
    api_key = await _require_user_qwen_key(db, current_user.id)
    voice_id = settings.QWEN_BYOK_TTS_VOICE.strip()
    if not tts_runtime.tts_is_configured(api_key, voice_id=voice_id):
        raise HTTPException(status_code=503, detail="教练语音未配置")

    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="朗读文本不能为空")

    try:
        speech = await tts_runtime.synthesize_animated_speech(
            text,
            api_key=api_key,
            voice_id=voice_id,
        )
    except QwenTTSAPIError:
        logger.exception("Coach animated TTS provider failure")
        raise HTTPException(status_code=502, detail="语音合成暂时不可用") from None
    except Exception:
        logger.exception("Coach animated TTS unexpected failure")
        raise HTTPException(status_code=502, detail="语音合成暂时不可用") from None

    return CoachAnimatedTTSResponse(
        audio_base64=base64.b64encode(speech.audio).decode("ascii"),
        duration_seconds=speech.duration_seconds,
        mouth_cues=[
            CoachMouthCue(start=cue.start, end=cue.end, value=cue.value)
            for cue in speech.mouth_cues
        ],
        alignment=speech.alignment,
    )


@router.get("/{user_id}/history", response_model=ChatHistoryResponse)
async def get_chat_history(
    user_id: int,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取用户对话历史（按时间正序，最近 N 条）"""
    ensure_current_user_matches(current_user, user_id)
    count_result = await db.execute(
        select(func.count()).select_from(ChatMessageRecord)
        .where(ChatMessageRecord.user_id == user_id)
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        select(ChatMessageRecord)
        .where(ChatMessageRecord.user_id == user_id)
        .order_by(desc(ChatMessageRecord.created_at))
        .limit(limit)
    )
    records = list(reversed(result.scalars().all()))

    items = [
        ChatMessageResponse(
            id=r.id,
            role=r.role,
            content=r.content,
            created_at=r.created_at,
        )
        for r in records
    ]
    return ChatHistoryResponse(messages=items, total=total)
