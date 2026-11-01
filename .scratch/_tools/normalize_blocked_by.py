"""把工单 frontmatter 的 blocked_by 统一成带引号的两字符写法，避免 YAML 对 0 前缀的歧义。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRATCH = ROOT / ".scratch"

LINE_RE = re.compile(r"^blocked_by:\s*\[(.*)\]\s*$", re.M)
TICKET_RE = re.compile(r'^ticket:\s*"?(\d+)"?\s*$', re.M)


def normalize(match: re.Match) -> str:
    numbers = [f"{int(n):02d}" for n in re.findall(r"\d+", match.group(1))]
    if not numbers:
        return "blocked_by: []"
    quoted = ", ".join(f'"{n}"' for n in numbers)
    return f"blocked_by: [{quoted}]"


def normalize_ticket(match: re.Match) -> str:
    return f"ticket: {int(match.group(1))}"


def main() -> int:
    changed = 0
    for path in sorted(SCRATCH.glob("*/issues/*.md")):
        text = path.read_text(encoding="utf-8")
        new_text = LINE_RE.sub(normalize, text, count=1)
        new_text = TICKET_RE.sub(normalize_ticket, new_text, count=1)
        if new_text != text:
            path.write_text(new_text, encoding="utf-8")
            changed += 1
    print(f"normalized blocked_by in {changed} ticket files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
