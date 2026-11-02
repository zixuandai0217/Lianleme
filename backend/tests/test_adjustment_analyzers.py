"""Analyzer 抽象 + 三路规则 + Merge Node（工单 24）的外部行为测试。

最低 seam 只断言用户可观测的事实：一次评估产出五维小结、合并分与方向；缺数据走
缺省而不报错；单维度失败只降级自己；整趟评估不调用任何模型。

规则型分析器的评分映射是纯函数、边界值密集（0.85/0.7、疲劳 3、睡眠 7h/6h），
用表驱动单测逐条断言；路由层复用打卡 → 调整的既有骨架，只把 LLM 工厂换成计数的
替身，证明零模型调用。
"""

import datetime
import json
import logging
import types
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.services.ai.adjust_analyzers as analyzers_module
import app.services.ai.adjust_graph as adjust_graph_module
import app.services.plan.plan_service as plan_service_module
import app.services.workout.workout_service as workout_service_module
from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.plan import TrainingPlan
from app.models.user import User
from app.models.weight import WeightRecord
from app.services.ai.adjust_analyzers import (
    DIMENSION_BODY_COMPOSITION,
    DIMENSION_COMPLETION,
    DIMENSION_FATIGUE,
    DIMENSION_INJURY_RISK,
    DIMENSION_ORDER,
    DIMENSION_SLEEP,
    AnalyzerResult,
    analyze_completion,
    analyze_fatigue,
    analyze_sleep,
    evaluate_dimensions,
    run_analyzer,
)
from app.services.ai.adjust_merge import (
    decide_direction,
    delta_percent_for,
    merge_results,
)
from app.services.ai.llm_adjust_analyzers import (
    DEGRADATION_NO_KEY,
    DEGRADATION_NOTE,
)

TODAY = datetime.date.today()


def week_plan() -> list[dict]:
    """每天一个动作的简单计划，足够让调整有对象。"""
    return [
        {
            "day": weekday,
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
        for weekday in range(1, 8)
    ]


# --------------------------------------------------------------------------
# 纯函数：规则型分析器的阈值表（ADR-0003）
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rate", "expected"),
    [
        (1.0, 9),
        (0.85, 9),
        (0.84, 7),
        (0.7, 7),
        (0.69, 5),
        (0.0, 5),
    ],
)
def test_completion_thresholds(rate: float, expected: int):
    """AC1：完成率 ≥0.85→9、0.7-0.85→7、<0.7→5，边界值逐条断言。"""
    result = analyze_completion({"completion_rates": [rate]})
    assert result.name == DIMENSION_COMPLETION
    assert result.source == "rule"
    assert result.degraded is False
    assert result.data_completeness == "full"
    assert result.score == expected


@pytest.mark.parametrize(
    ("fatigue", "expected"),
    [(1, 10), (2, 9), (3, 7), (4, 5), (5, 3)],
)
def test_fatigue_thresholds(fatigue: int, expected: int):
    """AC1：疲劳 1-2→9-10、3→7、4-5→3-5。"""
    result = analyze_fatigue({"fatigue_scores": [fatigue]})
    assert result.name == DIMENSION_FATIGUE
    assert result.source == "rule"
    assert result.score == expected


@pytest.mark.parametrize(
    ("hours", "quality", "expected"),
    [
        (7.5, 5, 9),
        (7.0, 4, 9),
        (6.5, 4, 7),
        (6.0, 3, 7),
        (5.9, 5, 5),
        (8.0, 2, 7),
    ],
)
def test_sleep_thresholds(hours: float, quality: int, expected: int):
    """AC1：睡眠 ≥7h 且质量 ≥4→9、6-7h→7、<6h→5；睡够但质量差按 7 分。"""
    result = analyze_sleep({"sleep_hours": hours, "sleep_quality": quality})
    assert result.name == DIMENSION_SLEEP
    assert result.source == "rule"
    assert result.score == expected


def test_missing_fatigue_uses_documented_default():
    """AC3：无疲劳数据按缺省 3 分参与，并标注「数据为缺省」。"""
    result = analyze_fatigue({"fatigue_scores": []})
    assert result.score == 7  # 缺省值 3 走阈值表
    assert result.data_completeness == "default"
    assert result.degraded is True
    assert "数据为缺省" in result.reason


