from datetime import datetime

from fastapi import APIRouter

from app.agent.graph import coach_graph
from app.schemas import CoachMessageRequest, PlanRequest, PlanResponse

router = APIRouter(prefix="/internal", tags=["internal"])


@router.post('/coach/message')
async def coach_message(payload: CoachMessageRequest):
    result = coach_graph.invoke(payload.model_dump())
    return {
        'session_id': payload.session_id,
        'reply': result.get('response', '今天也要坚持！'),
    }


@router.post('/plan/generate', response_model=PlanResponse)
async def plan_generate(payload: PlanRequest):
    result = coach_graph.invoke(
        {
            'user_id': payload.user_id,
            'session_id': 'plan-session',
            'message': f"请生成{payload.objective}的{payload.plan_type}计划",
        }
    )
    return PlanResponse(
        plan_id=f"plan_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        plan_type=payload.plan_type,
        summary=result.get('response', '已生成计划'),
    )


@router.post('/plan/regenerate', response_model=PlanResponse)
async def plan_regenerate(payload: PlanRequest):
    return await plan_generate(payload)
