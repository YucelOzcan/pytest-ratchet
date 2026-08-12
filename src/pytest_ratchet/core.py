"""Core ratchet primitive: a justified baseline with bidirectional enforcement.

Deliberately pytest-free (docs/design.md): the same primitive must be able to
back a CLI later.
"""

from __future__ import annotations

import datetime
import tomllib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

TODO_REASON = "TODO"

_ENTRY_FIELDS = {"key", "reason", "count", "added"}


class BaselineFormatError(Exception):
    """The baseline file is malformed. The run must fail, never degrade."""

    def __init__(self, path: Path, problems: list[str]) -> None:
        self.path = path
        self.problems = problems
        listing = "\n".join(f"  - {p}" for p in problems)
        super().__init__(
            f"RATCHET: malformed baseline {path}\n{listing}\n"
            "Fix the file by hand: every [[<section>.entry]] needs a unique "
            "'key' and a non-empty 'reason' (optional: 'count', 'added')."
        )


@dataclass(frozen=True)
class Finding:
    """One normalized scanner finding.

    `key` is the identity used for matching (stable coordinates, '/'-separated
    paths, no line numbers). Everything else is display-only and never
    participates in matching: `kind` groups findings in human-facing output,
    `message` and `line` show where the finding currently sits.
    """

    kind: str
    key: str
    message: str = ""
    line: int | None = None


@dataclass(frozen=True)
class Entry:
    key: str
    reason: str
    count: int = 1
    added: datetime.date | None = None

    @property
    def is_todo(self) -> bool:
        return self.reason.strip() == TODO_REASON


@dataclass(frozen=True)
class Baseline:
    path: Path
    sections: dict[str, dict[str, Entry]]
    missing: bool = False


def load_baseline(path: Path) -> Baseline:
    """Load a baseline file; a missing file is an empty baseline, flagged.

    Raises BaselineFormatError on any malformation: this file is the contract
    the whole tool enforces, so it gets no lenient parsing.
    """
    if not path.exists():
        return Baseline(path=path, sections={}, missing=True)

    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise BaselineFormatError(path, [f"not valid TOML: {exc}"]) from exc

    problems: list[str] = []
    sections: dict[str, dict[str, Entry]] = {}

    for section_name, section_value in raw.items():
        where = f"[{section_name}]"
        if not isinstance(section_value, dict):
            problems.append(f"{where}: expected a section table, got {type(section_value).__name__}")
            continue
        unknown = sorted(set(section_value) - {"entry"})
        if unknown:
            problems.append(f"{where}: unknown keys {unknown} (only 'entry' tables are allowed)")
        entry_list = section_value.get("entry", [])
        if not isinstance(entry_list, list):
            problems.append(f"{where}: 'entry' must be an array of tables ([[{section_name}.entry]])")
            continue

        entries: dict[str, Entry] = {}
        for index, item in enumerate(entry_list):
            at = f"[[{section_name}.entry]] #{index + 1}"
            if not isinstance(item, dict):
                problems.append(f"{at}: expected a table")
                continue
            unknown = sorted(set(item) - _ENTRY_FIELDS)
            if unknown:
                problems.append(f"{at}: unknown fields {unknown} (typo?)")
                continue

            key = item.get("key")
            if not isinstance(key, str) or not key.strip():
                problems.append(f"{at}: 'key' must be a non-empty string")
                continue
            key = key.strip()
            if key in entries:
                problems.append(
                    f"{at}: duplicate key {key!r} in section [{section_name}] — "
                    "merge the entries (use 'count' for true duplicates)"
                )
                continue

            reason = item.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                problems.append(f"{at} ({key}): 'reason' must be a non-empty string")
                continue

            count = item.get("count", 1)
            if isinstance(count, bool) or not isinstance(count, int) or count < 1:
                problems.append(f"{at} ({key}): 'count' must be an integer >= 1")
                continue

            added = item.get("added")
            if added is not None and (
                isinstance(added, datetime.datetime) or not isinstance(added, datetime.date)
            ):
                problems.append(f"{at} ({key}): 'added' must be a plain date (e.g. added = 2026-08-11)")
                continue

            entries[key] = Entry(key=key, reason=reason.strip(), count=count, added=added)

        sections[section_name] = entries

    if problems:
        raise BaselineFormatError(path, problems)
    return Baseline(path=path, sections=sections)


@dataclass(frozen=True)
class NewProblem:
    key: str
    found: int
    accepted: int
    context: str  # display-only, from the live scan


