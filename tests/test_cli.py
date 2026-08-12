from pathlib import Path

from pytest_ratchet.cli import main
from pytest_ratchet.core import load_baseline

DEAD_CODE = "def unused_function():\n    pass\n"


def make_project(tmp_path, monkeypatch) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    (src / "mod.py").write_text(DEAD_CODE)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_init_seeds_baseline_and_scaffolds_test(tmp_path, monkeypatch, capsys):
    make_project(tmp_path, monkeypatch)
    assert main(["init", "src"]) == 0

    baseline = load_baseline(tmp_path / "ratchet-baseline.toml")
    entry = baseline.sections["vulture"]["src/mod.py::function::unused_function"]
    assert entry.reason == "TODO"
    assert entry.added is not None

    scaffold = (tmp_path / "test_ratchet.py").read_text()
    assert "vulture_findings(['src'])" in scaffold
    assert 'ratchet.check("vulture"' in scaffold

    out = capsys.readouterr().out
    assert "seeded 1 entries" in out
    assert "wrote test_ratchet.py" in out


def test_init_is_idempotent_and_append_only(tmp_path, monkeypatch, capsys):
    make_project(tmp_path, monkeypatch)
    assert main(["init", "src"]) == 0
    baseline_path = tmp_path / "ratchet-baseline.toml"

    # A human edits the file: comment + a real reason. init must preserve both.
    human_text = baseline_path.read_text().replace(
        'reason = "TODO"', 'reason = "kept for the dispatch protocol"  # reviewed'
    )
    baseline_path.write_text(human_text)

    assert main(["init", "src"]) == 0
    out = capsys.readouterr().out
    assert "nothing to seed" in out
    after = baseline_path.read_text()
    assert after == human_text  # byte-identical: nothing rewritten
    assert "# reviewed" in after


def test_init_appends_only_new_findings(tmp_path, monkeypatch):
    project = make_project(tmp_path, monkeypatch)
    assert main(["init", "src"]) == 0
    (project / "src" / "more.py").write_text("def also_unused():\n    pass\n")
    assert main(["init", "src"]) == 0

    entries = load_baseline(project / "ratchet-baseline.toml").sections["vulture"]
    assert set(entries) == {
        "src/mod.py::function::unused_function",
        "src/more.py::function::also_unused",
    }


def test_init_warns_on_undercounted_key(tmp_path, monkeypatch, capsys):
    project = make_project(tmp_path, monkeypatch)
    assert main(["init", "src"]) == 0
    # Same symbol appears a second time in the same file -> same key, count 2.
    (project / "src" / "mod.py").write_text(DEAD_CODE + "\n\n" + DEAD_CODE)
    assert main(["init", "src"]) == 0
    out = capsys.readouterr().out
    assert "warning: src/mod.py::function::unused_function occurs 2x" in out
    assert "raise the count by hand" in out


def test_init_refuses_malformed_baseline(tmp_path, monkeypatch, capsys):
    make_project(tmp_path, monkeypatch)
    (tmp_path / "ratchet-baseline.toml").write_text(
        '[vulture]\n[[vulture.entry]]\nkey = "k"\nreasn = "typo"\n'
    )
    assert main(["init", "src"]) == 1
    err = capsys.readouterr().err
    assert "malformed baseline" in err
    assert "Fix the baseline by hand" in err


def test_init_does_not_overwrite_existing_test_file(tmp_path, monkeypatch, capsys):
    make_project(tmp_path, monkeypatch)
    (tmp_path / "test_ratchet.py").write_text("# custom guard, hands off\n")
    assert main(["init", "src"]) == 0
    assert (tmp_path / "test_ratchet.py").read_text() == "# custom guard, hands off\n"
    assert "left untouched" in capsys.readouterr().out


def test_init_end_to_end_with_pytest(pytester):
    """The 15-minute story: init -> pytest green; fix the dead code without
    touching the baseline -> pytest red with STALE."""
    src = pytester.path / "src"
    src.mkdir()
    (src / "mod.py").write_text(DEAD_CODE)

    assert main(["init", "src"]) == 0  # pytester has already chdir'd into path

    result = pytester.runpytest()
    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(["*section [[]vulture[]]: 1 entry OK, 1 TODO*"])

    (src / "mod.py").write_text("")  # debt paid, baseline now lies
    result = pytester.runpytest()
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*STALE*", "*src/mod.py::function::unused_function*"])
