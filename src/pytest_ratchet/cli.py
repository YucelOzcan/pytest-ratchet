"""The `ratchet` CLI. v1: `ratchet init` — seed a baseline from a vulture run.

init is append-only by design (docs/design.md): it can create the baseline
file or add missing entries to it, but it never rewrites, reorders, or
deletes anything a human wrote.
"""

from __future__ import annotations

import argparse
import datetime
import sys
from collections import Counter
from pathlib import Path
from typing import Sequence

from pytest_ratchet import core
from pytest_ratchet.adapters import ScannerUnavailableError
from pytest_ratchet.adapters.vulture import vulture_findings

_FILE_HEADER = (
    "# ratchet-baseline.toml — accepted findings, one [[<section>.entry]] each.\n"
    "# Every entry needs a reason; replace TODO once the finding is examined.\n"
    "# New findings fail the run; stale entries fail it too, until removed.\n"
)

_TEST_TEMPLATE = '''"""Ratchet guard: scanner findings vs the justified baseline."""

from pytest_ratchet.adapters.vulture import vulture_findings


def test_vulture_ratchet(ratchet):
    ratchet.check("vulture", vulture_findings({paths!r}))
'''


def _toml_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _entry_block(key: str, count: int, today: datetime.date) -> str:
    lines = ["", "[[vulture.entry]]", f"key = {_toml_string(key)}", 'reason = "TODO"']
    if count > 1:
        lines.append(f"count = {count}")
    lines.append(f"added = {today.isoformat()}")
    return "\n".join(lines) + "\n"


def _cmd_init(args: argparse.Namespace) -> int:
    try:
        findings = vulture_findings(args.paths, min_confidence=args.min_confidence)
    except ScannerUnavailableError as exc:
        print(f"ratchet init: {exc}", file=sys.stderr)
        return 1

    baseline_path = Path(args.baseline)
    try:
        baseline = core.load_baseline(baseline_path)
    except core.BaselineFormatError as exc:
        print(f"ratchet init: {exc}", file=sys.stderr)
        print("Fix the baseline by hand before seeding into it.", file=sys.stderr)
        return 1

    existing = baseline.sections.get("vulture", {})
    actual = Counter(f.key for f in findings)
    today = datetime.date.today()

    new_keys = sorted(key for key in actual if key not in existing)
    covered = len(actual) - len(new_keys)
    undercounted = sorted(
        key for key in actual if key in existing and actual[key] > existing[key].count
    )

    if new_keys:
        blocks = "".join(_entry_block(key, actual[key], today) for key in new_keys)
        if baseline.missing:
            baseline_path.write_text(_FILE_HEADER + blocks, encoding="utf-8")
        else:
            with baseline_path.open("a", encoding="utf-8") as fh:
                fh.write(blocks)
        # Self-check: init must never write a baseline that fails to load.
        core.load_baseline(baseline_path)
        print(f"seeded {len(new_keys)} entries (reason: TODO) into {baseline_path}")
    else:
        print(f"nothing to seed: {baseline_path} already covers all findings")
    if covered:
        print(f"{covered} findings were already in the baseline")
    for key in undercounted:
        print(
            f"warning: {key} occurs {actual[key]}x but the baseline records "
            f"count {existing[key].count} — pytest will report it as NEW; "
            "raise the count by hand if the extra occurrences are accepted"
        )

    test_path = Path(args.test_file)
    if test_path.exists():
        print(f"{test_path} already exists — left untouched")
    else:
        test_path.write_text(
            _TEST_TEMPLATE.format(paths=[str(p) for p in args.paths]), encoding="utf-8"
        )
        print(f"wrote {test_path} — run `pytest` to enforce the ratchet")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ratchet", description="Baselines that cannot lie."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser(
        "init", help="run vulture and seed the baseline with TODO reasons"
    )
    p_init.add_argument("paths", nargs="+", help="paths to scan (e.g. src/)")
    p_init.add_argument(
        "--min-confidence", type=int, default=0, help="vulture minimum confidence (0-100)"
    )
    p_init.add_argument("--baseline", default="ratchet-baseline.toml")
    p_init.add_argument(
        "--test-file",
        default="test_ratchet.py",
        help="where to scaffold the guard test (skipped if the file exists)",
    )

    args = parser.parse_args(argv)
    return _cmd_init(args)
