"""质量门：一条命令回答「这个项目现在达标没有」。

用法：
    python tools/quality_gate.py          # 快速档：静态检查 + 单元测试（提交前）
    python tools/quality_gate.py --full   # 完整档：快速档 + 主链路 smoke + 前端构建自检
    python tools/quality_gate.py --report # 报告档：不阻断的检查（CI 阶段 C 使用）

退出码：0 表示全绿；非 0 表示至少一步失败（摘要首行给出失败步骤与可定位线索）。
每一步都有超时上限（StepSpec.timeout_seconds）：超时按失败处理并终止子进程，不会挂死。
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_ALLOWLIST_PATH = ROOT / "tools" / "skip_allowlist.txt"

SKIP_RE = re.compile(r"^SKIPPED \[(\d+)\] (\S+?):\d+: (.*)$", re.M)
LOCATOR_RE = re.compile(r"^(?:FAILED|ERROR) (\S+?)(?: - (.*))?$", re.M)

TAIL_LINES = 40


PROFILES = ("fast", "full", "report")


@dataclass(frozen=True)
class Step:
    """一个可执行步骤：命令、工作目录、跳过收集与超时上限。"""

    name: str
    cmd: tuple[str, ...]
    cwd: Path
    collects_skips: bool = False
    timeout_seconds: int = 300


@dataclass(frozen=True)
class StepSpec:
    """步骤定义（可执行文件尚未解析）：所有档位共用同一份，只按 profiles 选子集。

    CI 契约只需要步骤名与超时上限，不该因为没有 npm/uv 就起不来，所以「清单元数据」
    与「可执行文件解析」分成两层：step_names() / step_timeouts() 是纯函数，
    build_steps() 才解析可执行文件。
    """

    name: str
    tool: str
    args: tuple[str, ...]
    cwd: str
    profiles: frozenset[str] = frozenset({"fast", "full"})
    collects_skips: bool = False
    timeout_seconds: int = 300


STEP_SPECS: tuple[StepSpec, ...] = (
    StepSpec("web-typecheck", "npm", ("run", "typecheck"), "web", timeout_seconds=300),
    StepSpec("web-lint", "npm", ("run", "lint"), "web", timeout_seconds=300),
    StepSpec("web-unit", "npm", ("run", "test:unit:run"), "web", timeout_seconds=300),
    StepSpec(
        "backend-lint",
        "uv",
        ("run", "ruff", "check", "."),
        "backend",
        timeout_seconds=180,
    ),
    StepSpec(
        "backend-unit",
        "uv",
        ("run", "pytest", "-q", "-rs"),
        "backend",
        collects_skips=True,
        timeout_seconds=600,
    ),
    StepSpec(
        "smoke",
        "uv",
        ("run", "pytest", "-q", "tests/test_smoke_main_path.py"),
        "backend",
        frozenset({"full"}),
        collects_skips=True,
        timeout_seconds=600,
    ),
    StepSpec(
        "web-build",
        "npm",
        ("run", "build"),
        "web",
        frozenset({"full"}),
        timeout_seconds=600,
    ),
    StepSpec(
        "backend-mypy-report",
        "uv",
        ("run", "mypy", "app"),
        "backend",
        frozenset({"report"}),
        timeout_seconds=600,
    ),
    StepSpec(
        "coach-assets-report",
        "uv",
        ("run", "python", "../web/scripts/validate-coach-assets.py"),
        "backend",
        frozenset({"report"}),
        timeout_seconds=300,
    ),
)


@dataclass
class StepResult:
    step: Step
    returncode: int
    duration: float
    output: str
    skips: list[tuple[str, str]] = field(default_factory=list)
    unregistered_skips: list[tuple[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.unregistered_skips


def load_allowlist(path: Path = SKIP_ALLOWLIST_PATH) -> list[tuple[str, str]]:
    """读取「已登记的跳过」：每行 `相对路径 | 原因片段`，空行与 # 开头忽略。"""
    if not path.exists():
        return []
    entries: list[tuple[str, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "|" not in line:
            entries.append((line, ""))
            continue
        test_path, reason = line.split("|", 1)
        entries.append((test_path.strip(), reason.strip()))
    return entries


def parse_skips(output: str) -> list[tuple[str, str]]:
    """从 pytest -rs 输出里提取 (用例文件, 原因)。"""
    return [(match.group(2), match.group(3).strip()) for match in SKIP_RE.finditer(output)]


def split_registered_skips(
    skips: list[tuple[str, str]], allowlist: list[tuple[str, str]]
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    registered: list[tuple[str, str]] = []
    unregistered: list[tuple[str, str]] = []
    for test_path, reason in skips:
        if any(
            test_path.endswith(allowed_path) and allowed_reason in reason
            for allowed_path, allowed_reason in allowlist
        ):
            registered.append((test_path, reason))
        else:
            unregistered.append((test_path, reason))
    return registered, unregistered


def failure_locator(result: StepResult) -> str:
    """给失败步骤找一个能直接定位的线索：优先 FAILED/ERROR 行，其次最后一行输出。"""
    match = LOCATOR_RE.search(result.output)
    if match:
        return match.group(1) + (f" — {match.group(2)}" if match.group(2) else "")
    tail = [line for line in result.output.strip().splitlines() if line.strip()]
    return tail[-1].strip() if tail else f"exit code {result.returncode}"


def run_step(step: Step, allowlist: list[tuple[str, str]]) -> StepResult:
    started = time.monotonic()
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    try:
        completed = subprocess.run(  # noqa: S603 - 步骤命令由本文件定义，非用户输入
            list(step.cmd),
            cwd=step.cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=step.timeout_seconds,
        )
        returncode = completed.returncode
        output = (completed.stdout or "") + (completed.stderr or "")
    except FileNotFoundError as exc:
        returncode = 127
        output = f"命令未找到：{exc}"
    except subprocess.TimeoutExpired:
        # 超时即失败并终止子进程：不允许挂死整个门，也不允许降级为跳过。
        returncode = 124
        output = f"步骤超时：超过 {step.timeout_seconds}s 未结束（已终止）"
    duration = time.monotonic() - started

    result = StepResult(step=step, returncode=returncode, duration=duration, output=output)
    if step.collects_skips:
        result.skips = parse_skips(output)
        _, result.unregistered_skips = split_registered_skips(result.skips, allowlist)
    return result


def render_summary(results: list[StepResult], profile: str, total: float) -> str:
    lines: list[str] = []
    failing = [result for result in results if not result.ok]

    if failing:
        first = failing[0]
        lines.append(f"FAIL {first.step.name} — {failure_locator(first)}")
    else:
        lines.append(f"PASS — {len(results)} steps, profile={profile}")

    name_width = max(len(result.step.name) for result in results) if results else 10
    for result in results:
        status = "ok  " if result.ok else "FAIL"
        skipped = len(result.skips)
        lines.append(
            f"  [{status}] {result.step.name.ljust(name_width)}  "
            f"{result.duration:6.1f}s  exit={result.returncode}  skipped={skipped}"
        )
        for test_path, reason in result.unregistered_skips:
            lines.append(f"         ✗ 未登记的跳过：{test_path}（{reason}）")
        for test_path, reason in result.skips:
            if (test_path, reason) not in result.unregistered_skips:
                lines.append(f"         · 已登记跳过：{test_path}（{reason}）")

    for result in failing:
        lines.append("")
        lines.append(f"--- {result.step.name} 输出末尾 ---")
        tail = result.output.strip().splitlines()[-TAIL_LINES:]
        lines.extend(f"  {line}" for line in tail)

    lines.append("")
    lines.append(f"总耗时 {total:.1f}s")
    return "\n".join(lines)


def _validate_profile(profile: str) -> None:
    """档位只允许 PROFILES 里声明的那几档，写错时立刻报错而不是跑出一个空集合。"""
    if profile not in PROFILES:
        raise ValueError(f"未知的质量门档位：{profile}（可选：{', '.join(PROFILES)}）")


def _specs_for(profile: str, names: set[str] | None = None) -> list[StepSpec]:
    """选定档位的步骤定义；可选再按步骤名过滤，未知名字直接报错。"""
    _validate_profile(profile)
    specs = [spec for spec in STEP_SPECS if profile in spec.profiles]
    if names is None:
        return specs
    unknown = names - {spec.name for spec in specs}
    if unknown:
        raise ValueError(f"档位 {profile} 没有步骤：{', '.join(sorted(unknown))}")
    return [spec for spec in specs if spec.name in names]


def step_names(profile: str) -> list[str]:
    """该档位的步骤名清单（纯函数，不解析可执行文件，供 CI 契约比对必需检查）。"""
    return [spec.name for spec in _specs_for(profile)]


def step_timeouts(profile: str) -> dict[str, int]:
    """该档位每个步骤的超时上限（秒），供 CI 契约校验 job timeout 覆盖步骤上限。"""
    return {spec.name: spec.timeout_seconds for spec in _specs_for(profile)}


def build_steps(profile: str, *, names: set[str] | None = None) -> list[Step]:
    """把步骤定义解析成可执行步骤；CI 可选单步，但仍共用命令、跳过检查与超时。"""
    specs = _specs_for(profile, names)
    resolved = {spec.tool: shutil.which(spec.tool) for spec in specs}
    missing = sorted(tool for tool, path in resolved.items() if path is None)
    if missing:
        raise SystemExit(f"质量门缺少必需的可执行文件：{', '.join(missing)}")

    return [
        Step(
            name=spec.name,
            cmd=(resolved[spec.tool], *spec.args),
            cwd=ROOT / spec.cwd,
            collects_skips=spec.collects_skips,
            timeout_seconds=spec.timeout_seconds,
        )
        for spec in specs
    ]


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="练了么质量门")
    parser.add_argument(
        "--full",
        action="store_true",
        help="完整档：额外跑主链路 smoke 与前端构建自检",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="报告档：只跑不阻断的检查（CI 阶段 C；结论由 CI 的 continue-on-error 决定）",
    )
    parser.add_argument("--profile", choices=PROFILES, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--step", action="append", help="只跑指定步骤（CI 并行 job 使用）")
    args = parser.parse_args(argv)

    if args.profile:
        profile = args.profile
    elif args.full:
        profile = "full"
    elif args.report:
        profile = "report"
    else:
        profile = "fast"
    if args.step:
        try:
            steps = build_steps(profile, names=set(args.step))
        except ValueError as exc:
            parser.error(str(exc))
    else:
        steps = build_steps(profile)
    allowlist = load_allowlist()

    results: list[StepResult] = []
    started = time.monotonic()
    for step in steps:
        results.append(run_step(step, allowlist))
    total = time.monotonic() - started

    print(render_summary(results, profile, total))
    return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())
