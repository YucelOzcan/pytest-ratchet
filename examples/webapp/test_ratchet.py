"""Ratchet guards for the example webapp: one scanner + two resolvers.

Run from the repository root:  pytest examples/webapp
See README.md in this directory for the walkthrough.
"""

import re
from pathlib import Path

from pytest_ratchet import unreachable_findings
from pytest_ratchet.adapters.vulture import vulture_findings

from app import handlers, routes

HERE = Path(__file__).parent


class TemplateResolver:
    """Orphan templates: every template on disk must be render()'ed somewhere.

    Templates are loaded by *name string* at runtime, so no static tool can
    tell a live template from a dead one. The resolver states both sides.
    """

    kind = "orphan-template"

    def candidates(self):
        return {p.name for p in (HERE / "app" / "templates").glob("*.html")}

    def reachable(self):
        source = "\n".join(
            p.read_text(encoding="utf-8") for p in (HERE / "app").glob("*.py")
        )
        return set(re.findall(r'render\(\s*"([^"]+)"\s*\)', source))


class HandlerResolver:
    """Unmounted handlers: every handle_* function must appear in ROUTES.

    routes.dispatch() resolves handlers with getattr(handlers, name) — a
    handler missing from ROUTES is unreachable, and vulture cannot know.
    """

    kind = "unmounted-handler"

    def candidates(self):
        return {name for name in vars(handlers) if name.startswith("handle_")}

    def reachable(self):
        return set(routes.ROUTES.values())


def test_dead_code(ratchet):
    ratchet.check("vulture", vulture_findings([HERE / "app"], root=HERE))


def test_orphan_templates(ratchet):
    ratchet.check("templates", unreachable_findings(TemplateResolver()))


def test_unmounted_handlers(ratchet):
    ratchet.check("handlers", unreachable_findings(HandlerResolver()))
