import sys

import pytest

from pytest_ratchet.adapters import ScannerUnavailableError
from pytest_ratchet.adapters.vulture import vulture_findings

DEAD_CODE = "def unused_function():\n    pass\n"


def test_findings_are_keyed_by_symbol(tmp_path):
    (tmp_path / "mod.py").write_text(DEAD_CODE)
    findings = vulture_findings([tmp_path / "mod.py"], root=tmp_path)
    assert len(findings) == 1
    f = findings[0]
    assert f.key == "mod.py::function::unused_function"
    assert f.kind == "function"
    assert f.line == 1  # display-only; not part of the key
    assert "unused function" in f.message


def test_relative_root_still_yields_relative_keys(tmp_path, monkeypatch):
    # Regression: a relative `root` must not silently leave keys absolute.
    (tmp_path / "proj" / "src").mkdir(parents=True)
    (tmp_path / "proj" / "src" / "mod.py").write_text(DEAD_CODE)
    monkeypatch.chdir(tmp_path)
    findings = vulture_findings(["proj/src"], root="proj")
    assert [f.key for f in findings] == ["src/mod.py::function::unused_function"]


def test_min_confidence_filters(tmp_path):
    (tmp_path / "mod.py").write_text(DEAD_CODE)
    assert vulture_findings([tmp_path / "mod.py"], root=tmp_path, min_confidence=100) == []


def test_clean_code_yields_nothing(tmp_path):
    (tmp_path / "mod.py").write_text("def used():\n    pass\n\nused()\n")
    assert vulture_findings([tmp_path / "mod.py"], root=tmp_path) == []


def test_missing_scanner_raises_never_skips(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "vulture", None)  # simulate: not installed
    with pytest.raises(ScannerUnavailableError, match="pip install vulture"):
        vulture_findings([tmp_path])
