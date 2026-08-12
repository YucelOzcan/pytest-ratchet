import datetime
from pathlib import Path

import pytest

from pytest_ratchet.core import (
    Baseline,
    BaselineFormatError,
    Finding,
    check,
    load_baseline,
)

TODAY = datetime.date(2026, 8, 11)


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "ratchet-baseline.toml"
    path.write_text(text, encoding="utf-8")
    return path


def finding(key: str, **kwargs) -> Finding:
    return Finding(kind="unused-function", key=key, **kwargs)


# --- loading ---------------------------------------------------------------


def test_load_valid_file(tmp_path):
    path = write(
        tmp_path,
        """
        [vulture]
        [[vulture.entry]]
        key = "a.py::function::f"
        reason = "kept for the plugin protocol"
        added = 2026-08-01

        [[vulture.entry]]
        key = "b.py::variable::x"
        reason = "TODO"
        count = 2
        """,
    )
    baseline = load_baseline(path)
    assert not baseline.missing
    entries = baseline.sections["vulture"]
    assert entries["a.py::function::f"].added == datetime.date(2026, 8, 1)
    assert entries["b.py::variable::x"].count == 2
    assert entries["b.py::variable::x"].is_todo
    assert not entries["a.py::function::f"].is_todo


def test_missing_file_is_empty_and_flagged(tmp_path):
    baseline = load_baseline(tmp_path / "ratchet-baseline.toml")
    assert baseline.missing
    assert baseline.sections == {}


def test_invalid_toml_fails(tmp_path):
    path = write(tmp_path, "not [ valid")
    with pytest.raises(BaselineFormatError, match="not valid TOML"):
        load_baseline(path)


@pytest.mark.parametrize(
    ("body", "match"),
    [
        ('[v]\n[[v.entry]]\nkey = "k"', "'reason' must be a non-empty string"),
        ('[v]\n[[v.entry]]\nkey = "k"\nreason = "  "', "'reason' must be a non-empty string"),
        ('[v]\n[[v.entry]]\nreason = "r"', "'key' must be a non-empty string"),
        ('[v]\n[[v.entry]]\nkey = "k"\nreasn = "typo"', r"unknown fields \['reasn'\]"),
        ('[v]\n[[v.entry]]\nkey = "k"\nreason = "r"\ncount = 0', "'count' must be an integer >= 1"),
        ('[v]\n[[v.entry]]\nkey = "k"\nreason = "r"\ncount = true', "'count' must be an integer >= 1"),
        (
            '[v]\n[[v.entry]]\nkey = "k"\nreason = "r"\nadded = 2026-08-11T10:00:00',
            "'added' must be a plain date",
        ),
        ('[v]\nstray = 1\n[[v.entry]]\nkey = "k"\nreason = "r"', r"unknown keys \['stray'\]"),
        ("v = 1", "expected a section table"),
    ],
)
def test_malformed_baselines_fail(tmp_path, body, match):
    path = write(tmp_path, body)
    with pytest.raises(BaselineFormatError, match=match):
        load_baseline(path)


def test_duplicate_key_fails(tmp_path):
    path = write(
        tmp_path,
        """
        [v]
        [[v.entry]]
        key = "k"
        reason = "one"
        [[v.entry]]
        key = "k"
        reason = "two"
        """,
    )
    with pytest.raises(BaselineFormatError, match="duplicate key 'k'"):
        load_baseline(path)


def test_all_problems_reported_at_once(tmp_path):
    path = write(
        tmp_path,
        """
        [v]
        [[v.entry]]
        key = "a"
        [[v.entry]]
        key = "b"
        reasn = "typo"
        """,
    )
    with pytest.raises(BaselineFormatError) as excinfo:
        load_baseline(path)
    assert len(excinfo.value.problems) == 2


# --- checking --------------------------------------------------------------


def baseline_with(tmp_path, text: str) -> Baseline:
    return load_baseline(write(tmp_path, text))


def test_green_when_findings_match_baseline(tmp_path):
    baseline = baseline_with(
        tmp_path,
        '[v]\n[[v.entry]]\nkey = "a"\nreason = "r"',
    )
    report = check("v", [finding("a")], baseline, today=TODAY)
    assert report.ok
    assert report.summary_line() == "section [v]: 1 entry OK"


def test_empty_project_no_baseline_is_green(tmp_path):
    baseline = load_baseline(tmp_path / "ratchet-baseline.toml")
    report = check("v", [], baseline, today=TODAY)
    assert report.ok


def test_generator_findings_are_consumed_once(tmp_path):
    # The signature promises Iterable, and check() walks findings twice.
    baseline = load_baseline(tmp_path / "ratchet-baseline.toml")
    report = check("v", (finding(f"k{i}") for i in range(2)), baseline, today=TODAY)
    assert [p.key for p in report.new] == ["k0", "k1"]


