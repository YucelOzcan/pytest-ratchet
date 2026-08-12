import pytest

from pytest_ratchet.resolve import ResolverError, unreachable_findings


class FakeResolver:
    kind = "orphan-template"

    def __init__(self, candidates, reachable):
        self._candidates = candidates
        self._reachable = reachable

    def candidates(self):
        return self._candidates

    def reachable(self):
        return self._reachable


def test_unreachable_candidates_become_findings():
    findings = unreachable_findings(
        FakeResolver({"a.html", "b.html", "c.html"}, {"b.html"})
    )
    assert [f.key for f in findings] == ["a.html", "c.html"]  # sorted
    assert findings[0].kind == "orphan-template"
    assert "never reached" in findings[0].message


def test_everything_reachable_yields_nothing():
    assert unreachable_findings(FakeResolver({"a"}, {"a"})) == []


def test_phantom_reachables_are_ignored():
    # reachable sets are often wider (builtins, third-party names)
    assert unreachable_findings(FakeResolver({"a"}, {"a", "not-a-candidate"})) == []


def test_zero_candidates_fails_never_guards_nothing():
    with pytest.raises(ResolverError, match="zero candidates"):
        unreachable_findings(FakeResolver(set(), set()))


def test_zero_candidates_can_be_allowed_explicitly():
    assert unreachable_findings(FakeResolver(set(), set()), allow_empty=True) == []
