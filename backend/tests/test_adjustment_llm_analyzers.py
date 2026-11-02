"""两路 LLM 分析器 + 降级（工单 25）的外部行为测试。

模型可用时两维返回结构化健康评分并进入合并；超时 / 限流 / 鉴权 / 输出不可解析
只让该维降级，其余维度与方向照常；无可用 Key 时一次模型调用都不发，响应侧
不出现凭据错误文案。Prompt 只允许聚合摘要（均值、趋势、计数、训练天数），
不发送用户标识、邮箱、昵称或逐日原始序列。

这里直接用 AdjustGraph 的公开出口断言五维与合并结果，用固定替身记录请求；
降级元数据到 08 结论 / 26 详情的投影由末尾的 schema 测试覆盖。
"""

from __future__ import annotations

import asyncio
import datetime
import json
import types

import pytest

from app.models.adjustment import PlanAdjustment
from app.models.adjustment_job import PlanAdjustmentJob
from app.schemas.adjustment import AdjustmentJobDetail, AdjustmentOutcomeResponse
from app.services.ai.adjust_analyzers import (
    DIMENSION_BODY_COMPOSITION,
    DIMENSION_COMPLETION,
    DIMENSION_INJURY_RISK,
    DIMENSION_ORDER,
)
from app.services.ai.adjust_graph import AdjustGraph
from app.services.ai.llm_adjust_analyzers import (
    DEGRADATION_AUTH,
    DEGRADATION_INSUFFICIENT_DATA,
    DEGRADATION_NO_KEY,
    DEGRADATION_OUTPUT_UNPARSEABLE,
    DEGRADATION_RATE_LIMIT,
    DEGRADATION_TIMEOUT,
    LlmAnalyzerContext,
    build_prompt,
)

TODAY = datetime.date.today()
DEGRADATION_NOTE = "本次未做深度分析"


def week_plan() -> dict:
    """一周计划的最小形状，足够让调整有落地对象。"""
    return {
        "weekly_plan": [
            {
                "day": day,
                "focus": "全身",
                "exercises": [
                    {
                        "name": "深蹲",
                        "sets": 3,
                        "reps": "12",
                        "weight_suggestion": "自重",
                        "tips": "挺胸收腹",
                        "rest_seconds": 60,
                    }
                ],
                "estimated_duration": 30,
                "is_rest_day": False,
            }
            for day in range(1, 8)
        ],
        "difficulty_factor": 1.0,
    }


def aggregate_summary() -> dict:
    """计划服务应产出的聚合摘要；刻意塞入敏感字段证明 Prompt 会白名单过滤。"""
    return {
        "goal": "减脂",
        "height_cm": 175.0,
        "weight_kg": 70.0,
        "age_band": "30-39",
        "weekly_completion_average": 0.8,
        "training": {"training_days": 4, "consecutive_training_days": 2},
        "weight": {
            "mean_kg": 69.8,
            "trend_direction": "down",
            "record_count": 5,
            "window_days": 30,
        },
        "rule_scores": {"completion": 9.0, "fatigue": 7.0, "sleep": 7.0},
        # 以下字段不属于聚合摘要，绝不能进入 Prompt。
        "email": "secret@example.com",
        "nickname": "秘密昵称",
        "user_id": 42,
        "weight_series": [69.0, 69.5, 70.0],
    }


class _ProviderHTTPError(Exception):
    """带 HTTP 状态码的供应商失败，用来驱动 llm_observability 的分类。"""

    def __init__(self, status_code: int):
        super().__init__("provider failure")
        self.status_code = status_code


def _structured(score: float, reason: str) -> str:
    return json.dumps(
        {"score": score, "reason": reason, "suggestion": "按计划推进并注意恢复"},
        ensure_ascii=False,
    )


class _ScriptedClient:
    """按维度返回脚本化结果的模型替身，并记录每次请求。"""

    def __init__(self, *, injury=None, body=None):
        self.injury = _structured(8, "伤病风险低") if injury is None else injury
        self.body = _structured(6, "体重趋势与目标一致") if body is None else body
        self.calls: list[dict] = []

    async def ainvoke(self, messages, **kwargs):
        prompt = messages[-1].content
        self.calls.append({"prompt": prompt, "temperature": kwargs.get("temperature")})
        scripted = self.injury if DIMENSION_INJURY_RISK in prompt else self.body
        if isinstance(scripted, BaseException):
            raise scripted
        if callable(scripted):
            return await scripted()
        return types.SimpleNamespace(content=scripted)


async def _run_graph(client, summary, *, unavailable_reason=None) -> dict:
    graph = AdjustGraph(
        user_id=7,
        llm_context=LlmAnalyzerContext(
            client=client,
            summary=summary,
            unavailable_reason=unavailable_reason,
        ),
    )
    return await graph.run(
        completion_rate=0.9,
        difficulty_rating=3,
        current_plan=week_plan(),
    )


def _by_name(state: dict) -> dict[str, dict]:
    return {entry["name"]: entry for entry in state["dimensions"]}