@dataclass(frozen=True)
class StaleProblem:
    key: str
    found: int
    recorded: int
    reason: str


@dataclass(frozen=True)
class Report:
    section: str
    baseline_path: Path
    baseline_missing: bool
    entry_count: int
    new: tuple[NewProblem, ...]
    stale: tuple[StaleProblem, ...]
    todo_keys: tuple[str, ...]
    todo_oldest_days: int | None
    strict_todo: bool

    @property
    def problem_count(self) -> int:
        todo = len(self.todo_keys) if self.strict_todo else 0
        return len(self.new) + len(self.stale) + todo

    @property
    def ok(self) -> bool:
        return self.problem_count == 0

    def summary_line(self) -> str:
        """One line for green runs: invisible success is indistinguishable
        from a check that didn't run."""
        entries = f"{self.entry_count} entr{'y' if self.entry_count == 1 else 'ies'} OK"
        line = f"section [{self.section}]: {entries}"
        if self.todo_keys:
            line += f", {len(self.todo_keys)} TODO"
            if self.todo_oldest_days is not None:
                line += f" (oldest: {self.todo_oldest_days} days)"
        return line

    def render(self) -> str:
        n = self.problem_count
        lines = [f"RATCHET: {n} problem{'s' if n != 1 else ''} in section [{self.section}]"]

        if self.new:
            lines.append("")
            lines.append("  NEW (not in baseline — fix it or add it with a reason):")
            for p in self.new:
                detail = f"    {p.key}"
                if p.context:
                    detail += f"   {p.context}"
                if p.accepted:
                    detail += f"   ({p.found} found, {p.accepted} accepted)"
                lines.append(detail)

        if self.stale:
            lines.append("")
            lines.append("  STALE (in baseline but no longer found — delete the entry):")
            for p in self.stale:
                detail = f"    {p.key}"
                if p.found:
                    detail += f"   (recorded count {p.recorded}, found {p.found})"
                lines.append(detail)
                lines.append(f'      reason was: "{p.reason}"')

        if self.strict_todo and self.todo_keys:
            lines.append("")
            lines.append("  TODO (strict_todo is enabled — replace TODO with a real reason):")
            for key in self.todo_keys:
                lines.append(f"    {key}")

        if self.baseline_missing and self.new:
            lines.append("")
            lines.append(
                f"  (no baseline file at {self.baseline_path} — run `ratchet init` "
                "to seed one, or create it by hand)"
            )

        return "\n".join(lines)


def check(
    section: str,
    findings: Iterable[Finding],
    baseline: Baseline,
    *,
    strict_todo: bool = False,
    today: datetime.date | None = None,
) -> Report:
    """Compare live findings against one baseline section.

    Set semantics with exact counts, both directions red:
      findings - baseline  -> NEW
      baseline - findings  -> STALE (including count decay)
    """
    entries = baseline.sections.get(section, {})
    findings = list(findings)  # the signature promises Iterable; we walk it twice
    actual = Counter(f.key for f in findings)

    context_by_key: dict[str, str] = {}
    for f in findings:
        if f.key not in context_by_key:
            parts = [p for p in (f.message,) if p]
            if f.line is not None:
                parts.append(f"line {f.line}")
            context_by_key[f.key] = f"({section}: {', '.join(parts)})" if parts else ""

    new = tuple(
        NewProblem(
            key=key,
            found=actual[key],
            accepted=entries[key].count if key in entries else 0,
            context=context_by_key[key],
        )
        for key in sorted(actual)
        if actual[key] > (entries[key].count if key in entries else 0)
    )

    stale = tuple(
        StaleProblem(
            key=key,
            found=actual.get(key, 0),
            recorded=entries[key].count,
            reason=entries[key].reason,
        )
        for key in sorted(entries)
        if entries[key].count > actual.get(key, 0)
    )

    todo_entries = [e for e in entries.values() if e.is_todo]
    todo_keys = tuple(sorted(e.key for e in todo_entries))
    todo_oldest_days: int | None = None
    dated = [e.added for e in todo_entries if e.added is not None]
    if dated:
        reference = today if today is not None else datetime.date.today()
        todo_oldest_days = max((reference - d).days for d in dated)

    return Report(
        section=section,
        baseline_path=baseline.path,
        baseline_missing=baseline.missing,
        entry_count=len(entries),
        new=new,
        stale=stale,
        todo_keys=todo_keys,
        todo_oldest_days=todo_oldest_days,
        strict_todo=strict_todo,
    )
