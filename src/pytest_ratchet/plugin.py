"""Thin pytest layer over the core primitive."""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from typing import Any, Iterable

import pytest

from pytest_ratchet import core
from pytest_ratchet.tickets import DEFAULT_TICKET_PATTERN, TicketPatternError

_SUMMARIES = pytest.StashKey[list]()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addini(
        "ratchet_baseline",
        help="Path to the ratchet baseline file, relative to rootdir",
        default="ratchet-baseline.toml",
    )
    parser.addini(
        "ratchet_strict_todo",
        help="Fail on baseline entries whose reason is TODO",
        type="bool",
        default=False,
    )
    parser.addini(
        "ratchet_ticket_tracker",
        help=(
            "Ticket tracker factory as 'module:callable' (e.g. "
            "pytest_ratchet.adapters.plane:PlaneTracker). Enables CLOSED_TICKET: "
            "a reason that starts with a ticket id fails when that ticket is closed"
        ),
        default="",
    )
    parser.addini(
        "ratchet_ticket_strict",
        help="Fail when the tracker cannot answer for a cited ticket (recommended in CI)",
        type="bool",
        default=False,
    )
    parser.addini(
        "ratchet_ticket_pattern",
        help="Regex matching one ticket id at the start of a reason",
        default=DEFAULT_TICKET_PATTERN,
    )
    parser.addini(
        "ratchet_ticket_timeout",
        help="Seconds one tracker request may take (passed to factories accepting 'timeout')",
        default="10",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.stash[_SUMMARIES] = []


class Ratchet:
    """Session-held handle: loads the baseline once, checks sections.

    Loading is read-only, so pytest-xdist workers each holding their own
    copy is harmless.
    """

    def __init__(self, config: pytest.Config) -> None:
        self._config = config
        self._baseline: core.Baseline | None = None
        self._load_error: core.BaselineFormatError | None = None
        self._tracker: Any = None
        self._tracker_loaded = False

    @property
    def baseline_path(self) -> Path:
        return Path(self._config.rootpath) / self._config.getini("ratchet_baseline")

    def _load(self) -> None:
        if self._baseline is None and self._load_error is None:
            try:
                self._baseline = core.load_baseline(self.baseline_path)
            except core.BaselineFormatError as exc:
                self._load_error = exc

    def _load_tracker(self) -> Any:
        """Build the ticket tracker once per session from ratchet_ticket_tracker.

        Misconfiguration fails the test loudly: a tracker that silently does
        not exist would be a closed-ticket check that silently does not run.
        """
        if self._tracker_loaded:
            return self._tracker
        self._tracker_loaded = True
        spec = str(self._config.getini("ratchet_ticket_tracker")).strip()
        if not spec:
            return None
        if ":" not in spec:
            pytest.fail(
                f"RATCHET: ratchet_ticket_tracker must be 'module:callable', got {spec!r}",
                pytrace=False,
            )
        module_name, _, attr = spec.partition(":")
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            pytest.fail(
                f"RATCHET: cannot import ticket tracker module {module_name!r}: {exc}",
                pytrace=False,
            )
        factory = getattr(module, attr, None)
        if factory is None:
            pytest.fail(
                f"RATCHET: ticket tracker {spec!r}: {module_name} has no attribute {attr!r}",
                pytrace=False,
            )
        kwargs: dict[str, Any] = {}
        if callable(factory):
            try:
                if "timeout" in inspect.signature(factory).parameters:
                    kwargs["timeout"] = float(self._config.getini("ratchet_ticket_timeout"))
            except (TypeError, ValueError):
                pass
            tracker = factory(**kwargs)
        else:
            tracker = factory
        if not callable(getattr(tracker, "is_open", None)):
            pytest.fail(
                f"RATCHET: ticket tracker {spec!r} produced {type(tracker).__name__}, "
                "which has no is_open(ticket_id) method",
                pytrace=False,
            )
        self._tracker = tracker
        return tracker

    def check(self, section: str, findings: Iterable[core.Finding]) -> core.Report:
        self._load()
        if self._load_error is not None:
            pytest.fail(str(self._load_error), pytrace=False)
        assert self._baseline is not None
        tracker = self._load_tracker()
        try:
            report = core.check(
                section,
                findings,
                self._baseline,
                strict_todo=self._config.getini("ratchet_strict_todo"),
                tracker=tracker,
                ticket_pattern=str(self._config.getini("ratchet_ticket_pattern")),
                strict_tickets=self._config.getini("ratchet_ticket_strict"),
            )
        except TicketPatternError as exc:
            pytest.fail(f"RATCHET: {exc}", pytrace=False)
        if not report.ok:
            pytest.fail(report.render(), pytrace=False)
        self._config.stash[_SUMMARIES].append(report.summary_line())
        return report


@pytest.fixture(scope="session")
def ratchet(request: pytest.FixtureRequest) -> Ratchet:
    return Ratchet(request.config)


def pytest_terminal_summary(
    terminalreporter, exitstatus: int, config: pytest.Config
) -> None:
    lines = config.stash.get(_SUMMARIES, [])
    if lines:
        terminalreporter.section("ratchet")
        for line in lines:
            terminalreporter.write_line(line)
