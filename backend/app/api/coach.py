"""AI 陪练路由：对话接口（流式 SSE + 普通 JSON 双模式）"""
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.chat import ChatMessage, CoachResponse
from app.services.ai.coach_graph import CoachGraph

router = APIRouter()


@router.post("/chat", response_model=CoachResponse)
async def chat(msg: ChatMessage, db: AsyncSession = Depends(get_db)):
    """
    AI 教练普通对话接口（JSON 模式）
    适合快捷操作按钮触发（完成一组/换个动作等）
    """
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
async def chat_stream(msg: ChatMessage, db: AsyncSession = Depends(get_db)):
    """
    AI 教练流式对话接口（SSE 模式）
    适合用户自由输入对话，前端逐字打字效果
    """
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
