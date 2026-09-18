"""Fail on committed credential material without flagging environment names."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PEM_RE = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")
ASSIGNMENT_RE = re.compile(
    r"(?i)\b(?:private[_-]?key|mnemonic|api[_-]?key|secret(?:[_-]?key)?)\b"
    r"\s*[:=]\s*(['\"])(?!\1)([^'\"]{8,})\1"
)


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True
    )
    return [ROOT / item for item in result.stdout.decode().split("\0") if item]


def main() -> int:
    findings: list[str] = []
    for path in tracked_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if PEM_RE.search(text):
            findings.append(f"{path.relative_to(ROOT)}: private-key PEM material")
        for match in ASSIGNMENT_RE.finditer(text):
            findings.append(f"{path.relative_to(ROOT)}: literal credential assignment")
            break
    if findings:
        print("SECRET_SCAN: FAIL")
        print("\n".join(findings))
        return 1
    print(f"SECRET_SCAN: PASS ({len(tracked_files())} tracked files inspected)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
