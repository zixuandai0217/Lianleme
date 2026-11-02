"""模型增强 + 节流 + 降级的路由级测试（工单 42）。

只断言外部可观测行为：每周期模型调用次数、动作类型与口语化反馈、规则问题项与
评分仍然保留、20 秒去重、单会话上限、连续失败熔断、降级原因与 200 响应、
无 Key 时零调用且不出现凭据引导，以及「Prompt 里只有聚合摘要」这条隐私边界。

模型一律用脚本化替身（记录消息、按脚本返回或抛错），不走网络、不消耗 Key。
"""

import asyncio
import json
import math
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.pose import get_pose_graph
from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.user import User
from app.services.ai.llm_factory import LLMClientFactory
from app.services.ai.pose_graph import PoseGraph
from app.services.pose import llm_coach
from app.services.pose.evaluation import Issue, evaluate_cycle
from app.services.pose.segmentation import KNEE_CHAIN
from app.services.pose.session_store import PoseSessionStore, get_pose_session_store
from app.services.user.api_key_service import ApiKeyRequiredError

SESSIONS_URL = "/api/pose/sessions"
START_ANGLE = 175.0
BOTTOM_ANGLE = 90.0
VALGUS_INWARD = 0.05

OWNER_OPENID = "pose-llm-owner"
OWNER_NICKNAME = "Pose LLM Owner"

# 模型替身的固定输出：动作、置信度、综合分与一句口语化改写。
MODEL_SCORE_LOW = 6.5
MODEL_FEEDBACK = "yo 膝盖往外推一点，knees out! 💪"


def _model_reply(
    *,
    action: str = "squat",
    confidence: float = 0.87,
    score: float = MODEL_SCORE_LOW,
    feedback: str = MODEL_FEEDBACK,
) -> str:
    return json.dumps(
        {
            "action": action,
            "action_confidence": confidence,
            "quality_score": score,
            "feedback": feedback,
        },
        ensure_ascii=False,
    )


DEFAULT_REPLY = _model_reply()
HIGH_SCORE_REPLY = _model_reply(score=9.5)
LOW_SCORE_REPLY = _model_reply(score=4.0)
UNPARSABLE_REPLY = "这一组我看着还行，继续保持。"


class AuthenticationError(Exception):
    """Provider rejected the credentials."""


class RateLimitError(Exception):
    """Provider throttled the caller."""


class ScriptedLLM:
    """脚本化模型替身：按顺序返回文本或抛错，并记录每次调用的消息。"""

    def __init__(self, script: list | None = None) -> None:
        self.script = list(script or [])
        self.calls: list[list] = []
        self.llm_provider = "qwen"
        self.llm_mode = "byok"

    async def ainvoke(self, messages, **kwargs):
        self.calls.append(list(messages))
        item = self.script.pop(0) if self.script else DEFAULT_REPLY
        if isinstance(item, BaseException):
            raise item
        return SimpleNamespace(content=item)


# --- 合成关键点序列（与切分/评估测试同一套构造） ----------------------------


def _leg_points(angle: float, x_center: float):
    """按膝角构造髋/膝/踝三点（180° = 完全伸直）。"""
    delta = math.radians(180.0 - angle)
    hip = (x_center, 0.40)
    knee = (x_center, 0.55)
    ankle = (knee[0] + 0.15 * math.sin(delta), knee[1] + 0.15 * math.cos(delta))
    return hip, knee, ankle


def _frame(t_ms: int, angle: float, *, visibility: float = 0.95) -> dict:
    """构造一帧帧批载荷（33 点关键点，只给运动相关点赋真实坐标）。"""
    keypoints = [{"x": 0.5, "y": 0.5, "z": 0.0, "visibility": 0.95} for _ in range(33)]
    for indices, x_center in ((KNEE_CHAIN.left, 0.45), (KNEE_CHAIN.right, 0.55)):
        for index, point in zip(indices, _leg_points(angle, x_center)):
            keypoints[index] = {
                "x": point[0],
                "y": point[1],
                "z": 0.0,
                "visibility": visibility,
            }
    return {"t_ms": t_ms, "keypoints": keypoints, "person_count": 1}


