"""Thin pytest layer over the core primitive."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pytest

from pytest_ratchet import core

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

    @property
    def baseline_path(self) -> Path:
        return Path(self._config.rootpath) / self._config.getini("ratchet_baseline")

    def _load(self) -> None:
        if self._baseline is None and self._load_error is None:
            try:
                self._baseline = core.load_baseline(self.baseline_path)
            except core.BaselineFormatError as exc:
                self._load_error = exc

    def check(self, section: str, findings: Iterable[core.Finding]) -> core.Report:
        self._load()
        if self._load_error is not None:
            pytest.fail(str(self._load_error), pytrace=False)
        assert self._baseline is not None
        report = core.check(
            section,
            findings,
            self._baseline,
            strict_todo=self._config.getini("ratchet_strict_todo"),
        )
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
