"""校验 .scratch/*/issues/*.md 工单，并生成全局索引 .scratch/TICKETS.md。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRATCH = ROOT / ".scratch"

BATCHES = [
    ("A", "地基", range(1, 7)),
    ("B", "分析链路", range(7, 17)),
    ("C", "陪练协议", range(17, 20)),
    ("D", "计划与训练", range(20, 24)),
    ("E", "自适应调整", range(24, 29)),
    ("F", "产品闭环", range(29, 36)),
    ("G", "管理后台", range(36, 40)),
    ("H", "AI 深度", range(40, 46)),
]

PATH_PATTERNS = [
    re.compile(r"\bbackend/"),
    re.compile(r"\bweb/src/"),
    re.compile(r"\bdocs/(adr|plans|agents)/"),
    re.compile(r"\.(py|tsx?|json|md)\b"),
    re.compile(r"[A-Za-z]:[\\/]"),
]

AC_RE = re.compile(r"^- \[ \] .+", re.M)
FM_RE = re.compile(r"^---\n(.*?)\n---\n", re.S)

DECISIONS = [
    "**08 的存储形态**：独立「调整结论」记录（一次调整一条、带稳定标识），计划侧只保存最近一次的引用，不复制理由文本；20 读引用、21 与 28 都投影同一来源，24 在该记录上扩展五维明细与合并分。",
    "**09 / 10 的切法**：09 以「测试可 verify」为完成定义（创建即持久、428 不产生记录、重启后仍可查），不为了页面可 demo 而引入内存读取过渡或双写；用户可感知的等待体验从 10 开始。",
    "**14 → 15 的缩略图空窗**：14 阶段历史接口的缩略图字段返回空值并带降级标记，前端走占位；缩略图在 15 补齐。这是刻意接受的中间态。",
    "**周期宿主只有一个**：16 的孤儿巡检挂在执行器（11）的定时清理上，不依赖 33；33 的 tick 只做规则判定与投递记录写入，不承担巡检，也不自建第二套定时器。",
    "**主链路 smoke 不单独成票**：本地质量门的完整档在 01，「CI 上无密钥确定性 + 换故障替身必红」在 02，避免为一张横切验证票再改一次全局编号。",
    "**统一脱敏环节归 05**：03 只定义日志形态与字段，脱敏由 05 的 LLM 调用日志负责，03 不再重复要求。",
    "**18 的「流式与非流式动作一致」**以路由层契约测试验证（同一输入两处输出一致），不要求该行为对用户直接可见。",
    "**29 内联 API 错误语义**：区分「资源不存在」与「请求失败」随 29 一起做，不单独成票——它是引导判定能正确的前提。",
    "**30 不依赖 07**：30 只消费周计划查询语义，07 改的是今日接口的三态，不构成 30 的阻塞边。",
    "**38 的两处二选一已钉死**：筛选 0 行返回仅表头的文件；被拒绝的导出同样写审计记录（含拒绝原因）。",
    "**33 的手动 tick 是内部/运维入口**，不是公开 HTTP 端点，因此不进入 39 的逐端点权限回归清单。",
    "**43 的摘要验收为契约级**：以「下游可只读获取且不含坐标」断言，不依赖 25 落地做端到端，故 43 不依赖 25。",
]



def parse(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    fm_match = FM_RE.match(text)
    fm = {}
    if fm_match:
        for line in fm_match.group(1).splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                fm[key.strip()] = value.strip().strip('"').strip("'")
    title_match = re.search(r"^# (\d+) — (.+)$", text, re.M)
    blocked_raw = fm.get("blocked_by", "[]")
    blocked = [int(n) for n in re.findall(r"\d+", blocked_raw)]
    return {
        "path": path,
        "text": text,
        "fm": fm,
        "title": title_match.group(2) if title_match else None,
        "title_num": int(title_match.group(1)) if title_match else None,
        "blocked": blocked,
        "acs": AC_RE.findall(text),
    }


def main() -> int:
    files = sorted(SCRATCH.glob("*/issues/*.md"))
    if not files:
        print("no tickets found")
        return 1

    tickets: dict[int, dict] = {}
    problems = 0
    for path in files:
        t = parse(path)
        rel = path.relative_to(ROOT).as_posix()
        issues: list[str] = []
        num = t["title_num"]

        if not t["fm"]:
            issues.append("missing frontmatter")
        if t["fm"].get("status") != "ready-for-agent":
            issues.append("status != ready-for-agent")
        if t["fm"].get("feature") != path.parent.parent.name:
            issues.append(f"feature mismatch: {t['fm'].get('feature')} vs {path.parent.parent.name}")
        if t["fm"].get("ticket") is None:
            issues.append("missing ticket number")
        elif num is not None and int(t["fm"]["ticket"]) != num:
            issues.append("frontmatter ticket != H1 number")
        if num is None:
            issues.append("H1 missing or not '# NN — title'")
        elif not path.name.startswith(f"{num:02d}-"):
            issues.append(f"filename should start with {num:02d}-")
        else:
            tickets[num] = t

        if not t["title"]:
            issues.append("missing title")

        if "**What to build:**" not in t["text"]:
            issues.append("missing What to build")
        if "**Blocked by:**" not in t["text"]:
            issues.append("missing Blocked by")
        if len(t["acs"]) < 3:
            issues.append(f"only {len(t['acs'])} acceptance criteria")
        if len(t["acs"]) > 6:
            issues.append(f"{len(t['acs'])} acceptance criteria (max 6)")

        body = t["text"].split("**Status:**", 1)[0]
        hits = sorted({p.pattern for p in PATH_PATTERNS if p.search(body)})
        if hits:
            issues.append(f"file-path leakage: {hits}")

        if issues:
            print(f"FAIL {rel}")
            for issue in issues:
                print(f"     - {issue}")
                problems += 1

    expected = set(range(1, 46))
    missing = expected - set(tickets)
    extra = set(tickets) - expected
    if missing:
        print(f"FAIL missing ticket numbers: {sorted(missing)}")
        problems += len(missing)
    if extra:
        print(f"FAIL unexpected ticket numbers: {sorted(extra)}")
        problems += len(extra)

    for num, t in sorted(tickets.items()):
        for b in t["blocked"]:
            if b not in tickets:
                print(f"FAIL {num:02d} blocked_by {b:02d} does not exist")
                problems += 1
            if b == num:
                print(f"FAIL {num:02d} blocks itself")
                problems += 1
            if b > num:
                print(f"FAIL {num:02d} blocked by later ticket {b:02d}")
                problems += 1

    if problems:
        print(f"\n{len(files)} tickets, {problems} problems — index not written")
        return 2

    lines: list[str] = [
        "# 练了么 — 工单索引（45 张）",
        "",
        "由 14 份规格竖切而来。每张票都是 tracer bullet：跨层、可单独 demo，声明了阻塞它的票。",
        "工单文件位于 `.scratch/<feature>/issues/<NN>-<slug>.md`，`NN` 是全局依赖序号。",
        "",
        "## 可立即开工（无阻塞）",
        "",
    ]
    frontier = [n for n, t in sorted(tickets.items()) if not t["blocked"]]
    lines.append("、".join(f"{n:02d}" for n in frontier))
    lines.append("")
    lines.append("## 全量表")
    lines.append("")
    for code, name, rng in BATCHES:
        batch_nums = [n for n in sorted(tickets) if n in rng]
        if not batch_nums:
            continue
        lines.append(f"### 批次 {code} — {name}")
        lines.append("")
        lines.append("| # | 工单 | 规格 | 阻塞 |")
        lines.append("|---|---|---|---|")
        for n in batch_nums:
            t = tickets[n]
            feature = t["path"].parent.parent.name
            rel = t["path"].relative_to(SCRATCH).as_posix()
            blocked = "、".join(f"{b:02d}" for b in t["blocked"]) or "—"
            lines.append(f"| {n:02d} | [{t['title']}]({rel}) | `{feature}` | {blocked} |")
        lines.append("")
    lines.append("## 使用方式")
    lines.append("")
    lines.append("1. 只领取「阻塞」全部完成、且无阻塞的票（frontier）。")
    lines.append("2. 一张票就是一次完整交付：`What to build` 是验收范围，`Acceptance criteria` 是完成定义。")
    lines.append("3. 规格正文在同目录上一级的 `issue.md`；票与规格冲突时以票为准，并回头修规格。")
    lines.append("4. 校验脚本：`.scratch/_tools/verify_tickets.py`；新增或调整票后跑一次。")
    lines.append("")
    lines.append("## 已裁决的切票边界")
    lines.append("")
    for decision in DECISIONS:
        lines.append(f"- {decision}")
    lines.append("")

    out = SCRATCH / "TICKETS.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"OK {len(tickets)} tickets, 0 problems → wrote {out.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