def _angle_at(t_ms: int, segments: list[tuple[int, float, float]]) -> float:
    cursor = 0
    for duration, start, end in segments:
        if t_ms <= cursor + duration:
            if duration <= 0:
                return end
            return start + (end - start) * ((t_ms - cursor) / duration)
        cursor += duration
    return segments[-1][2]


def _sequence(segments, *, fps: int = 4, **frame_kwargs) -> list[dict]:
    interval = max(1, round(1000 / fps))
    total = sum(duration for duration, _, _ in segments)
    return [
        _frame(t_ms, _angle_at(t_ms, segments), **frame_kwargs)
        for t_ms in range(0, total + 1, interval)
    ]


def _rep_segments(
    *,
    hold_ms: int = 600,
    rep_ms: int = 2000,
    tail_ms: int = 600,
    reps: int = 1,
    gap_ms: int = 600,
) -> list[tuple[int, float, float]]:
    down = rep_ms // 2
    up = rep_ms - down
    segments: list[tuple[int, float, float]] = []
    for index in range(reps):
        segments.append((hold_ms, START_ANGLE, START_ANGLE))
        segments.append((down, START_ANGLE, BOTTOM_ANGLE))
        segments.append((up, BOTTOM_ANGLE, START_ANGLE))
        if index < reps - 1:
            segments.append((gap_ms, START_ANGLE, START_ANGLE))
    segments.append((tail_ms, START_ANGLE, START_ANGLE))
    return segments


def _batches(frames: list[dict], size: int) -> list[list[dict]]:
    return [frames[index:index + size] for index in range(0, len(frames), size)]


def _valgus_sequence() -> list[dict]:
    """标准往返 + 明显膝内扣：正面视角下命中严重问题。"""
    frames = _sequence(_rep_segments())
    for frame in frames:
        keypoints = frame["keypoints"]
        keypoints[KNEE_CHAIN.left[1]]["x"] += VALGUS_INWARD
        keypoints[KNEE_CHAIN.right[1]]["x"] -= VALGUS_INWARD
    return frames


# --- 替身与夹具 -------------------------------------------------------------


class FakeClock:
    """可拨动的时钟：用来控制 20 秒去重窗口。"""

    def __init__(self, now: float = 1_700_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest_asyncio.fixture
async def session_factory(tmp_path: Path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'pose-llm.db'}", future=True
    )
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded_users(session_factory):
    async with session_factory() as session:
        owner = User(openid=OWNER_OPENID, nickname=OWNER_NICKNAME, is_admin=False)
        session.add(owner)
        await session.commit()
        await session.refresh(owner)
        return {"owner": owner}


@pytest_asyncio.fixture
async def clock():
    return FakeClock()


@pytest_asyncio.fixture
async def store(clock):
    return PoseSessionStore(clock=clock)


@pytest_asyncio.fixture
async def llm(monkeypatch):
    """默认替身返回一份合法 JSON；需要脚本的用例直接改 ``llm.script``。"""

    client = ScriptedLLM()

    async def fake_get_client(self, *args, **kwargs):
        return client

    monkeypatch.setattr(LLMClientFactory, "get_client", fake_get_client)
    return client


@pytest_asyncio.fixture
async def graph(seeded_users):
    """真实姿态图 + 真实教练，只有模型客户端被替换。"""
    return PoseGraph(coach=llm_coach.PoseLLMCoach(user_id=seeded_users["owner"].id))


@pytest_asyncio.fixture
async def client(session_factory, store, graph):
    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_pose_session_store] = lambda: store
    app.dependency_overrides[get_pose_graph] = lambda: graph

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as async_client:
        yield async_client

    app.dependency_overrides.clear()


