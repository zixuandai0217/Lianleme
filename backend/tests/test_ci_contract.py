"""CI 必需检查与质量门同源；此文件由 backend-unit 自动执行，不另设一条门。"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import ci_contract as contract  # noqa: E402
from tools import quality_gate as qg  # noqa: E402

WORKFLOW_TEXT = contract.DEFAULT_WORKFLOW.read_text(encoding="utf-8")
FAST = qg.step_names("fast")
FULL = qg.step_names("full")
REPORT = qg.step_names("report")
TIMEOUTS = qg.step_timeouts("full") | qg.step_timeouts("report")


def test_repository_ci_contract():
    problems = contract.check_workflow()
    assert not problems, "\n".join(problems)


def test_required_check_names_are_the_seven_stable_ones():
    assert contract.REQUIRED_CHECKS == (
        "web-typecheck",
        "web-lint",
        "web-unit",
        "backend-lint",
        "backend-unit",
        "smoke",
        "web-build",
    )
    assert set(contract.REQUIRED_CHECKS) == set(FULL)
    assert set(contract.REPORT_CHECKS) == set(REPORT)
    assert set(FAST) <= set(FULL)


def test_contract_runs_without_npm_or_uv(monkeypatch):
    monkeypatch.setattr(qg.shutil, "which", lambda tool: None)
    assert contract.check_workflow() == []


def test_gate_step_added_without_ci_job_is_detected():
    drifted_full = [*FULL, "forgotten-check"]
    problems = contract.check_text(
        WORKFLOW_TEXT, FAST, drifted_full, REPORT, TIMEOUTS | {"forgotten-check": 300}
    )
    assert any("forgotten-check" in problem for problem in problems)


def test_gate_step_renamed_without_ci_job_is_detected():
    drifted_fast = ["renamed-typecheck", *FAST[1:]]
    drifted_full = ["renamed-typecheck", *FULL[1:]]
    problems = contract.check_text(WORKFLOW_TEXT, drifted_fast, drifted_full, REPORT, TIMEOUTS)
    assert any("缺少质量门步骤：renamed-typecheck" in problem for problem in problems)
    assert any("web-typecheck" in problem for problem in problems)


def test_ci_check_renamed_without_gate_change_is_detected(tmp_path: Path):
    text = WORKFLOW_TEXT.replace("name: backend-unit\n", "name: renamed-unit\n")
    drifted = tmp_path / "ci.yml"
    drifted.write_text(text, encoding="utf-8")
    problems = contract.check_workflow(drifted)
    assert any("缺少" in problem and "backend-unit" in problem for problem in problems)
    assert any("多出" in problem and "renamed-unit" in problem for problem in problems)
    assert contract.main(["--check", "--workflow", str(drifted)]) == 1


def test_ci_cannot_silently_use_a_different_command():
    drifted = WORKFLOW_TEXT.replace(
        "quality_gate.py --step backend-unit", "other_gate.py --step other"
    )
    problems = contract.check_text(drifted, FAST, FULL, REPORT, TIMEOUTS)
    assert any("同名 --step" in problem for problem in problems)


def test_ci_job_timeout_must_cover_gate_step_timeout():
    drifted = WORKFLOW_TEXT.replace("timeout-minutes: 15", "timeout-minutes: 1", 1)
    problems = contract.check_text(drifted, FAST, FULL, REPORT, TIMEOUTS)
    assert any("小于门步骤超时上限" in problem for problem in problems)


def test_report_job_must_stay_report_only():
    drifted = WORKFLOW_TEXT.replace("continue-on-error: true\n", "", 1)
    problems = contract.check_text(drifted, FAST, FULL, REPORT, TIMEOUTS)
    assert any("必须 continue-on-error: true" in problem for problem in problems)


def test_pipeline_hygiene_is_enforced():
    no_cancel = WORKFLOW_TEXT.replace(
        "  cancel-in-progress: true", "  cancel-in-progress: false"
    )
    assert any(
        "cancel-in-progress" in problem
        for problem in contract.check_text(no_cancel, FAST, FULL, REPORT, TIMEOUTS)
    )

    unfrozen = WORKFLOW_TEXT.replace("uv sync --frozen", "uv sync")
    assert any(
        "uv sync --frozen" in problem
        for problem in contract.check_text(unfrozen, FAST, FULL, REPORT, TIMEOUTS)
    )

    stale_cache = WORKFLOW_TEXT.replace(
        "key: npm-${{ runner.os }}-${{ hashFiles('web/package-lock.json') }}",
        "key: npm-${{ runner.os }}-${{ github.ref }}",
    )
    assert any(
        "github.ref" in problem
        for problem in contract.check_text(stale_cache, FAST, FULL, REPORT, TIMEOUTS)
    )


@pytest.mark.parametrize("job_name", ["web-typecheck", "smoke"])
def test_required_job_cannot_swallow_failure(job_name: str):
    drifted = WORKFLOW_TEXT.replace(
        f"    name: {job_name}\n",
        f"    name: {job_name}\n    continue-on-error: true\n",
    )
    problems = contract.check_text(drifted, FAST, FULL, REPORT, TIMEOUTS)
    assert any("不允许吞错" in problem for problem in problems)


def test_job_without_stage_marker_fails_loudly():
    problems = contract.check_text(
        WORKFLOW_TEXT + "\n  forgotten:\n    name: forgotten\n", FAST, FULL, REPORT, TIMEOUTS
    )
    assert any("解析失败" in problem for problem in problems)
