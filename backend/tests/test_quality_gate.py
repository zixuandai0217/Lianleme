"""质量门自身的测试：摘要、跳过登记、失败定位与退出码。

门是全项目唯一的「达标与否」结论来源，它自己必须可测——否则它会静默变绿。
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import quality_gate as qg  # noqa: E402


def make_step(name: str = "unit", cmd: tuple[str, ...] = ("python", "-c", "")) -> qg.Step:
    return qg.Step(name=name, cmd=cmd, cwd=REPO_ROOT)


def make_result(ok: bool, name: str = "unit", output: str = "") -> qg.StepResult:
    return qg.StepResult(
        step=make_step(name),
        returncode=0 if ok else 1,
        duration=0.1,
        output=output,
    )


def test_parse_skips_extracts_path_and_reason():
    output = (
        "SKIPPED [1] tests/test_lip_sync.py:42: rhubarb 二进制未安装\n"
        "SKIPPED [2] tests/test_tts.py:10: 需要网络\n"
    )

    assert qg.parse_skips(output) == [
        ("tests/test_lip_sync.py", "rhubarb 二进制未安装"),
        ("tests/test_tts.py", "需要网络"),
    ]


def test_unregistered_skip_is_not_registered():
    skips = [("tests/test_lip_sync.py", "rhubarb 二进制未安装")]
    allowlist = [("tests/test_lip_sync.py", "rhubarb")]

    registered, unregistered = qg.split_registered_skips(skips, allowlist)

    assert registered == skips
    assert unregistered == []


def test_skip_outside_allowlist_is_flagged():
    skips = [("tests/test_new.py", "顺手跳过了")]

    _, unregistered = qg.split_registered_skips(skips, [])

    assert unregistered == skips


def test_step_with_unregistered_skip_is_not_ok():
    result = make_result(ok=True)
    result.skips = [("tests/test_new.py", "顺手跳过了")]
    result.unregistered_skips = list(result.skips)

    assert result.ok is False


def test_failure_locator_prefers_failed_line():
    result = make_result(
        ok=False,
        output="collected 3 items\nFAILED tests/test_x.py::test_y - assert 1 == 2\n",
    )

    assert qg.failure_locator(result) == "tests/test_x.py::test_y — assert 1 == 2"


def test_failure_locator_falls_back_to_last_line():
    result = make_result(ok=False, output="line one\n命令未找到：npm\n")

    assert qg.failure_locator(result) == "命令未找到：npm"


def test_summary_first_line_names_failing_step():
    results = [make_result(ok=True, name="web-lint"), make_result(ok=False, name="backend-unit")]

    summary = qg.render_summary(results, "fast", 1.23)

    assert summary.splitlines()[0].startswith("FAIL backend-unit")


def test_summary_lists_every_step_with_exit_code_and_duration():
    results = [make_result(ok=True, name="web-lint"), make_result(ok=False, name="backend-unit")]

    summary = qg.render_summary(results, "fast", 1.23)

    assert "web-lint" in summary and "backend-unit" in summary
    assert "exit=0" in summary and "exit=1" in summary
    assert "skipped=0" in summary


def test_summary_marks_unregistered_skips():
    result = make_result(ok=True, name="backend-unit")
    result.skips = [("tests/test_new.py", "顺手跳过了")]
    result.unregistered_skips = list(result.skips)

    summary = qg.render_summary([result], "fast", 0.1)

    assert "未登记的跳过" in summary
    assert summary.splitlines()[0].startswith("FAIL backend-unit")


def test_fast_and_full_profiles_share_step_definitions():
    fast = qg.build_steps("fast")
    full = qg.build_steps("full")

    assert [step.name for step in fast] == [
        "web-typecheck",
        "web-lint",
        "web-unit",
        "backend-lint",
        "backend-unit",
    ]
    assert [step.name for step in full[: len(fast)]] == [step.name for step in fast]
    assert {"smoke", "web-build"} <= {step.name for step in full}
    assert fast[0] == qg.build_steps("fast")[0]


@pytest.mark.asyncio
async def test_run_step_reports_nonzero_exit():
    step = make_step(cmd=(sys.executable, "-c", "raise SystemExit(3)"))

    result = qg.run_step(step, [])

    assert result.returncode == 3
    assert result.ok is False


def test_main_returns_nonzero_when_a_step_fails(monkeypatch):
    def fake_build_steps(profile: str):
        return [make_step("fake-step")]

    monkeypatch.setattr(qg, "build_steps", fake_build_steps)
    monkeypatch.setattr(
        qg,
        "run_step",
        lambda step, allowlist: qg.StepResult(
            step=step, returncode=1, duration=0.0, output="boom"
        ),
    )

    assert qg.main(["--profile", "fast"]) == 1


def test_main_returns_zero_when_all_steps_pass(monkeypatch):
    def fake_build_steps(profile: str):
        return [make_step("fake-step")]

    monkeypatch.setattr(qg, "build_steps", fake_build_steps)
    monkeypatch.setattr(
        qg,
        "run_step",
        lambda step, allowlist: qg.StepResult(
            step=step, returncode=0, duration=0.0, output="fine"
        ),
    )

    assert qg.main(["--profile", "fast"]) == 0
