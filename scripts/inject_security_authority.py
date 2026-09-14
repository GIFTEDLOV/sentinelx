"""Inject a real independent security publisher into a policy template.

The command changes only ``security_authority`` and ``security_prefix`` in a
JSON policy input.  It rejects placeholders, malformed raw-GitHub prefixes,
same-owner source/security prefixes, and in-place writes.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


RAW_PREFIX_RE = re.compile(r"^https://raw\.githubusercontent\.com/([A-Za-z0-9._-]+)/([A-Za-z0-9._-]+)/$")


def raw_owner(prefix: str) -> str:
    match = RAW_PREFIX_RE.fullmatch(prefix)
    return match.group(1) if match else ""


def inject(
    *, input_path: Path, output_path: Path, security_authority: str, security_prefix: str
) -> dict[str, object]:
    if input_path.resolve() == output_path.resolve():
        raise ValueError("in-place policy mutation is not allowed")
    if (not security_authority or security_authority.startswith("<<")
            or security_authority.endswith(">>")):
        raise ValueError("security authority must be a real supplied identifier")
    security_owner = raw_owner(security_prefix)
    if not security_owner:
        raise ValueError("security prefix must be canonical raw GitHub")
    try:
        document = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read policy template: {error}") from error
    if not isinstance(document, dict):
        raise ValueError("policy template must be a JSON object")
    for key in ("source_authority", "ci_authority", "source_prefix", "ci_prefix"):
        value = document.get(key)
        if not isinstance(value, str) or not value or value.startswith("<<"):
            raise ValueError(f"policy template field {key} is not ready")
    source_owner = raw_owner(document["source_prefix"])
    ci_owner = raw_owner(document["ci_prefix"])
    if not source_owner or not ci_owner:
        raise ValueError("source and CI prefixes must be canonical raw GitHub")
    if security_owner.lower() == source_owner.lower():
        raise ValueError("security publisher owner must differ from source owner")
    if security_prefix in (document["source_prefix"], document["ci_prefix"]):
        raise ValueError("all policy prefixes must be distinct")
    if security_authority in (document["source_authority"], document["ci_authority"]):
        raise ValueError("all policy authorities must be distinct")
    document["security_authority"] = security_authority
    document["security_prefix"] = security_prefix
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--security-authority", required=True)
    parser.add_argument("--security-prefix", required=True)
    args = parser.parse_args()
    try:
        inject(**vars(args))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(f"wrote policy with supplied security publisher to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
