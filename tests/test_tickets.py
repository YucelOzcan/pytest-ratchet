"""Reason liveness: cited tickets, the tracker protocol, CLOSED_TICKET in check()."""

from __future__ import annotations

from pathlib import Path

import pytest

from pytest_ratchet.core import Finding, check, load_baseline
from pytest_ratchet.tickets import (
    DEFAULT_TICKET_PATTERN,
    TicketPatternError,
    TicketTracker,
    cited_tickets,
    compile_ticket_pattern,
)

# --- parsing the convention -------------------------------------------------


@pytest.mark.parametrize(
    "reason,expected",
    [
        ("DAC-355: parser patterns grow", ["DAC-355"]),
        ("DAC-355 parser patterns grow", ["DAC-355"]),
        ("DAC-355, DAC-360: two tickets", ["DAC-355", "DAC-360"]),
        ("DAC-355 DAC-360: space separated", ["DAC-355", "DAC-360"]),
        ("DAC-355, DAC-355: duplicate", ["DAC-355"]),
        ("  DAC-7: leading whitespace is fine", ["DAC-7"]),
        ("see DAC-355 for context", []),
        ("fix when DAC-355 lands", []),
        ("TODO", []),
        ("kept for the plugin protocol", []),
        ("dac-355: lowercase is prose, not a claim", []),
        ("", []),
    ],
)
def test_cited_tickets_leading_list_only(reason, expected):
    assert cited_tickets(reason) == expected


def test_custom_pattern_is_anchored_even_if_user_forgot():
    regex = compile_ticket_pattern(r"#\d+")
    assert cited_tickets("#12: gh issue", regex) == ["#12"]
    assert cited_tickets("closes #12", regex) == []


def test_invalid_pattern_is_an_error():
    with pytest.raises(TicketPatternError):
        compile_ticket_pattern("(")


def test_default_pattern_is_anchored():
    assert DEFAULT_TICKET_PATTERN.startswith("^")


# --- check() with a tracker -------------------------------------------------


class FakeTracker:
    """Scripted answers; records every question so caching can be asserted."""

    def __init__(self, answers: dict[str, bool | None], notes: dict[str, str] | None = None):
        self.answers = answers
        self.notes = notes or {}
        self.asked: list[str] = []

    def is_open(self, ticket_id: str) -> bool | None:
        self.asked.append(ticket_id)
        return self.answers.get(ticket_id)

    def explain(self, ticket_id: str) -> str | None:
        return self.notes.get(ticket_id)


def test_fake_tracker_satisfies_the_protocol():
    assert isinstance(FakeTracker({}), TicketTracker)


def baseline(tmp_path: Path, *entries: tuple[str, str]):
    body = "[vulture]\n" + "".join(
        f'[[vulture.entry]]\nkey = "{key}"\nreason = "{reason}"\n' for key, reason in entries
    )
    path = tmp_path / "ratchet-baseline.toml"
    path.write_text(body, encoding="utf-8")
    return load_baseline(path)


def findings(*keys: str) -> list[Finding]:
    return [Finding(kind="unused-import", key=k) for k in keys]


def test_without_tracker_nothing_changes(tmp_path):
    b = baseline(tmp_path, ("a.py::import::x", "DAC-1: closed long ago"))
    report = check("vulture", findings("a.py::import::x"), b)
    assert report.ok
    assert not report.tickets_enabled
    assert report.tickets_checked == 0
    assert "ticket" not in report.summary_line()


def test_open_ticket_is_green_and_counted(tmp_path):
    b = baseline(tmp_path, ("a.py::import::x", "DAC-1: still open"))
    tracker = FakeTracker({"DAC-1": True})
    report = check("vulture", findings("a.py::import::x"), b, tracker=tracker)
    assert report.ok
    assert report.tickets_enabled and report.tickets_checked == 1
    assert report.summary_line() == "section [vulture]: 1 entry OK, 1 ticket checked"


def test_closed_ticket_is_red_with_the_three_way_hint(tmp_path):
    b = baseline(tmp_path, ("a.py::import::x", "DAC-1: waiting for the parser"))
    tracker = FakeTracker({"DAC-1": False}, notes={"DAC-1": "state Done (completed)"})
    report = check("vulture", findings("a.py::import::x"), b, tracker=tracker)
    assert not report.ok
    assert report.problem_count == 1
    (problem,) = report.closed_tickets
    assert (problem.key, problem.ticket, problem.detail) == (
        "a.py::import::x",
        "DAC-1",
        "state Done (completed)",
    )
    text = report.render()
    assert "RATCHET: 1 problem in section [vulture]" in text
    assert "CLOSED_TICKET" in text
    assert "reopen the ticket, or fix the debt and delete the entry, or point the reason at a live ticket" in text
    assert "a.py::import::x   DAC-1 is closed (state Done (completed))" in text
    assert 'reason was: "DAC-1: waiting for the parser"' in text


