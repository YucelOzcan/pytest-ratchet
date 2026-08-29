"""Reason liveness: is the ticket a reason cites still open?

A baseline entry whose reason says "DAC-355: fix once the parser grows" makes
a claim about a tracker. When DAC-355 is closed, the entry is neither NEW nor
STALE — the finding is still there, the entry is still there — yet the record
lies: the baseline says "tracked", the tracker says "done". This module gives
the ratchet a third question: *is the reason still alive?*

Convention (docs/design.md, v0.2): a reason cites tickets by starting with
one or more ticket ids — ``DAC-355: ...`` or ``DAC-355, DAC-360: ...``. Ids
elsewhere in the text ("see DAC-355") are prose, not claims, and are ignored
on purpose. A reason that cites no ticket is untouched by this feature.

The tracker is pluggable and deliberately tiny::

    class TicketTracker(Protocol):
        def is_open(self, ticket_id: str) -> bool | None: ...

``None`` means "could not tell" (no credentials, network down, unknown id).
By default that is counted and shown, never red — an offline run must not
break. With strict mode it is red, because in CI "could not tell" is not an
answer a baseline may hide behind.
"""

from __future__ import annotations

import re
from typing import Iterable, Protocol, runtime_checkable

DEFAULT_TICKET_PATTERN = r"^[A-Z][A-Z0-9]+-\d+"

# Separators allowed between ids in a leading list: "DAC-1, DAC-2:" / "DAC-1 DAC-2:"
_LIST_SEPARATOR = re.compile(r"[,\s]+")


@runtime_checkable
class TicketTracker(Protocol):
    """Answers one question per ticket. Adapters live in pytest_ratchet.adapters.

    Optional, duck-typed and display-only: ``explain(ticket_id) -> str | None``
    — a short human phrase used in reports ("state Done (completed)",
    "HTTP 404", "PLANE_API_KEY not set"). Never used for the decision.
    """

    def is_open(self, ticket_id: str) -> bool | None: ...


class TicketPatternError(ValueError):
    """The configured ticket pattern is not a usable regex."""


def compile_ticket_pattern(pattern: str = DEFAULT_TICKET_PATTERN) -> re.Pattern[str]:
    if not pattern.startswith("^"):
        # An unanchored pattern would turn prose mentions into claims.
        pattern = "^" + pattern
    try:
        return re.compile(pattern)
    except re.error as exc:
        raise TicketPatternError(f"ratchet ticket pattern {pattern!r} is not valid: {exc}") from exc


def cited_tickets(reason: str, pattern: str | re.Pattern[str] = DEFAULT_TICKET_PATTERN) -> list[str]:
    """Ticket ids a reason *claims* — the leading list only, in order, unique.

    >>> cited_tickets("DAC-355: parser grows")
    ['DAC-355']
    >>> cited_tickets("DAC-355, DAC-360: two tickets")
    ['DAC-355', 'DAC-360']
    >>> cited_tickets("see DAC-355 for context")
    []
    """
    regex = pattern if isinstance(pattern, re.Pattern) else compile_ticket_pattern(pattern)
    text = reason.strip()
    found: list[str] = []
    pos = 0
    while True:
        m = regex.match(text[pos:])
        if not m or not m.group(0):
            break
        ticket = m.group(0)
        if ticket not in found:
            found.append(ticket)
        pos += m.end()
        sep = _LIST_SEPARATOR.match(text[pos:])
        if not sep:
            break
        pos += sep.end()
    return found


def explain(tracker: TicketTracker, ticket_id: str) -> str | None:
    """The tracker's optional display phrase for a ticket, if it offers one."""
    fn = getattr(tracker, "explain", None)
    if fn is None:
        return None
    text = fn(ticket_id)
    return str(text) if text else None


class TicketStatusCache:
    """One tracker call per ticket per check — several entries often cite one ticket."""

    def __init__(self, tracker: TicketTracker) -> None:
        self._tracker = tracker
        self._seen: dict[str, bool | None] = {}

    def is_open(self, ticket_id: str) -> bool | None:
        if ticket_id not in self._seen:
            self._seen[ticket_id] = self._tracker.is_open(ticket_id)
        return self._seen[ticket_id]

    def explain(self, ticket_id: str) -> str | None:
        return explain(self._tracker, ticket_id)


def all_cited(reasons: Iterable[str], pattern: str | re.Pattern[str] = DEFAULT_TICKET_PATTERN) -> list[str]:
    """Every ticket cited across many reasons, unique, in first-seen order."""
    regex = pattern if isinstance(pattern, re.Pattern) else compile_ticket_pattern(pattern)
    out: list[str] = []
    for reason in reasons:
        for ticket in cited_tickets(reason, regex):
            if ticket not in out:
                out.append(ticket)
    return out
