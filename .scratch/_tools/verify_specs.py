"""校验 .scratch/*/issue.md 是否符合 to-spec 模板与 tracker 约定。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRATCH = ROOT / ".scratch"

REQUIRED_SECTIONS = [
    "## Problem Statement",
    "## Solution",
    "## User Stories",
    "## Implementation Decisions",
    "## Testing Decisions",
    "## Out of Scope",
    "## Further Notes",
    "## 相关文件",
]

PATH_PATTERNS = [
    re.compile(r"\bbackend/"),
    re.compile(r"\bweb/src/"),
    re.compile(r"\bdocs/(adr|plans|agents)/"),
    re.compile(r"\.(py|tsx?|json|md)\b"),
    re.compile(r"[A-Za-z]:[\\/]"),
]

STORY_RE = re.compile(r"^\d+\.\s+.+", re.M)


def section_bounds(text: str, heading: str) -> tuple[int, int]:
    start = text.find(heading)
    if start < 0:
        return -1, -1
    nxt = len(text)
    for other in REQUIRED_SECTIONS:
        idx = text.find(other, start + len(heading))
        if idx > 0:
            nxt = min(nxt, idx)
    return start, nxt


def main() -> int:
    files = sorted(SCRATCH.glob("*/issue.md"))
    if not files:
        print("no issue.md found")
        return 1

    problems = 0
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        issues: list[str] = []

        if not text.startswith("---\n"):
            issues.append("missing frontmatter")
        else:
            fm_end = text.find("\n---\n", 4)
            fm = text[4:fm_end] if fm_end > 0 else ""
            if "status: ready-for-agent" not in fm:
                issues.append("frontmatter status != ready-for-agent")
            m = re.search(r"^feature:\s*(\S+)", fm, re.M)
            if not m:
                issues.append("frontmatter missing feature")
            elif m.group(1) != path.parent.name:
                issues.append(f"feature slug mismatch: {m.group(1)} vs {path.parent.name}")
            if "sources:" not in fm:
                issues.append("frontmatter missing sources")

        for heading in REQUIRED_SECTIONS:
            if heading not in text:
                issues.append(f"missing {heading}")

        start, end = section_bounds(text, "## User Stories")
        if start > 0:
            body = text[start:end]
            stories = STORY_RE.findall(body)
            if len(stories) < 12:
                issues.append(f"user stories only {len(stories)}")
            loose = [s for s in stories if "以便" not in s]
            if loose:
                issues.append(f"{len(loose)} stories lack 以便")

        start, end = section_bounds(text, "## Implementation Decisions")
        if start > 0:
            body = text[start:end]
            hits = sorted({pat.pattern for pat in PATH_PATTERNS if pat.search(body)})
            if hits:
                issues.append(f"file-path leakage in Implementation Decisions: {hits}")
            if len(body) < 400:
                issues.append("Implementation Decisions too thin")

        start, end = section_bounds(text, "## Testing Decisions")
        if start > 0:
            body = text[start:end]
            if "seam" not in body.lower():
                issues.append("Testing Decisions does not mention seam")
            if "prior art" not in body.lower():
                issues.append("Testing Decisions does not cite prior art")

        for empty_section in ("## Problem Statement", "## Solution", "## Out of Scope"):
            start, end = section_bounds(text, empty_section)
            if start > 0 and len(text[start:end].strip()) < len(empty_section) + 20:
                issues.append(f"{empty_section} looks empty")

        lines = len(text.splitlines())
        status = "OK " if not issues else "FAIL"
        print(f"{status} {rel} ({lines} lines)")
        for issue in issues:
            print(f"     - {issue}")
            problems += 1

    print(f"\n{len(files)} specs checked, {problems} problems")
    return 0 if problems == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
