"""质量门 ⇔ CI 契约；`python tools/ci_contract.py --check` 不一致时非零退出。

契约回答两个问题：
1. 门里声明为必需的步骤（完整档）与 CI 的必需检查名是否逐字一致；
2. 报告制步骤（门 `report` 档）在 CI 里是否确实不阻断。

名字是分支保护的锚点，所以必需检查名在 REQUIRED_CHECKS 里显式钉死：门里新增步骤时
必须同时更新 CI、契约常量与文档，任何一侧漏改都失败——这正是「不要静默少跑一项」。
读数只用 quality_gate 的纯函数（step_names / step_timeouts），不解析可执行文件，
因此没有 npm/uv 的环境也能跑契约。

只读取本仓库工作流的受限 YAML 子集，不引入 YAML 依赖。每个 job 必须有
`# stage: A|B|C` 标记：A 对应快速档，B 对应完整档独有步骤，C 为报告制。
这不是通用 YAML 校验器；不支持的 job/needs/name 写法会明确报错，不静默忽略。
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import quality_gate  # noqa: E402

DEFAULT_WORKFLOW = ROOT / ".github/workflows/ci.yml"

# 分支保护要逐字引用的必需检查名（顺序与阶段一致）。改名等于破坏合并门禁。
REQUIRED_CHECKS = (
    "web-typecheck",
    "web-lint",
    "web-unit",
    "backend-lint",
    "backend-unit",
    "smoke",
    "web-build",
)
REPORT_CHECKS = ("backend-mypy-report", "coach-assets-report")

_COMMAND_PATTERNS = {
    "A": r"quality_gate\.py --step {name}\s*$",
    "B": r"quality_gate\.py (?:--full|--profile full) --step {name}\s*$",
    "C": r"quality_gate\.py (?:--report|--profile report) --step {name}\s*$",
}


@dataclass(frozen=True)
class Job:
    job_id: str
    name: str
    stage: str
    needs: frozenset[str]
    report_only: bool
    timeout_minutes: int | None
    body: str


def parse_jobs(text: str) -> list[Job]:
    """读取两空格 job 键、四空格字段；只接受静态检查名与行内 needs 列表。"""
    if "\t" in text:
        raise ValueError("工作流不能使用 tab 缩进")
    sections = re.split(r"(?m)^jobs:\s*\n", text)
    if len(sections) != 2:
        raise ValueError("必须有且仅有一个顶层 jobs: 段落")
    jobs_text = sections[1]
    if re.search(r"(?m)^[^ #\n]", jobs_text):
        raise ValueError("jobs: 必须是最后一个顶层段落")
    blocks = re.split(r"(?m)^  ([\w-]+):[ \t]*\n", jobs_text)
    if len(blocks) < 3:
        raise ValueError("jobs: 没有可识别的 job")
    jobs: list[Job] = []
    for index in range(1, len(blocks), 2):
        job_id, body = blocks[index:index + 2]
        names = re.findall(r"(?m)^    name: ([\w-]+)\s*$", body)
        stages = re.findall(r"(?m)^    # stage: ([ABC])\s*$", body)
        if len(names) != 1 or len(stages) != 1:
            raise ValueError(f"job {job_id} 必须有一个静态 name 与一个 # stage: A|B|C")
        needs_fields = re.findall(r"(?m)^    needs:(.*)$", body)
        needs: set[str] = set()
        for field in needs_fields:
            if not re.fullmatch(r"\s*\[[\w, -]*\]\s*", field):
                raise ValueError(f"job {job_id} 的 needs 必须用静态行内列表")
            needs.update(part.strip() for part in field.strip()[1:-1].split(",") if part.strip())
        timeout = re.search(r"(?m)^    timeout-minutes:\s*(\d+)\s*$", body)
        jobs.append(
            Job(
                job_id,
                names[0],
                stages[0],
                frozenset(needs),
                bool(re.search(r"(?m)^    continue-on-error: true\s*$", body)),
                int(timeout.group(1)) if timeout else None,
                body,
            )
        )
    return jobs


def gate_manifest_problems(
    fast: list[str],
    full: list[str],
    report: list[str],
) -> list[str]:
    """纯函数：门的步骤清单必须与契约钉死的名字一致，且报告步骤与必需步骤不相交。"""
    problems: list[str] = []
    if set(full) != set(REQUIRED_CHECKS):
        problems.append(
            "质量门完整档步骤与契约约定的必需检查名不一致："
            f"门={sorted(set(full))}；约定={sorted(REQUIRED_CHECKS)}"
        )
    if set(report) != set(REPORT_CHECKS):
        problems.append(
            "质量门报告档步骤与契约约定的报告检查名不一致："
            f"门={sorted(set(report))}；约定={sorted(REPORT_CHECKS)}"
        )
    if not set(fast) <= set(full):
        problems.append("完整档未包含全部快速档步骤")
    overlap = (set(fast) | set(full)) & set(report)
    if overlap:
        problems.append(f"步骤同时出现在必需与报告档：{', '.join(sorted(overlap))}")
    for label, names in (("快速档", fast), ("完整档", full), ("报告档", report)):
        if len(names) != len(set(names)):
            problems.append(f"质量门{label}步骤名重复")
    return problems


def contract_problems(
    fast: list[str],
    full: list[str],
    report: list[str],
    timeouts: dict[str, int],
    jobs: list[Job],
) -> list[str]:
    """纯函数：比较门的三档清单与实际 job，并检查命令、依赖与超时覆盖。"""
    problems: list[str] = []
    for stage, expected in (
        ("A", set(fast)),
        ("B", set(full) - set(fast)),
        ("C", set(report)),
    ):
        actual = {job.name for job in jobs if job.stage == stage}
        for name in sorted(expected - actual):
            problems.append(f"CI 阶段 {stage} 缺少质量门步骤：{name}")
        for name in sorted(actual - expected):
            problems.append(f"CI 阶段 {stage} 多出质量门未声明的检查：{name}")

    for attr in ("job_id", "name"):
        values = [getattr(job, attr) for job in jobs]
        if len(values) != len(set(values)):
            problems.append(f"CI {attr} 重复")

    stage_a_ids = {job.job_id for job in jobs if job.stage == "A"}
    all_needs = {need for job in jobs for need in job.needs}
    for job in jobs:
        step_timeout = timeouts.get(job.name)
        if step_timeout is None:
            problems.append(f"CI job {job.name} 在质量门里没有对应步骤")
        elif job.timeout_minutes is None:
            problems.append(f"CI job {job.name} 缺少 timeout-minutes，无法覆盖步骤超时")
        elif job.timeout_minutes * 60 < step_timeout:
            problems.append(
                f"CI job {job.name} 的 timeout-minutes={job.timeout_minutes} "
                f"小于门步骤超时上限 {step_timeout}s，会先把门砍断"
            )

        pattern = _COMMAND_PATTERNS[job.stage].format(name=re.escape(job.name))
        if not re.search(pattern, job.body, re.M):
            problems.append(f"CI job {job.name} 必须调用质量门同名 --step，不能自拼命令")

        if job.stage == "C":
            if not job.report_only or job.job_id in all_needs or job.needs:
                problems.append(
                    f"报告制 {job.name} 必须 continue-on-error: true 且隔离 needs"
                )
            continue
        if "continue-on-error:" in job.body or "|| true" in job.body:
            problems.append(f"必需检查 {job.name} 不允许吞错")
        if re.search(r"(?m)^    if:", job.body):
            problems.append(f"必需检查 {job.name} 不允许条件跳过")
        if job.stage == "A" and job.needs:
            problems.append(f"阶段 A 的 {job.name} 必须并行（无 needs）")
        if job.stage == "B" and job.needs != stage_a_ids:
            problems.append(f"阶段 B 的 {job.name} 必须 needs 全部且仅阶段 A jobs")

    required = {job.name for job in jobs if job.stage in {"A", "B"}}
    if required != set(full):
        missing = sorted(set(full) - required)
        extra = sorted(required - set(full))
        problems.append(
            "CI 必需检查集合与质量门必需步骤集合不一致："
            + "；".join(
                part
                for part in (
                    f"缺少 {', '.join(missing)}" if missing else "",
                    f"多出 {', '.join(extra)}" if extra else "",
                )
                if part
            )
        )
    report_only = {job.name for job in jobs if job.stage == "C"}
    if report_only != set(report):
        problems.append("CI 报告制检查集合与质量门报告档不一致")
    return problems


def pipeline_problems(jobs: list[Job], text: str) -> list[str]:
    """编排层硬要求：触发、并发取消、锁文件安装、缓存键与必需步骤不吞错。"""
    problems: list[str] = []

    if not re.search(r"(?m)^on:\s*$", text):
        problems.append("缺少顶层 on: 触发声明")
    for trigger in ("push", "pull_request"):
        if not re.search(rf"(?m)^  {trigger}:\s*$", text):
            problems.append(f"缺少 {trigger} 触发：推送或开 PR 时不会自动跑门")
    if not re.search(r"(?m)^concurrency:\s*$", text):
        problems.append("缺少 concurrency 段落")
    if not re.search(r"(?m)^  cancel-in-progress:\s*true\s*$", text):
        problems.append("concurrency.cancel-in-progress 必须为 true（新提交要取消旧运行）")

    for job in jobs:
        body = job.body
        if re.search(r"\bnpm\s+install\b", body):
            problems.append(f"job {job.name} 使用 npm install：必须 npm ci 按锁文件安装")
        if re.search(r"\bnpm\s+(ci|run)\b", body) and "npm ci" not in body:
            problems.append(f"job {job.name} 未使用 npm ci 安装前端依赖")
        if re.search(r"\buv\s+sync\b", body):
            if "uv sync --frozen" not in body:
                problems.append(f"job {job.name} 未使用 uv sync --frozen 按锁文件安装")
            if "uv lock --check" not in body:
                problems.append(f"job {job.name} 未用 uv lock --check 校验锁文件新鲜度")
        if "cache-suffix:" in body and "github.ref" in body:
            problems.append(f"job {job.name} 的缓存键含 github.ref：分支键无法复用")
        if "actions/cache" in body:
            for key in re.findall(r"(?m)^          key:\s*(.+)$", body):
                if "hashFiles(" not in key:
                    problems.append(f"job {job.name} 的缓存键必须包含锁文件哈希")
                if "github.ref" in key:
                    problems.append(f"job {job.name} 的缓存键不能包含 github.ref")
    return problems


def check_text(
    text: str,
    fast: list[str] | None = None,
    full: list[str] | None = None,
    report: list[str] | None = None,
    timeouts: dict[str, int] | None = None,
) -> list[str]:
    """校验一份工作流文本；返回问题清单，空清单表示契约成立。"""
    fast = list(fast) if fast is not None else quality_gate.step_names("fast")
    full = list(full) if full is not None else quality_gate.step_names("full")
    report = list(report) if report is not None else quality_gate.step_names("report")
    timeouts = (
        dict(timeouts)
        if timeouts is not None
        else quality_gate.step_timeouts("full") | quality_gate.step_timeouts("report")
    )
    try:
        jobs = parse_jobs(text)
    except ValueError as exc:
        return [f"工作流解析失败：{exc}"]
    return (
        gate_manifest_problems(fast, full, report)
        + contract_problems(fast, full, report, timeouts, jobs)
        + pipeline_problems(jobs, text)
    )


def check_workflow(path: Path = DEFAULT_WORKFLOW) -> list[str]:
    """真实门清单是唯一来源；pytest 与 CLI 共用这一条路径（不依赖 npm/uv）。"""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"读不到工作流：{exc}"]
    return check_text(text)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="质量门 ⇔ CI 必需检查一致性校验")
    parser.add_argument("--check", action="store_true", required=True)
    parser.add_argument("--workflow", type=Path, default=DEFAULT_WORKFLOW)
    args = parser.parse_args(argv)
    problems = check_workflow(args.workflow)
    if problems:
        print("FAIL — CI 契约不一致：\n" + "\n".join(f"  ✗ {p}" for p in problems))
        return 1
    print(f"PASS — 必需检查（{len(REQUIRED_CHECKS)}）：{', '.join(REQUIRED_CHECKS)}")
    print(f"        报告制检查（{len(REPORT_CHECKS)}）：{', '.join(REPORT_CHECKS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
