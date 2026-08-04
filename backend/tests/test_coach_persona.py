"""Behavior tests for the high-energy gym-bro coach persona."""

from app.services.ai.coach_graph import CoachGraph


def test_coach_prompt_uses_contextual_gym_bro_slang():
    """Keep the coach wild and supportive without repeating profanity every line."""
    graph = CoachGraph(user_id=1)

    prompt = graph._build_base_prompt(
        {
            "current_exercise": "bench press",
            "completed_sets": 2,
            "total_sets": 4,
        }
    )

    assert "bro" in prompt
    assert "homie" in prompt
    assert "shit" in prompt
    assert "不要每句话" in prompt
    assert "不攻击" in prompt
    assert "bench press" in prompt