def test_missing_sleep_uses_documented_default():
    """AC3：无睡眠数据按缺省 3 分 / 7 小时参与，并标注「数据为缺省」。"""
    result = analyze_sleep({"sleep_hours": None, "sleep_quality": None})
    assert result.score == 7
    assert result.data_completeness == "default"
    assert result.degraded is True
    assert "数据为缺省" in result.reason
    assert "7" in result.reason


def test_sleep_with_only_hours_is_partial_not_default():
    """有时长无质量时按缺省质量补齐，但标记为 partial（不是完全缺省）。"""
    result = analyze_sleep({"sleep_hours": 7.5, "sleep_quality": None})
    assert result.score == 7
    assert result.data_completeness == "partial"
    assert result.degraded is False


def test_completion_without_rates_is_default():
    """没有完成率数据时不报错，按缺省处理并从合并中剔除。"""
    result = analyze_completion({"completion_rates": []})
    assert result.data_completeness == "default"
    assert result.degraded is True
    assert "数据为缺省" in result.reason


def test_invalid_input_degrades_only_that_dimension():
    """AC4：一维输入非法时只有它降级，其余四维与固定顺序不受影响。"""
    results = evaluate_dimensions(
        {"completion_rates": [0.9], "fatigue_scores": [99], "sleep_hours": None}
    )
    assert [result.name for result in results] == list(DIMENSION_ORDER)
    by_name = {result.name: result for result in results}

    assert by_name[DIMENSION_FATIGUE].degraded is True
    assert by_name[DIMENSION_FATIGUE].data_completeness == "default"

    assert by_name[DIMENSION_COMPLETION].score == 9
    assert by_name[DIMENSION_COMPLETION].degraded is False
    for name in (DIMENSION_INJURY_RISK, DIMENSION_SLEEP, DIMENSION_BODY_COMPOSITION):
        assert by_name[name].name == name


def test_llm_dimensions_are_not_evaluated_placeholders():
    """AC1/AC5：两路模型维度只做「未评估」占位，不发起模型调用。"""
    results = evaluate_dimensions({"completion_rates": [0.9]})
    by_name = {result.name: result for result in results}
    for name in (DIMENSION_INJURY_RISK, DIMENSION_BODY_COMPOSITION):
        placeholder = by_name[name]
        assert placeholder.source == "llm"
        assert placeholder.degraded is True
        assert placeholder.data_completeness == "default"
        assert "未评估" in placeholder.reason


def test_dimension_entry_shape_is_uniform():
    """AC1：五个条目形状一致，字段齐全且类型符合契约。"""
    entries = [result.to_dict() for result in evaluate_dimensions({"completion_rates": [0.9]})]
    assert len(entries) == 5
    for entry in entries:
        assert set(entry) == {
            "name",
            "score",
            "reason",
            "suggestion",
            "source",
            "degraded",
            "data_completeness",
        }
        assert entry["source"] in {"rule", "llm"}
        assert entry["data_completeness"] in {"full", "partial", "default"}
        assert isinstance(entry["degraded"], bool)
        assert 0 <= entry["score"] <= 10


# --------------------------------------------------------------------------
# 纯函数：Merge Node
# --------------------------------------------------------------------------


def _result(
    name: str,
    score: float,
    *,
    completeness: str = "full",
    degraded: bool = False,
    reason: str = "默认理由",
) -> AnalyzerResult:
    return AnalyzerResult(
        name=name,
        score=score,
        reason=reason,
        suggestion="默认建议",
        source="rule",
        degraded=degraded,
        data_completeness=completeness,
    )


def test_merge_is_equal_weight_average_excluding_defaults():
    """AC2：等权平均，缺省维度不计入平均并在剔除清单里列出。"""
    dimensions = [
        _result(DIMENSION_COMPLETION, 9),
        _result(DIMENSION_FATIGUE, 7, completeness="default", degraded=True),
        _result(DIMENSION_INJURY_RISK, 5, completeness="default", degraded=True),
        _result(DIMENSION_SLEEP, 8),
        _result(DIMENSION_BODY_COMPOSITION, 5, completeness="default", degraded=True),
    ]
    merged = merge_results(dimensions)

    assert merged.overall_score == pytest.approx(8.5)
    assert merged.excluded_dimensions == [
        DIMENSION_FATIGUE,
        DIMENSION_INJURY_RISK,
        DIMENSION_BODY_COMPOSITION,
    ]
    assert merged.degraded_dimensions == [
        DIMENSION_FATIGUE,
        DIMENSION_INJURY_RISK,
        DIMENSION_BODY_COMPOSITION,
    ]
    assert merged.completeness == "partial"
    assert merged.dimension_scores[DIMENSION_COMPLETION] == 9
    assert merged.dimension_scores[DIMENSION_FATIGUE] == 7