@pytest.mark.asyncio
async def test_model_outputs_enter_merge_with_two_temperature_zero_calls():
    """AC1/AC4：两维结构化输出进入合并；两维等权；调用恰好 2 次且温度为 0。"""
    client = _ScriptedClient()
    state = await _run_graph(client, aggregate_summary())

    dimensions = _by_name(state)
    injury = dimensions[DIMENSION_INJURY_RISK]
    body = dimensions[DIMENSION_BODY_COMPOSITION]
    assert injury["source"] == "llm"
    assert injury["degraded"] is False
    assert injury["score"] == 8
    assert injury["reason"] == "伤病风险低"
    assert body["source"] == "llm"
    assert body["degraded"] is False
    assert body["score"] == 6
    assert body["reason"] == "体重趋势与目标一致"

    # 两维成功时不再出现在降级清单里，深度分析标记保持干净。
    assert DIMENSION_INJURY_RISK not in state["merged"]["degraded_dimensions"]
    assert DIMENSION_BODY_COMPOSITION not in state["merged"]["degraded_dimensions"]
    assert state["merged"]["degradation_note"] is None

    # 等权：完成率 9 + 伤病 8 + 体成分 6（疲劳 / 睡眠缺省被剔除）→ 7.67。
    assert state["merged"]["overall_score"] == pytest.approx(7.67)
    assert state["adjustment_type"] == "increase"

    assert len(client.calls) == 2
    assert all(call["temperature"] == 0 for call in client.calls)
    assert [entry["name"] for entry in state["dimensions"]] == list(DIMENSION_ORDER)


def test_prompt_contains_only_aggregates_not_identity_or_raw_series():
    """AC5：Prompt 只有聚合摘要，敏感字段与逐日原始序列都被白名单挡掉。"""
    prompt = build_prompt(
        DIMENSION_INJURY_RISK,
        {"completion_rates": [0.111, 0.222], "fatigue_scores": [1, 2, 3]},
        aggregate_summary(),
    )

    assert "secret@example.com" not in prompt
    assert "秘密昵称" not in prompt
    assert "weight_series" not in prompt
    assert '"user_id"' not in prompt
    assert "0.111" not in prompt
    assert "0.222" not in prompt

    # 均值与计数可以出现，原始逐日值不可以。
    assert "completion_average" in prompt
    assert "weight_trend" in prompt
    assert "training_days" in prompt


@pytest.mark.parametrize(
    ("body_script", "expected_reason"),
    [
        (asyncio.TimeoutError(), DEGRADATION_TIMEOUT),
        (_ProviderHTTPError(429), DEGRADATION_RATE_LIMIT),
        (_ProviderHTTPError(401), DEGRADATION_AUTH),
        ("这不是 JSON", DEGRADATION_OUTPUT_UNPARSEABLE),
    ],
)
@pytest.mark.asyncio
async def test_each_failure_mode_degrades_only_that_dimension(body_script, expected_reason):
    """AC2：失败维降级为规则近似，另一维与合并方向不受影响。"""
    client = _ScriptedClient(body=body_script)
    state = await _run_graph(client, aggregate_summary())

    dimensions = _by_name(state)
    body = dimensions[DIMENSION_BODY_COMPOSITION]
    injury = dimensions[DIMENSION_INJURY_RISK]

    assert body["degraded"] is True
    assert body["source"] == "llm"
    assert body["data_completeness"] == "default"
    assert 0 <= body["score"] <= 10
    assert DEGRADATION_NOTE in body["reason"]
    assert state["merged"]["degraded_reasons"][DIMENSION_BODY_COMPOSITION] == expected_reason
    assert state["merged"]["degradation_note"] == DEGRADATION_NOTE

    # 另一维成功、完成率与方向都不受这一路失败影响。
    assert injury["degraded"] is False
    assert injury["score"] == 8
    assert dimensions[DIMENSION_COMPLETION]["score"] == 9
    assert state["adjustment_type"] == "increase"
    assert len(client.calls) <= 2


@pytest.mark.asyncio
async def test_wait_for_timeout_degrades_only_the_slow_dimension(monkeypatch):
    """超时预算真正生效：慢调用被取消，该维降级为 timeout，另一维照常。"""
    import app.services.ai.llm_adjust_analyzers as llm_module

    monkeypatch.setattr(llm_module, "LLM_ANALYZER_TIMEOUT_SECONDS", 0.01)

    async def _slow_response():
        await asyncio.sleep(0.2)
        return types.SimpleNamespace(content=_structured(6, "慢响应"))

    client = _ScriptedClient(body=_slow_response)
    state = await _run_graph(client, aggregate_summary())

    dimensions = _by_name(state)
    assert dimensions[DIMENSION_BODY_COMPOSITION]["degraded"] is True
    assert (
        state["merged"]["degraded_reasons"][DIMENSION_BODY_COMPOSITION]
        == DEGRADATION_TIMEOUT
    )
    assert dimensions[DIMENSION_INJURY_RISK]["degraded"] is False
    assert state["adjustment_type"] == "increase"