def test_unknown_is_counted_not_red_by_default(tmp_path):
    b = baseline(tmp_path, ("a.py::import::x", "DAC-1: tracker is down"))
    tracker = FakeTracker({}, notes={"DAC-1": "HTTP 503"})
    report = check("vulture", findings("a.py::import::x"), b, tracker=tracker)
    assert report.ok
    assert len(report.unresolved_tickets) == 1
    assert report.unresolved_tickets[0].detail == "HTTP 503"
    assert report.summary_line() == "section [vulture]: 1 entry OK, 1 ticket checked (1 unresolved)"


def test_unknown_is_red_under_strict(tmp_path):
    b = baseline(tmp_path, ("a.py::import::x", "DAC-1: tracker is down"))
    tracker = FakeTracker({}, notes={"DAC-1": "PLANE_API_KEY not set"})
    report = check("vulture", findings("a.py::import::x"), b, tracker=tracker, strict_tickets=True)
    assert not report.ok
    assert report.problem_count == 1
    text = report.render()
    assert "UNRESOLVED_TICKET (strict_tickets is enabled" in text
    assert "a.py::import::x   DAC-1   (PLANE_API_KEY not set)" in text


def test_each_ticket_is_asked_once_per_check(tmp_path):
    b = baseline(
        tmp_path,
        ("a.py::import::x", "DAC-1: shared ticket"),
        ("b.py::import::y", "DAC-1: same ticket again"),
        ("c.py::import::z", "DAC-1, DAC-2: two tickets"),
    )
    tracker = FakeTracker({"DAC-1": True, "DAC-2": False})
    report = check(
        "vulture", findings("a.py::import::x", "b.py::import::y", "c.py::import::z"), b, tracker=tracker
    )
    assert sorted(tracker.asked) == ["DAC-1", "DAC-2"]
    assert report.tickets_checked == 2
    assert [p.key for p in report.closed_tickets] == ["c.py::import::z"]


def test_any_closed_ticket_in_a_list_is_red(tmp_path):
    b = baseline(tmp_path, ("a.py::import::x", "DAC-1, DAC-2: both must be open"))
    tracker = FakeTracker({"DAC-1": True, "DAC-2": False})
    report = check("vulture", findings("a.py::import::x"), b, tracker=tracker)
    assert [p.ticket for p in report.closed_tickets] == ["DAC-2"]


def test_prose_mentions_are_not_checked(tmp_path):
    b = baseline(tmp_path, ("a.py::import::x", "kept — see DAC-1 for history"))
    tracker = FakeTracker({"DAC-1": False})
    report = check("vulture", findings("a.py::import::x"), b, tracker=tracker)
    assert report.ok and tracker.asked == [] and report.tickets_checked == 0


def test_closed_ticket_and_stale_entry_are_both_reported(tmp_path):
    b = baseline(tmp_path, ("a.py::import::x", "DAC-1: gone and closed"))
    tracker = FakeTracker({"DAC-1": False})
    report = check("vulture", [], b, tracker=tracker)
    assert report.problem_count == 2
    text = report.render()
    assert "STALE" in text and "CLOSED_TICKET" in text


def test_custom_pattern_via_check(tmp_path):
    b = baseline(tmp_path, ("a.py::import::x", "#12: github issue"))
    tracker = FakeTracker({"#12": False})
    report = check("vulture", findings("a.py::import::x"), b, tracker=tracker, ticket_pattern=r"#\d+")
    assert [p.ticket for p in report.closed_tickets] == ["#12"]


def test_tracker_without_explain_is_fine(tmp_path):
    class Bare:
        def is_open(self, ticket_id: str) -> bool | None:
            return False

    b = baseline(tmp_path, ("a.py::import::x", "DAC-1: closed"))
    report = check("vulture", findings("a.py::import::x"), b, tracker=Bare())
    assert report.closed_tickets[0].detail is None
    assert "DAC-1 is closed\n" in report.render()