def test_merge_all_default_is_conservative_keep():
    """全维缺省时不编造合并分，方向落到保守的 keep。"""
    dimensions = [
        _result(name, 5, completeness="default", degraded=True)
        for name in DIMENSION_ORDER
    ]
    merged = merge_results(dimensions)
    assert merged.overall_score == 0.0
    assert merged.completeness == "default"
    assert merged.top_reasons == []
    assert decide_direction(merged.overall_score, 0.9, participating=False) == "keep"


def test_merge_top_reasons_prefer_red_flag_then_extremes():
    """AC2：top_reasons 优先红标志关联维度，再取极端分数，最多 3 条。"""
    dimensions = [
        _result(DIMENSION_COMPLETION, 9, reason="完成率理由"),
        _result(DIMENSION_FATIGUE, 2, reason="疲劳理由"),
        _result(DIMENSION_INJURY_RISK, 2, reason="伤病理由"),
        _result(DIMENSION_SLEEP, 9, reason="睡眠理由"),
        _result(DIMENSION_BODY_COMPOSITION, 6, reason="体成分理由"),
    ]
    merged = merge_results(dimensions)

    assert [flag["code"] for flag in merged.red_flags] == [
        "injury_risk_high",
        "fatigue_high",
    ]
    assert merged.top_reasons[0] == "伤病理由"
    assert len(merged.top_reasons) <= 3
    assert "疲劳理由" in merged.top_reasons


def test_merge_injury_score_above_three_is_not_a_red_flag():
    """伤病健康评分 > 3 不点亮红标志（红标志只做中断旁路，不参与平均分）。"""
    dimensions = [_result(DIMENSION_INJURY_RISK, 4, reason="伤病理由")]
    merged = merge_results(dimensions)
    assert merged.red_flags == []


def test_merge_flags_low_completion():
    """红标志：完成率过低在当前数据下即可判定（无需历史）。"""
    dimensions = [_result(DIMENSION_COMPLETION, 5)]
    merged = merge_results(dimensions, completion_rate=0.4)
    assert [flag["code"] for flag in merged.red_flags] == ["completion_low"]
    assert "40%" in merged.red_flags[0]["evidence"]


def test_merge_flags_high_fatigue():
    """红标志：疲劳健康评分过低同样可判定。"""
    dimensions = [
        _result(DIMENSION_COMPLETION, 9),
        _result(DIMENSION_FATIGUE, 5, reason="疲劳理由"),
    ]
    merged = merge_results(dimensions, completion_rate=0.9)
    assert [flag["code"] for flag in merged.red_flags] == ["fatigue_high"]


@pytest.mark.parametrize(
    ("score", "rate", "expected"),
    [
        (7.6, 0.6, "increase"),
        (7.5, 0.6, "increase"),
        (7.4, 0.6, "keep"),
        (5.0, 0.6, "keep"),
        (4.9, 0.6, "decrease"),
        # 合并分与完成率极值冲突时取更保守的一方。
        (7.6, 0.8, "increase"),
        (7.4, 0.8, "keep"),
        (7.4, 0.49, "decrease"),
        (4.9, 0.6, "decrease"),
        (5.0, 0.49, "decrease"),
    ],
)
def test_direction_mapping_and_completion_conflict_rule(score: float, rate: float, expected: str):
    """AC2：≥7.5 加量、5.0-7.5 保持、<5.0 减量；与完成率极值冲突取保守方。"""
    assert decide_direction(score, rate) == expected


def test_delta_percent_follows_the_declared_range():
    """方向对应的幅度沿用现状量级：加量 10-15%、减量 15-20%。"""
    assert delta_percent_for("increase") == pytest.approx(12.0)
    assert delta_percent_for("decrease") == pytest.approx(18.0)
    assert delta_percent_for("keep") == pytest.approx(0.0)


