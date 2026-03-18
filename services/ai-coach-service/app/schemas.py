from pydantic import BaseModel


class CoachMessageRequest(BaseModel):
    user_id: str
    session_id: str
    message: str


class PlanRequest(BaseModel):
    user_id: str
    plan_type: str
    objective: str


class PlanResponse(BaseModel):
    plan_id: str
    plan_type: str
    summary: str
