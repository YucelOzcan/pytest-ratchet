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

from pathlib import Path

from pytest_ratchet.adapters.vulture import vulture_findings

# Anchored on this file's directory — the same place `ratchet init` seeded the
# baseline from — so the guard scans the right tree and produces keys matching
# the baseline no matter which directory pytest runs from.
HERE = Path(__file__).parent
PATHS = {paths!r}


def test_vulture_ratchet(ratchet):
    ratchet.check(
        "vulture", vulture_findings([HERE / p for p in PATHS], root=HERE)
    )
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
    if args.added:
        try:
            today = datetime.date.fromisoformat(args.added)
        except ValueError:
            print(
                f"ratchet init: --added must be a date like 2026-08-09, got {args.added!r}",
                file=sys.stderr,
            )
            return 1
    else:
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

    # The plugin reads the baseline from pytest's rootdir, which is not always
    # the directory init ran in (monorepos, nested configs). Say so here
    # rather than let the first pytest run look like a broken setup.
    resolved = baseline_path.resolve()
    print(f"\nbaseline: {resolved}")
    outer = _pytest_config_above(resolved.parent)
    if outer is not None:
        print(
            f"note: {outer} sits above this directory, so pytest's rootdir is "
            f"probably {outer.parent} and it will not find this baseline.\n"
            f"      Either run pytest from {resolved.parent}, or add to {outer}:\n"
            f"          ratchet_baseline = "
            f"{_relative(resolved, outer.parent)}"
        )
    else:
        print(
            "pytest reads it from its rootdir — run pytest from this directory, "
            "or point it here with `ratchet_baseline` in your pytest config."
        )
    return 0


_PYTEST_CONFIG_NAMES = ("pytest.ini", "pyproject.toml", "tox.ini", "setup.cfg")


def _pytest_config_above(start: Path) -> Path | None:
    """The nearest pytest config in a *parent* directory, if any.

    A config above us usually means pytest's rootdir is that directory, not
    this one — the monorepo trap where init succeeds and the first pytest run
    looks broken.
    """
    for parent in start.parents:
        for name in _PYTEST_CONFIG_NAMES:
            candidate = parent / name
            if candidate.exists():
                return candidate
    return None


def _relative(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return str(path)


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
        "--added",
        metavar="YYYY-MM-DD",
        help=(
            "date to stamp on seeded entries (default: today). Use the real "
            "acceptance date when migrating an existing baseline, so the TODO "
            "age report stays truthful."
        ),
    )
    p_init.add_argument(
        "--test-file",
        default="test_ratchet.py",
        help="where to scaffold the guard test (skipped if the file exists)",
    )

    args = parser.parse_args(argv)
    return _cmd_init(args)
