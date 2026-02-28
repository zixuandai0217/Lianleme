"""
AI 健康顾问路由
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from datetime import datetime
from typing import List, Optional
import uuid

from app.database import get_db
from app.models.user import User
from app.models.chat_message import ChatMessage
from app.schemas.chat import (
    ChatMessageRequest,
    ChatResponse,
    ChatMessageItem,
    ChatSessionResponse
)
from app.schemas.common import APIResponse
from app.api.deps import get_current_user
from app.core.ai_service import ai_service

router = APIRouter()


@router.post("/chat", response_model=ChatResponse, summary="AI 对话")
async def chat(
    request: ChatMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """与 AI 健康顾问进行对话"""
    # 获取历史对话（最近 10 轮）
    history_result = await db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.user_id == current_user.id,
            ChatMessage.session_id == request.session_id
        )
        .order_by(ChatMessage.created_at)
        .limit(10)
    )
    history_messages = history_result.scalars().all()

    # 转换为 API 格式
    history = [
        {"role": msg.role, "content": msg.content}
        for msg in history_messages
    ]

    # 获取今日上下文数据
    context = await get_user_today_context(current_user.id, db)

    # 调用 AI 服务
    reply = await ai_service.chat_consultant(
        message=request.message,
        history=history,
        context=context
    )

    # 保存用户消息
    user_msg = ChatMessage(
        user_id=current_user.id,
        session_id=request.session_id,
        role="user",
        content=request.message
    )
    db.add(user_msg)

    # 保存 AI 回复
    assistant_msg = ChatMessage(
        user_id=current_user.id,
        session_id=request.session_id,
        role="assistant",
        content=reply
    )
    db.add(assistant_msg)

    await db.commit()
    await db.refresh(assistant_msg)

    return ChatResponse(
        reply=reply,
        session_id=request.session_id,
        message_id=assistant_msg.id
    )


@router.get("/sessions", response_model=List[ChatSessionResponse], summary="获取会话列表")
async def get_chat_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取用户的聊天会话列表"""
    # 获取所有会话的最后一条消息
    result = await db.execute(
        select(
            ChatMessage.session_id,
            func.max(ChatMessage.created_at).label("last_message_time"),
            func.count(ChatMessage.id).label("message_count")
        )
        .where(ChatMessage.user_id == current_user.id)
        .group_by(ChatMessage.session_id)
        .order_by(desc("last_message_time"))
        .limit(20)
    )
    rows = result.all()

    sessions = []
    for row in rows:
        # 获取最后一条消息内容
        last_msg_result = await db.execute(
            select(ChatMessage.content)
            .where(
                ChatMessage.user_id == current_user.id,
                ChatMessage.session_id == row.session_id
            )
            .order_by(desc(ChatMessage.created_at))
            .limit(1)
        )
        last_msg = last_msg_result.scalar_one_or_none()

        sessions.append(ChatSessionResponse(
            session_id=row.session_id,
            last_message=last_msg or "",
            last_message_time=row.last_message_time,
            message_count=row.message_count
        ))

    return sessions


@router.get("/sessions/{session_id}", response_model=List[ChatMessageItem], summary="获取会话详情")
async def get_session_messages(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取指定会话的所有消息"""
    result = await db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.user_id == current_user.id,
            ChatMessage.session_id == session_id
        )
        .order_by(ChatMessage.created_at)
        .limit(50)
    )
    messages = result.scalars().all()

    return [ChatMessageItem.model_validate(msg) for msg in messages]


@router.delete("/sessions/{session_id}", response_model=APIResponse, summary="删除会话")
async def delete_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """删除指定会话的所有消息"""
    await db.execute(
        delete(ChatMessage)
        .where(
            ChatMessage.user_id == current_user.id,
            ChatMessage.session_id == session_id
        )
    )
    await db.commit()

    return APIResponse(message="会话已删除")


async def get_user_today_context(user_id: int, db: AsyncSession) -> dict:
    """获取用户今日数据上下文"""
    from app.models.diet_log import DietLog
    from app.models.workout_log import WorkoutLog
    from datetime import date

    today = date.today()

    # 今日摄入
    diet_result = await db.execute(
        select(func.sum(DietLog.total_calories))
        .where(DietLog.user_id == user_id, DietLog.log_date == today)
    )
    calories_in = diet_result.scalar_one_or_none() or 0

    # 今日消耗
    workout_result = await db.execute(
        select(func.sum(WorkoutLog.calories_burned))
        .where(WorkoutLog.user_id == user_id, WorkoutLog.workout_date == today)
    )
    exercise_calories = workout_result.scalar_one_or_none() or 0

    # 运动状态
    workout_count_result = await db.execute(
        select(func.count(WorkoutLog.id))
        .where(WorkoutLog.user_id == user_id, WorkoutLog.workout_date == today)
    )
    workout_count = workout_count_result.scalar_one_or_none() or 0

    return {
        "calories_in": calories_in,
        "calories_out": exercise_calories,
        "workout_status": "已完成" if workout_count > 0 else "未完成"
    }


# 需要导入 delete
from sqlalchemy import delete, func
