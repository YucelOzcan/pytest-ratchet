"""Plane ticket tracker: is the work item a reason cites still open?

Talks to Plane's REST API v1 (self-hosted CE or cloud) with the standard
library only — no extra dependency for a feature most projects will not use.

Configuration, constructor arguments first, environment second:

    PLANE_BASE_URL         e.g. https://plane.example.com
    PLANE_API_KEY          a personal API token (Settings → API tokens)
    PLANE_WORKSPACE_SLUG   the workspace the ticket ids belong to

"Closed" means the item's state group is ``completed`` or ``cancelled`` —
a cancelled ticket kills a reason just as thoroughly as a finished one.

Every failure to answer (no token, network, HTTP error, unknown id) returns
``None`` — never a guess in either direction — and is explained in the
report. Under ``ratchet_ticket_strict`` that ``None`` is red.

pytest.ini::

    ratchet_ticket_tracker = pytest_ratchet.adapters.plane:PlaneTracker
    ratchet_ticket_strict = true      # recommended in CI
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

CLOSED_GROUPS = frozenset({"completed", "cancelled"})

_urlopen = urllib.request.urlopen  # module attribute so tests can replace it


class PlaneUnavailable(RuntimeError):
    """Plane could not be asked (network, HTTP, malformed response)."""


class PlaneTracker:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        workspace: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.base_url = (base_url or os.environ.get("PLANE_BASE_URL") or "").rstrip("/")
        self.api_key = api_key or os.environ.get("PLANE_API_KEY") or ""
        self.workspace = workspace or os.environ.get("PLANE_WORKSPACE_SLUG") or ""
        self.timeout = float(timeout)
        self._items: dict[str, dict[str, Any] | None] = {}
        self._states: dict[str, dict[str, tuple[str, str]]] = {}  # project -> state id -> (name, group)
        self._notes: dict[str, str] = {}

    # -- TicketTracker protocol --------------------------------------------

    def is_open(self, ticket_id: str) -> bool | None:
        missing = [
            name
            for name, value in (
                ("PLANE_BASE_URL", self.base_url),
                ("PLANE_API_KEY", self.api_key),
                ("PLANE_WORKSPACE_SLUG", self.workspace),
            )
            if not value
        ]
        if missing:
            self._notes[ticket_id] = f"{', '.join(missing)} not set"
            return None
        try:
            item = self._work_item(ticket_id)
            if item is None:
                self._notes[ticket_id] = "not found in Plane"
                return None
            name, group = self._state_of(item)
        except PlaneUnavailable as exc:
            self._notes[ticket_id] = str(exc)
            return None
        self._notes[ticket_id] = f"state {name} ({group})" if group else f"state {name}"
        return group not in CLOSED_GROUPS

    def explain(self, ticket_id: str) -> str | None:
        return self._notes.get(ticket_id)

    # -- Plane REST ----------------------------------------------------------

    def _work_item(self, ticket_id: str) -> dict[str, Any] | None:
        if ticket_id not in self._items:
            data = self._get(f"work-items/{ticket_id}/")
            self._items[ticket_id] = data if isinstance(data, dict) else None
        return self._items[ticket_id]

    def _state_of(self, item: dict[str, Any]) -> tuple[str, str]:
        project = str(item.get("project") or "")
        state = str(item.get("state") or "")
        if project not in self._states:
            data = self._get(f"projects/{project}/states/")
            results = data.get("results", data) if isinstance(data, dict) else data
            if not isinstance(results, list):
                raise PlaneUnavailable(f"unexpected states payload for project {project}")
            self._states[project] = {
                str(s.get("id")): (str(s.get("name", "?")), str(s.get("group", "")))
                for s in results
                if isinstance(s, dict)
            }
        try:
            return self._states[project][state]
        except KeyError:
            raise PlaneUnavailable(f"state {state or '?'} not in project {project} states") from None

    def _get(self, path: str) -> Any:
        url = f"{self.base_url}/api/v1/workspaces/{self.workspace}/{path}"
        request = urllib.request.Request(url, headers={"X-API-Key": self.api_key})
        try:
            with _urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise PlaneUnavailable(f"HTTP {exc.code} from {url}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise PlaneUnavailable(f"{exc} ({url})") from exc
        except ValueError as exc:  # not JSON
            raise PlaneUnavailable(f"non-JSON response from {url}: {exc}") from exc