@pytest.mark.asyncio
async def test_no_available_key_skips_calls_and_never_exposes_credentials():
    """AC3/AC6：无 Key 时零调用、两维降级、响应无凭据错误码与配置引导文案。"""
    client = _ScriptedClient()
    state = await _run_graph(
        client,
        aggregate_summary(),
        unavailable_reason=DEGRADATION_NO_KEY,
    )

    assert client.calls == []
    dimensions = _by_name(state)
    for name in (DIMENSION_INJURY_RISK, DIMENSION_BODY_COMPOSITION):
        entry = dimensions[name]
        assert entry["degraded"] is True
        assert entry["data_completeness"] == "default"
        assert DEGRADATION_NOTE in entry["reason"]
        assert state["merged"]["degraded_reasons"][name] == DEGRADATION_NO_KEY

    merged = state["merged"]
    assert merged["degradation_note"] == DEGRADATION_NOTE
    assert set(merged["degraded_dimensions"]) >= {
        DIMENSION_INJURY_RISK,
        DIMENSION_BODY_COMPOSITION,
    }

    serialized = json.dumps(
        {"dimensions": state["dimensions"], "merged": merged},
        ensure_ascii=False,
    )
    for forbidden in ("API Key", "api key", "请配置", "401", "403"):
        assert forbidden not in serialized

    # 规则维度仍照常产出，方向照常决策。
    assert dimensions[DIMENSION_COMPLETION]["score"] == 9
    assert state["adjustment_type"] == "increase"


@pytest.mark.asyncio
async def test_missing_weight_history_skips_only_body_call():
    """体成分没有可用体重记录时不发第二次调用，只降级该维（成本上限的保守侧）。"""
    summary = aggregate_summary()
    summary["weight"] = {
        "mean_kg": None,
        "trend_direction": "insufficient",
        "record_count": 0,
        "window_days": 30,
    }
    client = _ScriptedClient()
    state = await _run_graph(client, summary)

    assert len(client.calls) == 1
    body = _by_name(state)[DIMENSION_BODY_COMPOSITION]
    assert body["degraded"] is True
    assert state["merged"]["degraded_reasons"][DIMENSION_BODY_COMPOSITION] == (
        DEGRADATION_INSUFFICIENT_DATA
    )
    assert state["merged"]["degradation_note"] == DEGRADATION_NOTE


def test_degradation_metadata_projects_into_outcome_and_job_detail():
    """AC6：08 结论与 26 详情都能读到降级维度、原因分类与「本次未做深度分析」。"""
    llm_dimensions = (DIMENSION_INJURY_RISK, DIMENSION_BODY_COMPOSITION)
    dimensions = [
        {
            "name": name,
            "score": 5.0,
            "reason": f"{name} 理由",
            "suggestion": "建议",
            "source": "llm" if name in llm_dimensions else "rule",
            "degraded": name in llm_dimensions,
            "data_completeness": "default" if name in llm_dimensions else "full",
        }
        for name in DIMENSION_ORDER
    ]
    merged = {
        "overall_score": 5.0,
        "dimension_scores": {entry["name"]: entry["score"] for entry in dimensions},
        "red_flags": [],
        "top_reasons": ["完成率理由"],
        "degraded_dimensions": [DIMENSION_INJURY_RISK, DIMENSION_BODY_COMPOSITION],
        "excluded_dimensions": [DIMENSION_INJURY_RISK, DIMENSION_BODY_COMPOSITION],
        "completeness": "partial",
        "degraded_reasons": {
            DIMENSION_INJURY_RISK: DEGRADATION_TIMEOUT,
            DIMENSION_BODY_COMPOSITION: DEGRADATION_OUTPUT_UNPARSEABLE,
        },
        "degradation_note": DEGRADATION_NOTE,
    }
    now = datetime.datetime.now(datetime.timezone.utc)
    record = PlanAdjustment(
        id="adj_test",
        user_id=1,
        plan_id=1,
        direction="keep",
        reason="整体健康分 5.0",
        completion_rate=0.9,
        overall_score=5.0,
        delta_percent=0.0,
        dimensions=dimensions,
        merged=merged,
        created_at=now,
    )
    job = PlanAdjustmentJob(
        job_id="job_test",
        user_id=1,
        status="applied",
        adjustment_id=record.id,
        created_at=now,
        updated_at=now,
        landed_at=now,
        decision={"direction": "keep", "delta_percent": 0.0},
    )

    outcome = AdjustmentOutcomeResponse.from_record(record)
    assert outcome.merged is not None
    assert outcome.merged.degradation_note == DEGRADATION_NOTE
    assert outcome.merged.degraded_reasons[DIMENSION_INJURY_RISK] == DEGRADATION_TIMEOUT

    detail = AdjustmentJobDetail.from_job(job, record)
    assert detail.merged is not None
    assert detail.merged.degradation_note == DEGRADATION_NOTE
    assert (
        detail.merged.degraded_reasons[DIMENSION_BODY_COMPOSITION]
        == DEGRADATION_OUTPUT_UNPARSEABLE
    )