def test_run_analyzer_never_raises_for_bad_dimension():
    """单路异常必须被该路自己吞掉，绝不冒泡到 Merge 之前。"""
    broken = {"completion_rates": ["不是数字"]}
    result = run_analyzer(DIMENSION_COMPLETION, broken)
    assert result.degraded is True
    assert result.data_completeness == "default"
    assert result.score >= 0


# --------------------------------------------------------------------------
# 路由层：打卡 → 五维评估 → 结论可读
# --------------------------------------------------------------------------


class _OfflineLLM:
    """打卡反馈与模型维度的离线替身：绝不联网。

    模型维度拿到的是非 JSON 文本，因此两维都会走「输出不可解析」降级，
    保持工单 24 既有测试对「无深度分析」的断言。
    """

    async def ainvoke(self, messages, **kwargs):
        return types.SimpleNamespace(content="离线替身反馈：注意补水与休息。")


@pytest_asyncio.fixture
async def session_factory(tmp_path: Path):
    db_path = tmp_path / "adjustment-analyzers.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield factory

    await engine.dispose()


@pytest_asyncio.fixture
async def users(session_factory):
    async with session_factory() as session:
        owner = User(openid="analyzer-owner", nickname="Owner")
        other = User(openid="analyzer-other", nickname="Other")
        session.add_all([owner, other])
        await session.commit()
        await session.refresh(owner)
        await session.refresh(other)
        return {"owner": owner, "other": other}


@pytest_asyncio.fixture
async def active_plan(session_factory, users):
    async with session_factory() as session:
        plan = TrainingPlan(
            user_id=users["owner"].id,
            week_start=TODAY,
            weekly_plan=week_plan(),
            difficulty_factor=1.0,
            status="active",
        )
        session.add(plan)
        await session.commit()
        await session.refresh(plan)
        return plan


@pytest_asyncio.fixture
async def client(session_factory):
    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as async_client:
        yield async_client
    app.dependency_overrides.clear()


@pytest.fixture
def background_tasks(monkeypatch, session_factory):
    """捕获打卡后调度的调整协程，让测试可以确定性地执行它。"""
    captured: list = []

    def _capture(coroutine):
        captured.append(coroutine)
        return types.SimpleNamespace(cancel=lambda: None)

    monkeypatch.setattr(
        workout_service_module, "asyncio", types.SimpleNamespace(create_task=_capture)
    )
    monkeypatch.setattr(workout_service_module, "AsyncSessionLocal", session_factory)
    return captured


@pytest.fixture(autouse=True)
def offline_feedback_llm(monkeypatch):
    """打卡反馈与模型维度都走离线替身，测试绝不联网。"""

    async def fake_get_client(self, *args, **kwargs):
        return _OfflineLLM()

    monkeypatch.setattr(
        plan_service_module.LLMClientFactory, "get_client", fake_get_client
    )


@pytest.fixture
def graph_factory_calls(monkeypatch):
    """计数 AdjustGraph 自行解析客户端的次数：运行上下文应由 PlanService 注入。"""
    calls: list[object] = []

    class _StandIn:
        def __init__(self, db=None):
            self.db = db

        async def get_client(self, *args, **kwargs):
            calls.append(args or kwargs)
            raise AssertionError("Graph 不应自行解析模型客户端")

    monkeypatch.setattr(adjust_graph_module, "LLMClientFactory", _StandIn)
    return calls


@pytest.fixture(autouse=True)
def capture_logs(caplog):
    caplog.set_level(logging.INFO)
    return caplog


