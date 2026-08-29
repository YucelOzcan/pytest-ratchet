"""The README's reason-liveness promises, pinned as tests.

Each assertion here mirrors a sentence in README "Reason liveness"; if the
behaviour changes, the README must change in the same commit.
"""

from __future__ import annotations

from pytest_ratchet import TicketTracker, cited_tickets


def test_readme_convention_examples():
    assert cited_tickets("DAC-355: fix once the parser grows") == ["DAC-355"]
    assert cited_tickets("DAC-355, DAC-360: two tickets") == ["DAC-355", "DAC-360"]
    assert cited_tickets("kept — see DAC-355") == []
    assert cited_tickets("TODO") == []


def test_a_dozen_lines_is_enough_for_a_tracker():
    class AlwaysOpen:
        def is_open(self, ticket_id: str) -> bool | None:
            return True

    assert isinstance(AlwaysOpen(), TicketTracker)
