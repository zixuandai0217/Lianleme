from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, StateGraph

from app.agent.tools.fitness_tools import nutrition_hint_tool, workout_template_tool


class CoachState(TypedDict, total=False):
    user_id: str
    session_id: str
    message: str
    intent: str
    safety_ok: bool
    response: str


def detect_intent(state: CoachState) -> CoachState:
    msg = state.get("message", "")
    if any(k in msg for k in ["计划", "plan"]):
        intent = "plan"
    elif any(k in msg for k in ["吃", "饮食", "diet"]):
        intent = "diet"
    else:
        intent = "workout"
    state["intent"] = intent
    return state


def safety_guard(state: CoachState) -> CoachState:
    message = state.get("message", "")
    risky = any(k in message for k in ["处方", "药", "诊断", "病"])
    state["safety_ok"] = not risky
    return state


def generate_response(state: CoachState) -> CoachState:
    if not state.get("safety_ok", True):
        state["response"] = "我可以提供健康管理建议，但不能提供医疗诊断或处方，请咨询专业医生。"
        return state

    intent = state.get("intent", "workout")
    if intent == "diet":
        hint = nutrition_hint_tool.invoke({"goal": state.get("message", "减脂")})
        state["response"] = f"AI搭子建议：{hint}"
    elif intent == "plan":
        tpl = workout_template_tool.invoke({"level": "beginner"})
        state["response"] = f"我为你生成了训练方向：{tpl}"
    else:
        state["response"] = "先做5分钟动态热身，然后进行主训练，结束后做拉伸。"
    return state


def persist_state(state: CoachState) -> CoachState:
    # Why: preserve deterministic final output point for API usage and replay.
    # Scope: all coach message executions in LangGraph pipeline.
    # Verify: graph invoke returns a state containing `response`.
    return state


def build_graph():
    graph = StateGraph(CoachState)
    graph.add_node("intent", detect_intent)
    graph.add_node("safety", safety_guard)
    graph.add_node("respond", generate_response)
    graph.add_node("persist", persist_state)

    graph.set_entry_point("intent")
    graph.add_edge("intent", "safety")
    graph.add_edge("safety", "respond")
    graph.add_edge("respond", "persist")
    graph.add_edge("persist", END)

    return graph.compile()


coach_graph = build_graph()