def _auth(user_id: int) -> dict[str, str]:
    token = jwt.encode({"sub": str(user_id)}, settings.SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


async def check_in(client, user_id: int, *, completed: int, total: int, difficulty=None):
    """提交一次打卡；返回响应，由调用方断言状态码。"""
    payload = {
        "user_id": user_id,
        "workout_date": TODAY.isoformat(),
        "total_sets": total,
        "completed_sets": completed,
        "duration_minutes": 30,
    }
    if difficulty is not None:
        payload["difficulty_rating"] = difficulty
    return await client.post(
        "/api/workout/complete", json=payload, headers=_auth(user_id)
    )


async def run_adjustment(client, user_id: int, background_tasks, **kwargs):
    """打卡并执行被捕获的调整协程。"""
    response = await check_in(client, user_id, **kwargs)
    assert response.status_code == 200
    assert background_tasks, "打卡后应调度一次调整"
    await background_tasks[-1]
    return response


async def latest_outcome(client, user_id: int) -> dict:
    response = await client.get(
        f"/api/plan/{user_id}/adjustments/latest", headers=_auth(user_id)
    )
    assert response.status_code == 200
    return response.json()["outcome"]


@pytest.mark.asyncio
async def test_checkin_evaluates_five_dimensions_with_injected_llm_context(
    client, users, active_plan, background_tasks, graph_factory_calls
):
    """AC1/AC5：模型上下文由 PlanService 注入，Graph 不重复解析客户端。"""
    await run_adjustment(
        client, users["owner"].id, background_tasks, completed=9, total=10, difficulty=3
    )
    assert graph_factory_calls == [], f"Graph 不应自行解析客户端：{graph_factory_calls}"

    outcome = await latest_outcome(client, users["owner"].id)
    assert outcome is not None
    dimensions = outcome["dimensions"]
    assert [entry["name"] for entry in dimensions] == list(DIMENSION_ORDER)
    for entry in dimensions:
        assert entry["reason"]
        assert entry["suggestion"]
        assert 0 <= entry["score"] <= 10
    by_name = {entry["name"]: entry for entry in dimensions}
    assert by_name[DIMENSION_COMPLETION]["score"] == 9
    assert by_name[DIMENSION_COMPLETION]["source"] == "rule"
    assert by_name[DIMENSION_COMPLETION]["data_completeness"] == "full"
    for name in (DIMENSION_INJURY_RISK, DIMENSION_BODY_COMPOSITION):
        assert by_name[name]["source"] == "llm"
        assert by_name[name]["degraded"] is True
    assert graph_factory_calls == []


@pytest.mark.asyncio
async def test_merged_summary_and_direction_are_persisted_and_readable(
    client, users, active_plan, background_tasks, graph_factory_calls
):
    """AC2：合并分、剔除清单、顶层理由与方向都落进 08 的结论并读得出来。"""
    await run_adjustment(
        client, users["owner"].id, background_tasks, completed=9, total=10, difficulty=3
    )
    outcome = await latest_outcome(client, users["owner"].id)

    assert outcome["direction"] == "increase"
    assert outcome["completion_rate"] == pytest.approx(0.9)
    assert "90%" in outcome["reason"]
    assert outcome["overall_score"] == pytest.approx(9.0)

    merged = outcome["merged"]
    assert merged["overall_score"] == pytest.approx(9.0)
    assert merged["excluded_dimensions"] == [
        DIMENSION_FATIGUE,
        DIMENSION_INJURY_RISK,
        DIMENSION_SLEEP,
        DIMENSION_BODY_COMPOSITION,
    ]
    assert merged["degraded_dimensions"] == merged["excluded_dimensions"]
    assert merged["completeness"] == "partial"
    assert merged["red_flags"] == []
    assert 1 <= len(merged["top_reasons"]) <= 3
    assert outcome["delta_percent"] == pytest.approx(12.0)

    detail = await client.get(
        f"/api/plan/{users['owner'].id}/adjustments/{outcome['adjustment_id']}",
        headers=_auth(users["owner"].id),
    )
    assert detail.status_code == 200
    assert detail.json()["direction"] == "increase"

    # 落地仍然写回计划：方向对应的声明幅度体现在整体难度系数上。
    plan_response = await client.get(
        f"/api/plan/{users['owner'].id}/current", headers=_auth(users["owner"].id)
    )
    assert plan_response.status_code == 200
    assert plan_response.json()["plan"]["difficulty_factor"] == pytest.approx(1.12)


@pytest.mark.asyncio
async def test_completion_extreme_keeps_the_conservative_direction(
    client, users, active_plan, background_tasks
):
    """AC2：合并分指向保持、完成率极值指向加量时取更保守的一方。"""
    await run_adjustment(
        client, users["owner"].id, background_tasks, completed=8, total=10, difficulty=3
    )
    outcome = await latest_outcome(client, users["owner"].id)
    assert outcome["direction"] == "keep"
    assert outcome["overall_score"] == pytest.approx(7.0)
    assert outcome["delta_percent"] == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_low_completion_still_decreases(
    client, users, active_plan, background_tasks
):
    """完成率极低时方向为减量，且理由里带触发数值。"""
    await run_adjustment(
        client, users["owner"].id, background_tasks, completed=2, total=10, difficulty=3
    )
    outcome = await latest_outcome(client, users["owner"].id)
    assert outcome["direction"] == "decrease"
    assert outcome["overall_score"] == pytest.approx(5.0)
    assert outcome["delta_percent"] == pytest.approx(18.0)
    assert "20%" in outcome["reason"]

    plan_response = await client.get(
        f"/api/plan/{users['owner'].id}/current", headers=_auth(users["owner"].id)
    )
    assert plan_response.status_code == 200
    assert plan_response.json()["plan"]["difficulty_factor"] == pytest.approx(0.82)


@pytest.mark.asyncio
async def test_missing_fatigue_and_sleep_inputs_default_without_error(
    client, users, active_plan, background_tasks, graph_factory_calls
):
    """AC3：不填疲劳与睡眠时按缺省参与、标注「数据为缺省」，响应仍 200。"""
    response = await check_in(client, users["owner"].id, completed=9, total=10)
    assert response.status_code == 200
    await background_tasks[-1]

    outcome = await latest_outcome(client, users["owner"].id)
    by_name = {entry["name"]: entry for entry in outcome["dimensions"]}
    assert by_name[DIMENSION_FATIGUE]["data_completeness"] == "default"
    assert by_name[DIMENSION_FATIGUE]["score"] == 7
    assert "数据为缺省" in by_name[DIMENSION_FATIGUE]["reason"]
    assert by_name[DIMENSION_SLEEP]["data_completeness"] == "default"
    assert by_name[DIMENSION_SLEEP]["score"] == 7
    assert "数据为缺省" in by_name[DIMENSION_SLEEP]["reason"]
    assert by_name[DIMENSION_COMPLETION]["score"] == 9
    assert outcome["direction"] == "increase"
    assert outcome["merged"]["completeness"] == "partial"
    assert graph_factory_calls == []


@pytest.mark.asyncio
async def test_one_dimension_failure_degrades_only_itself(
    client, users, active_plan, background_tasks, monkeypatch
):
    """AC4：人为让睡眠维度失败，只有它降级，其余四维与方向照常产出。"""

    def _broken(payload):
        raise ValueError("该维度输入非法")

    monkeypatch.setitem(analyzers_module.ANALYZERS, DIMENSION_SLEEP, _broken)

    response = await check_in(client, users["owner"].id, completed=9, total=10, difficulty=3)
    assert response.status_code == 200
    await background_tasks[-1]

    outcome = await latest_outcome(client, users["owner"].id)
    by_name = {entry["name"]: entry for entry in outcome["dimensions"]}
    assert by_name[DIMENSION_SLEEP]["degraded"] is True
    assert by_name[DIMENSION_SLEEP]["data_completeness"] == "default"
    assert by_name[DIMENSION_COMPLETION]["score"] == 9
    assert by_name[DIMENSION_FATIGUE]["degraded"] is True  # 缺省而非失败
    assert len(outcome["dimensions"]) == 5
    assert outcome["direction"] == "increase"
    assert outcome["overall_score"] == pytest.approx(9.0)
    assert DIMENSION_SLEEP in outcome["merged"]["degraded_dimensions"]


@pytest.mark.asyncio
async def test_low_completion_surfaces_a_red_flag_and_a_decrease(
    client, users, active_plan, background_tasks
):
    """AC2：真实评估里风险信号不是空壳——完成率过低时列表非空且方向为减量。"""
    await run_adjustment(
        client, users["owner"].id, background_tasks, completed=2, total=10, difficulty=3
    )

    outcome = await latest_outcome(client, users["owner"].id)
    codes = [flag["code"] for flag in outcome["merged"]["red_flags"]]
    assert "completion_low" in codes
    assert outcome["direction"] == "decrease"


@pytest.mark.asyncio
async def test_missing_key_route_degrades_both_dimensions_without_credential_copy(
    client, users, active_plan, background_tasks, monkeypatch
):
    """AC3：无可用 Key 时接口仍 200，两维降级，响应不出现凭据错误文案。"""
    from app.services.user.api_key_service import ApiKeyRequiredError

    async def _no_key(self, *args, **kwargs):
        raise ApiKeyRequiredError("使用 AI 功能前，请先配置你自己的 API Key")

    monkeypatch.setattr(
        plan_service_module.LLMClientFactory, "get_client", _no_key
    )

    response = await check_in(
        client, users["owner"].id, completed=9, total=10, difficulty=3
    )
    assert response.status_code == 200
    await background_tasks[-1]

    outcome = await latest_outcome(client, users["owner"].id)
    by_name = {entry["name"]: entry for entry in outcome["dimensions"]}
    for name in (DIMENSION_INJURY_RISK, DIMENSION_BODY_COMPOSITION):
        entry = by_name[name]
        assert entry["degraded"] is True
        assert entry["data_completeness"] == "default"
        assert DEGRADATION_NOTE in entry["reason"]
        assert outcome["merged"]["degraded_reasons"][name] == DEGRADATION_NO_KEY
    assert outcome["merged"]["degradation_note"] == DEGRADATION_NOTE

    serialized = json.dumps(outcome, ensure_ascii=False)
    for forbidden in ("API Key", "请配置", "401", "403"):
        assert forbidden not in serialized

    # 规则维度与决策照常产出。
    assert by_name[DIMENSION_COMPLETION]["score"] == 9
    assert outcome["direction"] == "increase"


@pytest.mark.asyncio
async def test_route_prompt_uses_only_aggregate_summary(
    client, users, active_plan, session_factory, background_tasks, monkeypatch
):
    """AC5：真实链路里 Prompt 只含均值/趋势/计数，不含逐日体重与身份字段。"""

    class _StructuredLLM:
        def __init__(self):
            self.prompts: list[str] = []

        async def ainvoke(self, messages, **kwargs):
            self.prompts.append(messages[-1].content)
            return types.SimpleNamespace(
                content=json.dumps(
                    {"score": 7, "reason": "按聚合趋势判断", "suggestion": "保持当前计划"},
                    ensure_ascii=False,
                )
            )

    async with session_factory() as session:
        for offset, weight in enumerate((70.0, 69.5, 69.2)):
            session.add(
                WeightRecord(
                    user_id=users["owner"].id,
                    weight=weight,
                    recorded_date=TODAY - datetime.timedelta(days=offset),
                )
            )
        await session.commit()

    fake_llm = _StructuredLLM()

    async def _get_client(self, *args, **kwargs):
        return fake_llm

    monkeypatch.setattr(plan_service_module.LLMClientFactory, "get_client", _get_client)

    response = await check_in(
        client, users["owner"].id, completed=9, total=10, difficulty=3
    )
    assert response.status_code == 200
    await background_tasks[-1]

    analyzer_prompts = [
        entry for entry in fake_llm.prompts if "聚合摘要" in entry
    ]
    assert len(analyzer_prompts) == 2
    prompt = "\n".join(analyzer_prompts)
    assert "completion_average" in prompt
    assert "weight_mean_kg" in prompt
    assert "weight_trend" in prompt
    assert "training_days" in prompt
    assert "rule_scores" in prompt
    # 原始逐日体重、昵称与邮箱不得进入 Prompt。
    assert "69.5" not in prompt
    assert "69.2" not in prompt
    assert "Owner" not in prompt
    assert "@" not in prompt

    outcome = await latest_outcome(client, users["owner"].id)
    assert outcome["merged"]["degradation_note"] is None
    assert outcome["merged"]["degraded_reasons"].get(DIMENSION_INJURY_RISK) is None


@pytest.mark.asyncio
async def test_adjustment_failure_does_not_break_checkin(
    client, users, active_plan, background_tasks, monkeypatch
):
    """调整链路整体失败时打卡仍然成功，与工单 08 的解耦要求一致。"""

    async def _boom(self, **kwargs):
        raise RuntimeError("evaluation is down")

    monkeypatch.setattr(plan_service_module.PlanService, "adjust_plan_after_workout", _boom)

    response = await check_in(client, users["owner"].id, completed=9, total=10, difficulty=3)
    assert response.status_code == 200
    await background_tasks[-1]
    assert (await latest_outcome(client, users["owner"].id)) is None