def _auth_headers(user_id: int) -> dict[str, str]:
    token = jwt.encode({"sub": str(user_id)}, settings.SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


async def _create_session(client: AsyncClient, user_id: int, **payload) -> dict:
    response = await client.post(
        SESSIONS_URL, json=payload or None, headers=_auth_headers(user_id)
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _push(client: AsyncClient, user_id: int, session_id: str, frames: list[dict]):
    return await client.post(
        f"{SESSIONS_URL}/{session_id}/frames",
        json={"frames": frames},
        headers=_auth_headers(user_id),
    )


async def _push_cycles(
    client: AsyncClient,
    user_id: int,
    session_id: str,
    frames: list[dict],
    *,
    batch_size: int = 3,
    between=None,
) -> list[dict]:
    """分批推送整段序列，返回本次新完成的周期；``between`` 可在批间拨钟。"""
    cycles: list[dict] = []
    for batch in _batches(frames, batch_size):
        response = await _push(client, user_id, session_id, batch)
        assert response.status_code == 200, response.text
        cycles.extend(response.json()["cycles"])
        if between is not None:
            between(cycles)
    return cycles


async def _finish(client: AsyncClient, user_id: int, session_id: str) -> dict:
    response = await client.post(
        f"{SESSIONS_URL}/{session_id}/finish", headers=_auth_headers(user_id)
    )
    assert response.status_code == 200, response.text
    return response.json()


def _prompt_text(messages: list) -> str:
    return "\n".join(str(getattr(message, "content", "")) for message in messages)


# --- 模型增强：动作、反馈与规则结果保留 -------------------------------------


@pytest.mark.asyncio
async def test_enhancement_adds_action_and_feedback_and_keeps_rule_issues(
    client, seeded_users, graph, llm
):
    """AC1：动作类型（source=llm）+ 口语化反馈，同时规则问题项与评分仍在。"""
    user = seeded_users["owner"]
    session = await _create_session(client, user.id)
    llm.script = [HIGH_SCORE_REPLY]

    response = await _push(client, user.id, session["session_id"], _valgus_sequence())

    assert response.status_code == 200, response.text
    cycle = response.json()["cycles"][0]
    assert cycle["action"] == {"name": "squat", "confidence": 0.87, "source": "llm"}
    assert cycle["feedback_source"] == "llm"
    assert cycle["hint"] == MODEL_FEEDBACK
    assert cycle["model_score"] == 9.5
    assert cycle["degraded"] is False
    assert cycle["degrade_reason"] is None
    # 规则问题项与评分仍然保留，且严重问题把分数压在低分段。
    assert any(issue["type"] == "knee_valgus" for issue in cycle["issues"])
    rule_evaluation = evaluate_cycle(_valgus_sequence(), camera_view="front")
    assert cycle["score"] == rule_evaluation.score
    assert cycle["score"] < cycle["model_score"]
    assert llm.calls and len(llm.calls) == 1
    assert graph.model_calls == 1


@pytest.mark.asyncio
async def test_model_observations_enter_feedback_as_info_issues(
    client, seeded_users, llm
):
    """spec §5：模型发现规则没覆盖的异常 → info 级补充，不改分数段。"""
    user = seeded_users["owner"]
    session = await _create_session(client, user.id)
    rule_score = evaluate_cycle(_valgus_sequence(), camera_view="front").score
    llm.script = [
        json.dumps(
            {
                "action": "squat",
                "action_confidence": 0.8,
                "quality_score": 6.0,
                "feedback": "膝盖往外推一点，knees out",
                "observations": ["髋部有点晃，hips steady"],
            },
            ensure_ascii=False,
        )
    ]

    response = await _push(client, user.id, session["session_id"], _valgus_sequence())
    cycle = response.json()["cycles"][0]

    info = [issue for issue in cycle["issues"] if issue["severity"] == "info"]
    assert len(info) == 1
    assert info[0]["type"] == "model_observation"
    assert "髋部" in info[0]["hint"]
    # info 只是补充，不改变规则定的分数段。
    assert cycle["score"] == rule_score


@pytest.mark.asyncio
async def test_model_score_can_only_lower_when_rules_found_no_severe_issue(
    client, seeded_users, llm
):
    """模型分只在规则没有严重问题时微调，且只能取更低者。"""
    user = seeded_users["owner"]
    session = await _create_session(client, user.id, camera_view="side")
    frames = _sequence(_rep_segments())
    # 侧面标准往返：规则没有问题项，分数为满分。
    assert evaluate_cycle(frames, camera_view="side").score == 10.0
    llm.script = [LOW_SCORE_REPLY]

    response = await _push(client, user.id, session["session_id"], frames)

    cycle = response.json()["cycles"][0]
    assert cycle["score"] == 4.0
    assert cycle["model_score"] == 4.0
    assert cycle["issues"] == []


@pytest.mark.asyncio
async def test_model_score_never_raises_rule_score(client, seeded_users, llm):
    """无严重问题时模型分也不能抬高规则分。"""
    user = seeded_users["owner"]
    session = await _create_session(client, user.id, camera_view="side")
    llm.script = [_model_reply(score=7.0), _model_reply(score=9.8)]
    frames = _sequence(_rep_segments(reps=2))

    cycles = await _push_cycles(client, user.id, session["session_id"], frames)

    assert len(cycles) == 2
    # 规则分是 10，模型先给 7 再给 9.8：最终分只会是 7 与 9.8，绝不会高于 10。
    assert cycles[0]["score"] == 7.0
    assert cycles[1]["score"] == 9.8


@pytest.mark.asyncio
async def test_missing_quality_score_keeps_action_and_feedback(client, seeded_users, llm):
    """综合分是可选的：缺了它，动作与文案照用，最终分退回规则分。"""
    user = seeded_users["owner"]
    session = await _create_session(client, user.id, camera_view="side")
    llm.script = [
        json.dumps(
            {"action": "deadlift", "action_confidence": 0.8, "feedback": "腰背别松 brah"},
            ensure_ascii=False,
        )
    ]

    response = await _push(
        client, user.id, session["session_id"], _sequence(_rep_segments())
    )

    cycle = response.json()["cycles"][0]
    assert cycle["action"] == {"name": "deadlift", "confidence": 0.8, "source": "llm"}
    assert cycle["feedback_source"] == "llm"
    assert cycle["model_score"] is None
    assert cycle["score"] == 10.0
    assert cycle["degraded"] is False


def test_action_and_anonymous_output_normalization():
    """动作词表跨模块一致；低置信度与代码围栏输出都按规则归一化。"""
    from app.schemas.pose import ACTION_TYPES as SCHEMA_ACTION_TYPES

    assert set(llm_coach.ACTION_TYPES) == set(SCHEMA_ACTION_TYPES)
    assert llm_coach.normalize_action("深蹲") == "squat"
    assert llm_coach.normalize_action("side-bend") == "other"
    fenced = (
        "```json\n"
        '{"action": "squat", "action_confidence": 0.2, "quality_score": 12,'
        ' "feedback": "稳住 core"}\n'
        "```"
    )
    insight = llm_coach.parse_model_output(fenced)
    assert insight is not None
    assert insight.action == "other"
    assert insight.score == 10.0
    assert llm_coach.parse_model_output("没有 JSON 的一句话") is None


def test_fuse_score_is_conservative():
    """纯函数：严重问题钉住规则分，其余取较低者，模型分不参与抬分。"""
    severe = (Issue(type="knee_valgus", severity="critical"),)
    assert llm_coach.fuse_score(3.0, 9.5, severe) == 3.0
    assert llm_coach.fuse_score(10.0, 6.5, ()) == 6.5
    assert llm_coach.fuse_score(8.0, 9.5, ()) == 8.0
    assert llm_coach.fuse_score(8.0, None, ()) == 8.0


# --- 节流：每周期一次、20 秒去重、上限、熔断 -------------------------------


@pytest.mark.asyncio
async def test_one_model_call_per_cycle(client, seeded_users, llm):
    """AC2：每个完成的周期最多一次调用，批次再多也不会按帧调用。"""
    user = seeded_users["owner"]
    session = await _create_session(client, user.id, camera_view="side")
    frames = _sequence(_rep_segments(reps=2))

    cycles = await _push_cycles(client, user.id, session["session_id"], frames)

    assert len(cycles) == 2
    assert len(llm.calls) == 2


@pytest.mark.asyncio
async def test_repeated_issue_within_window_suppresses_hint_only(
    client, seeded_users, clock, llm
):
    """AC2：同一问题 + 同一动作 20 秒内不重复播报，但评分继续更新。"""
    user = seeded_users["owner"]
    session = await _create_session(client, user.id, camera_view="side")
    frames = _sequence(_rep_segments(reps=2))
    llm.script = [_model_reply(score=7.0), _model_reply(score=5.0)]

    cycles = await _push_cycles(client, user.id, session["session_id"], frames)

    assert len(cycles) == 2
    assert len(llm.calls) == 2
    first, second = cycles
    assert first["spoken"] is True
    assert first["hint"] == MODEL_FEEDBACK
    assert second["spoken"] is False
    assert second["hint"] is None
    # 不播报不等于不评分：模型仍然被调用，分数继续更新。
    assert second["score"] == 5.0
    assert second["model_score"] == 5.0


@pytest.mark.asyncio
async def test_hint_is_spoken_again_after_window_expires(
    client, seeded_users, clock, llm
):
    """去重窗口是 20 秒硬边界：过了窗口同一问题可以再播报一次。"""
    user = seeded_users["owner"]
    session = await _create_session(client, user.id, camera_view="side")
    frames = _sequence(_rep_segments(reps=2))
    llm.script = [_model_reply(score=7.0), _model_reply(score=5.0)]
    advanced = {"done": False}

    def between(cycles: list[dict]) -> None:
        if cycles and not advanced["done"]:
            advanced["done"] = True
            clock.advance(21)

    cycles = await _push_cycles(
        client, user.id, session["session_id"], frames, between=between
    )

    assert len(cycles) == 2
    assert cycles[1]["spoken"] is True
    assert cycles[1]["hint"] == MODEL_FEEDBACK


@pytest.mark.asyncio
async def test_budget_cap_pauses_model_with_single_notice(
    client, seeded_users, clock, llm, monkeypatch
):
    """AC3：达到单会话上限后转纯规则，且「深度点评已暂停」只提示一次。"""
    monkeypatch.setattr(llm_coach, "MODEL_CALL_BUDGET", 2)
    user = seeded_users["owner"]
    session = await _create_session(client, user.id, camera_view="side")
    frames = _sequence(_rep_segments(reps=4))

    cycles = await _push_cycles(client, user.id, session["session_id"], frames)

    assert len(cycles) >= 3
    assert len(llm.calls) == 2
    notices = [cycle["notice"] for cycle in cycles if cycle["notice"]]
    assert len(notices) == 1
    assert "深度点评已暂停" in notices[0]
    blocked = [cycle for cycle in cycles if cycle["degrade_reason"] == "budget_exhausted"]
    assert blocked
    assert all(cycle["degraded"] is True for cycle in blocked)
    # 纯规则周期仍有规则评分与问题项，响应照常 200。
    assert all(cycle["score"] is not None for cycle in cycles)

    summary = await _finish(client, user.id, session["session_id"])
    assert summary["model_calls"] == 2
    assert summary["model_paused"] is True
    assert summary["paused_notice_sent"] is True


@pytest.mark.asyncio
async def test_three_consecutive_failures_open_circuit(client, seeded_users, llm):
    """AC4：连续 3 次失败后熔断，后续周期不再调用，汇总能看出已熔断。"""
    user = seeded_users["owner"]
    session = await _create_session(client, user.id)
    frames = _sequence(_rep_segments(reps=4))
    llm.script = [TimeoutError("slow provider")] * 3

    cycles = await _push_cycles(client, user.id, session["session_id"], frames)

    assert len(cycles) >= 4
    assert len(llm.calls) == 3
    broken = [cycle for cycle in cycles if cycle["degrade_reason"] == "timeout"]
    assert len(broken) == 3
    assert all(cycle["degraded"] is True for cycle in broken)
    # 失败周期仍返回规则结果 + 模板文案。
    assert all(cycle["score"] is not None for cycle in broken)
    # 20 秒去重窗口内只播报一次：后续失败周期的 hint 被抑制，但评分照常更新。
    assert broken[0]["hint"]
    assert any(cycle["spoken"] is False for cycle in broken[1:])
    assert all(cycle["feedback_source"] == "template" for cycle in broken)
    after = cycles[3:]
    assert all(cycle["degrade_reason"] == "circuit_open" for cycle in after)

    summary = await _finish(client, user.id, session["session_id"])
    assert summary["circuit_open"] is True
    assert summary["model_degraded"] is True
    assert summary["model_calls"] == 3
    assert summary["degraded_cycles"] >= 3


@pytest.mark.asyncio
async def test_consecutive_failures_reset_on_success(client, seeded_users, llm):
    """成功一次就把连续失败计数清零：失败-成功-失败 不该提前熔断。"""
    user = seeded_users["owner"]
    session = await _create_session(client, user.id, camera_view="side")
    frames = _sequence(_rep_segments(reps=5))
    llm.script = [
        TimeoutError("boom"),
        TimeoutError("boom"),
        DEFAULT_REPLY,
        TimeoutError("boom"),
        TimeoutError("boom"),
    ]

    cycles = await _push_cycles(client, user.id, session["session_id"], frames)

    assert len(cycles) == 5
    assert len(llm.calls) == 5
    summary = await _finish(client, user.id, session["session_id"])
    assert summary["circuit_open"] is False
    assert summary["degraded_cycles"] == 4


# --- 降级：稳定原因、200 响应、下一周期继续尝试 -----------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (AuthenticationError("invalid api key"), "auth_failed"),
        (RateLimitError("429 too many requests"), "rate_limited"),
        (TimeoutError("read timeout"), "timeout"),
    ],
)
async def test_provider_failures_degrade_with_stable_reason(
    client, seeded_users, llm, error, reason
):
    """AC5：超时/限流/鉴权失败都返回 200 + 规则结果 + 模板文案 + 稳定原因。"""
    user = seeded_users["owner"]
    session = await _create_session(client, user.id)
    llm.script = [error]

    response = await _push(client, user.id, session["session_id"], _valgus_sequence())

    assert response.status_code == 200, response.text
    cycle = response.json()["cycles"][0]
    assert cycle["degraded"] is True
    assert cycle["degrade_reason"] == reason
    assert cycle["feedback_source"] == "template"
    assert cycle["action"] is None
    assert cycle["issues"]
    assert cycle["score"] is not None
    assert cycle["hint"]


