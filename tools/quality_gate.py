"""质量门：一条命令回答「这个项目现在达标没有」。

用法：
    python tools/quality_gate.py          # 快速档：静态检查 + 单元测试（提交前）
    python tools/quality_gate.py --full   # 完整档：快速档 + 主链路 smoke + 前端构建自检

退出码：0 表示全绿；非 0 表示至少一步失败（摘要首行给出失败步骤与可定位线索）。
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


@dataclass(frozen=True)
class Step:
    """一个质量门步骤。两档共用同一定义，只差在 profiles。"""

    name: str
    cmd: tuple[str, ...]
    cwd: Path
    profiles: frozenset[str] = frozenset({"fast", "full"})
    collects_skips: bool = False


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
        )
        returncode = completed.returncode
        output = (completed.stdout or "") + (completed.stderr or "")
    except FileNotFoundError as exc:
        returncode = 127
        output = f"命令未找到：{exc}"
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


def build_steps(profile: str) -> list[Step]:
    npm = shutil.which("npm")
    uv = shutil.which("uv")
    if npm is None or uv is None:
        missing = [name for name, path in (("npm", npm), ("uv", uv)) if path is None]
        raise SystemExit(f"质量门缺少必需的可执行文件：{', '.join(missing)}")

    web = ROOT / "web"
    backend = ROOT / "backend"
    guaranteed = frozenset({profile})

    steps = [
        Step("web-typecheck", (npm, "run", "typecheck"), web, guaranteed),
        Step("web-lint", (npm, "run", "lint"), web, guaranteed),
        Step("web-unit", (npm, "run", "test:unit:run"), web, guaranteed),
        Step("backend-lint", (uv, "run", "ruff", "check", "."), backend, guaranteed),
        Step(
            "backend-unit",
            (uv, "run", "pytest", "-q", "-rs"),
            backend,
            guaranteed,
            collects_skips=True,
        ),
        Step(
            "smoke",
            (uv, "run", "pytest", "-q", "tests/test_smoke_main_path.py"),
            backend,
            frozenset({"full"}),
            collects_skips=True,
        ),
        Step("web-build", (npm, "run", "build"), web, frozenset({"full"})),
    ]
    return [step for step in steps if profile in step.profiles]


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="练了么质量门")
    parser.add_argument(
        "--full",
        action="store_true",
        help="完整档：额外跑主链路 smoke 与前端构建自检",
    )
    parser.add_argument("--profile", choices=["fast", "full"], default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    profile = args.profile or ("full" if args.full else "fast")
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