def test_new_finding_fails(tmp_path):
    baseline = load_baseline(tmp_path / "ratchet-baseline.toml")
    report = check("v", [finding("a.py::function::f", message="unused function", line=7)], baseline, today=TODAY)
    assert not report.ok
    text = report.render()
    assert "RATCHET: 1 problem in section [v]" in text
    assert "NEW" in text
    assert "a.py::function::f   (v: unused function, line 7)" in text
    assert "run `ratchet init`" in text  # missing-file guidance


def test_stale_entry_fails_with_reason_shown(tmp_path):
    baseline = baseline_with(
        tmp_path,
        '[v]\n[[v.entry]]\nkey = "gone"\nreason = "was load-bearing"',
    )
    report = check("v", [], baseline, today=TODAY)
    assert not report.ok
    text = report.render()
    assert "STALE" in text
    assert 'reason was: "was load-bearing"' in text
    assert "ratchet init" not in text  # guidance only when the file is missing


def test_count_increase_is_new(tmp_path):
    baseline = baseline_with(
        tmp_path,
        '[v]\n[[v.entry]]\nkey = "k"\nreason = "r"\ncount = 1',
    )
    report = check("v", [finding("k"), finding("k")], baseline, today=TODAY)
    assert [p.key for p in report.new] == ["k"]
    assert report.new[0].found == 2
    assert report.new[0].accepted == 1
    assert "(2 found, 1 accepted)" in report.render()


def test_count_decay_is_stale(tmp_path):
    baseline = baseline_with(
        tmp_path,
        '[v]\n[[v.entry]]\nkey = "k"\nreason = "r"\ncount = 2',
    )
    report = check("v", [finding("k")], baseline, today=TODAY)
    assert [p.key for p in report.stale] == ["k"]
    assert "(recorded count 2, found 1)" in report.render()


def test_swap_same_section_is_caught_both_ways(tmp_path):
    # The ESLint count-swap hole: fix one finding, introduce another.
    baseline = baseline_with(
        tmp_path,
        '[v]\n[[v.entry]]\nkey = "old"\nreason = "r"',
    )
    report = check("v", [finding("new")], baseline, today=TODAY)
    assert [p.key for p in report.new] == ["new"]
    assert [p.key for p in report.stale] == ["old"]
    assert report.problem_count == 2


def test_sections_are_independent(tmp_path):
    baseline = baseline_with(
        tmp_path,
        '[v]\n[[v.entry]]\nkey = "k"\nreason = "r"',
    )
    report = check("other", [], baseline, today=TODAY)
    assert report.ok  # [v] entries do not leak into [other]


def test_report_ordering_is_deterministic(tmp_path):
    baseline = baseline_with(
        tmp_path,
        """
        [v]
        [[v.entry]]
        key = "z-stale"
        reason = "r"
        [[v.entry]]
        key = "a-stale"
        reason = "r"
        """,
    )
    report = check("v", [finding("z-new"), finding("a-new")], baseline, today=TODAY)
    assert [p.key for p in report.new] == ["a-new", "z-new"]
    assert [p.key for p in report.stale] == ["a-stale", "z-stale"]


# --- TODO handling ---------------------------------------------------------


def todo_baseline(tmp_path) -> Baseline:
    return baseline_with(
        tmp_path,
        """
        [v]
        [[v.entry]]
        key = "a"
        reason = "TODO"
        added = 2026-06-27

        [[v.entry]]
        key = "b"
        reason = "TODO"
        added = 2026-08-01
        """,
    )


def test_todo_is_green_but_surfaced_with_age(tmp_path):
    report = check("v", [finding("a"), finding("b")], todo_baseline(tmp_path), today=TODAY)
    assert report.ok
    assert report.summary_line() == "section [v]: 2 entries OK, 2 TODO (oldest: 45 days)"


def test_strict_todo_fails(tmp_path):
    report = check(
        "v", [finding("a"), finding("b")], todo_baseline(tmp_path), strict_todo=True, today=TODAY
    )
    assert not report.ok
    assert report.problem_count == 2
    text = report.render()
    assert "strict_todo is enabled" in text
    assert "replace TODO with a real reason" in text


def test_todo_without_added_has_no_age(tmp_path):
    baseline = baseline_with(
        tmp_path,
        '[v]\n[[v.entry]]\nkey = "a"\nreason = "TODO"',
    )
    report = check("v", [finding("a")], baseline, today=TODAY)
    assert report.summary_line() == "section [v]: 1 entry OK, 1 TODO"