@pytest.mark.asyncio
async def test_unparsable_output_degrades_and_next_cycle_retries(
    client, seeded_users, llm
):
    """AC5：输出不可解析 → 该周期降级；未熔断时下一周期仍会尝试。"""
    user = seeded_users["owner"]
    session = await _create_session(client, user.id, camera_view="side")
    frames = _sequence(_rep_segments(reps=2))
    llm.script = [UNPARSABLE_REPLY, DEFAULT_REPLY]

    cycles = await _push_cycles(client, user.id, session["session_id"], frames)

    assert len(cycles) == 2
    assert len(llm.calls) == 2
    assert cycles[0]["degraded"] is True
    assert cycles[0]["degrade_reason"] == "unparsable"
    assert cycles[1]["degraded"] is False
    assert cycles[1]["action"]["name"] == "squat"


@pytest.mark.asyncio
async def test_timeout_from_slow_provider_is_bounded(client, seeded_users, monkeypatch):
    """客户端不返回时按超时降级，绝不把请求挂死。"""
    user = seeded_users["owner"]
    session = await _create_session(client, user.id, camera_view="side")

    class SlowLLM:
        llm_provider = "qwen"
        llm_mode = "byok"

        async def ainvoke(self, messages, **kwargs):
            await asyncio.sleep(1.0)
            return SimpleNamespace(content=DEFAULT_REPLY)

    async def fake_get_client(self, *args, **kwargs):
        return SlowLLM()

    monkeypatch.setattr(LLMClientFactory, "get_client", fake_get_client)
    monkeypatch.setattr(llm_coach, "MODEL_TIMEOUT_SECONDS", 0.01)

    response = await _push(
        client, user.id, session["session_id"], _sequence(_rep_segments())
    )

    assert response.status_code == 200
    cycle = response.json()["cycles"][0]
    assert cycle["degraded"] is True
    assert cycle["degrade_reason"] == "timeout"


