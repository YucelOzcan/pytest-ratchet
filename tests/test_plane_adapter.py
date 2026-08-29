"""PlaneTracker against a scripted Plane REST API (no network)."""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from pytest_ratchet.adapters import plane
from pytest_ratchet.adapters.plane import PlaneTracker
from pytest_ratchet.tickets import TicketTracker

STATES = {
    "s-backlog": {"id": "s-backlog", "name": "Backlog", "group": "backlog"},
    "s-done": {"id": "s-done", "name": "Done", "group": "completed"},
    "s-cancel": {"id": "s-cancel", "name": "Cancelled", "group": "cancelled"},
    "s-started": {"id": "s-started", "name": "In Progress", "group": "started"},
}

ITEMS = {
    "DAC-1": {"id": "i1", "project": "p1", "state": "s-backlog"},
    "DAC-2": {"id": "i2", "project": "p1", "state": "s-done"},
    "DAC-3": {"id": "i3", "project": "p1", "state": "s-cancel"},
    "DAC-4": {"id": "i4", "project": "p2", "state": "s-started"},
}


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class FakePlane:
    """Routes URLs like Plane v1 does and counts requests per path."""

    def __init__(self, fail: dict[str, Exception] | None = None):
        self.calls: list[str] = []
        self.fail = fail or {}

    def __call__(self, request, timeout):
        url = request.full_url
        assert request.get_header("X-api-key") == "secret", request.header_items()
        assert timeout == pytest.approx(10.0) or timeout == pytest.approx(3.0)
        path = url.split("/api/v1/workspaces/ws/", 1)[1]
        self.calls.append(path)
        if path in self.fail:
            raise self.fail[path]
        if path.startswith("work-items/"):
            ident = path.split("/")[1]
            if ident not in ITEMS:
                raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
            body = ITEMS[ident]
        elif path.startswith("projects/") and path.endswith("/states/"):
            body = {"results": list(STATES.values())}
        else:
            raise AssertionError(f"unexpected path {path}")
        return FakeResponse(json.dumps(body).encode())


@pytest.fixture
def api(monkeypatch):
    fake = FakePlane()
    monkeypatch.setattr(plane, "_urlopen", fake)
    return fake


def tracker(**kwargs) -> PlaneTracker:
    return PlaneTracker(base_url="https://plane.test/", api_key="secret", workspace="ws", **kwargs)


def test_satisfies_the_protocol():
    assert isinstance(tracker(), TicketTracker)


def test_open_states_are_open(api):
    t = tracker()
    assert t.is_open("DAC-1") is True
    assert t.explain("DAC-1") == "state Backlog (backlog)"
    assert t.is_open("DAC-4") is True
    assert t.explain("DAC-4") == "state In Progress (started)"


def test_completed_and_cancelled_are_closed(api):
    t = tracker()
    assert t.is_open("DAC-2") is False
    assert t.explain("DAC-2") == "state Done (completed)"
    assert t.is_open("DAC-3") is False
    assert t.explain("DAC-3") == "state Cancelled (cancelled)"


def test_states_are_fetched_once_per_project(api):
    t = tracker()
    for ident in ("DAC-1", "DAC-2", "DAC-3", "DAC-1"):
        t.is_open(ident)
    assert api.calls.count("projects/p1/states/") == 1
    assert api.calls.count("work-items/DAC-1/") == 1  # item cached too
    t.is_open("DAC-4")
    assert api.calls.count("projects/p2/states/") == 1


def test_unknown_ticket_is_none_with_a_reason(api):
    t = tracker()
    assert t.is_open("DAC-999") is None
    assert t.explain("DAC-999") == "not found in Plane"


def test_network_error_is_none_never_a_guess(monkeypatch):
    fake = FakePlane(fail={"work-items/DAC-1/": urllib.error.URLError("timed out")})
    monkeypatch.setattr(plane, "_urlopen", fake)
    t = tracker()
    assert t.is_open("DAC-1") is None
    assert "timed out" in (t.explain("DAC-1") or "")


def test_http_error_other_than_404_is_none(monkeypatch):
    fake = FakePlane(
        fail={"work-items/DAC-1/": urllib.error.HTTPError("u", 503, "Service Unavailable", {}, None)}
    )
    monkeypatch.setattr(plane, "_urlopen", fake)
    t = tracker()
    assert t.is_open("DAC-1") is None
    assert t.explain("DAC-1") == "HTTP 503 from https://plane.test/api/v1/workspaces/ws/work-items/DAC-1/"


def test_missing_credentials_is_none_and_says_which(monkeypatch):
    for var in ("PLANE_BASE_URL", "PLANE_API_KEY", "PLANE_WORKSPACE_SLUG"):
        monkeypatch.delenv(var, raising=False)
    t = PlaneTracker()
    assert t.is_open("DAC-1") is None
    assert t.explain("DAC-1") == "PLANE_BASE_URL, PLANE_API_KEY, PLANE_WORKSPACE_SLUG not set"


def test_environment_fills_the_gaps(monkeypatch, api):
    monkeypatch.setenv("PLANE_BASE_URL", "https://plane.test")
    monkeypatch.setenv("PLANE_API_KEY", "secret")
    monkeypatch.setenv("PLANE_WORKSPACE_SLUG", "ws")
    assert PlaneTracker().is_open("DAC-2") is False


def test_timeout_is_passed_through(api):
    assert tracker(timeout=3).is_open("DAC-1") is True
    assert tracker().timeout == 10.0
