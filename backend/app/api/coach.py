"""AI 陪练路由：对话接口（流式 SSE + 普通 JSON）+ 历史记录"""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import ensure_current_user_matches, get_current_user
from app.models.chat_message import ChatMessageRecord
from app.models.user import User
from app.schemas.chat import (
    ChatHistoryResponse,
    ChatMessage,
    ChatMessageResponse,
    CoachResponse,
)
from app.services.ai.coach_graph import CoachGraph

router = APIRouter()


@router.post("/chat", response_model=CoachResponse)
async def chat(
    msg: ChatMessage,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """AI 教练流式对话接口（SSE 模式）"""
    ensure_current_user_matches(current_user, msg.user_id)
    graph = CoachGraph(user_id=msg.user_id, db=db)

    async def event_generator():
        async for chunk in graph.stream_chat(
            message=msg.message,
            context={
                "current_exercise": msg.current_exercise,
                "completed_sets": msg.completed_sets,
                "total_sets": msg.total_sets,
                "plan_id": msg.plan_id,
            },
        ):
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


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