@pytest.mark.asyncio
async def test_no_key_session_stays_pure_rule_without_credential_copy(
    client, seeded_users, monkeypatch
):
    """AC6：无 Key 且系统回退关闭 → 全程纯规则、零调用、不引导配置 Key。"""

    async def failing_get_client(self, *args, **kwargs):
        raise ApiKeyRequiredError("使用 AI 功能前，请先配置你自己的 API Key")

    monkeypatch.setattr(LLMClientFactory, "get_client", failing_get_client)
    user = seeded_users["owner"]
    session = await _create_session(client, user.id)
    frames = _sequence(_rep_segments(reps=2))

    cycles = await _push_cycles(client, user.id, session["session_id"], frames)

    assert len(cycles) == 2
    for cycle in cycles:
        assert cycle["degraded"] is True
        assert cycle["degrade_reason"] == "api_key_unavailable"
        assert cycle["action"] is None
        assert cycle["feedback_source"] == "template"
        assert cycle["score"] is not None
    assert cycles[0]["hint"]

    summary = await _finish(client, user.id, session["session_id"])
    assert summary["model_calls"] == 0
    assert summary["model_degraded"] is True

    lowered = json.dumps(cycles, ensure_ascii=False).lower()
    # 稳定降级码可以出现在响应里，但绝不出现「去配置 Key」的指引文案。
    for banned in ("请配置", "去配置", "配置自己的", "凭据错误"):
        assert banned not in lowered


@pytest.mark.asyncio
async def test_not_evaluable_cycle_never_calls_model(client, seeded_users, llm):
    """质量闸门优先于模型：不可评估周期零调用、零降级标记。"""
    user = seeded_users["owner"]
    session = await _create_session(client, user.id)

    response = await _push(
        client,
        user.id,
        session["session_id"],
        _sequence(_rep_segments(), visibility=0.4),
    )

    assert response.status_code == 200
    cycle = response.json()["cycles"][0]
    assert cycle["evaluable"] is False
    assert cycle["degraded"] is False
    assert cycle["action"] is None
    assert llm.calls == []


# --- Prompt 隐私边界与默认常量 ----------------------------------------------


@pytest.mark.asyncio
async def test_prompt_contains_only_aggregate_summary(client, seeded_users, llm):
    """输入最小化：只用关节角度摘要 + 视角 + 动作提示，不含身份与坐标。"""
    user = seeded_users["owner"]
    session = await _create_session(
        client, user.id, camera_view="front", exercise_hint="深蹲"
    )
    llm.script = [DEFAULT_REPLY]

    await _push(client, user.id, session["session_id"], _valgus_sequence())

    assert len(llm.calls) == 1
    text = _prompt_text(llm.calls[0])
    assert "front" in text
    assert "深蹲" in text
    # 只有聚合角度摘要：帧行数在 8–12 之间，且是角度而不是坐标。
    frame_lines = [line for line in text.splitlines() if line.startswith("t=")]
    assert llm_coach.MIN_SUMMARY_FRAMES <= len(frame_lines) <= llm_coach.MAX_SUMMARY_FRAMES
    # 身份与原始数据都不进 Prompt。
    for banned in (OWNER_OPENID, OWNER_NICKNAME, "keypoints", "visibility", "person_count"):
        assert banned not in text
    # 用户手选动作优先于模型识别：来源标成 user。
    cycle_response = await client.get(
        f"{SESSIONS_URL}/{session['session_id']}/result", headers=_auth_headers(user.id)
    )
    cycle = cycle_response.json()["cycles"][0]
    assert cycle["action"] == {"name": "squat", "confidence": 1.0, "source": "user"}
    assert cycle["hint"] == MODEL_FEEDBACK


def test_throttle_defaults_are_module_constants():
    """上限/窗口/熔断阈值是模块常量，不依赖运行时配置。"""
    assert llm_coach.MODEL_CALL_BUDGET == 20
    assert llm_coach.BREAKER_FAILURE_THRESHOLD == 3
    assert llm_coach.REPEAT_SUPPRESS_WINDOW_MS == 20_000
    assert llm_coach.MODEL_TEMPERATURE == 0.0
    assert 8 <= llm_coach.MIN_SUMMARY_FRAMES <= llm_coach.MAX_SUMMARY_FRAMES <= 12
