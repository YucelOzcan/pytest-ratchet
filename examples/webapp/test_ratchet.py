"""Ratchet guards for the example webapp: one scanner + two resolvers.

Run from the repository root:  pytest examples/webapp
See README.md in this directory for the walkthrough.
"""

import re
from pathlib import Path

from pytest_ratchet import Finding, unreachable_findings
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


MANIFEST = HERE / "SCRIPTS.md"
SCRIPTS = HERE / "scripts"

# The manifest's two sections, and where a script must live to belong to each.
CATEGORIES = {"Active": SCRIPTS, "Archived": SCRIPTS / "archive"}


def manifest_entries() -> dict[str, str]:
    """{script name: section title} as documented in SCRIPTS.md."""
    entries, section = {}, None
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
        elif line.startswith("- `") and section:
            entries[line.split("`")[1]] = section
    return entries


def scripts_on_disk() -> dict[str, str]:
    """{script name: section it belongs to, judged by directory}."""
    return {
        path.name: section
        for section, directory in CATEGORIES.items()
        for path in directory.glob("*.py")
    }


class UnlistedScriptResolver:
    """Scripts on disk that the manifest never mentions."""

    kind = "unlisted-script"

    def candidates(self):
        return set(scripts_on_disk())

    def reachable(self):
        return set(manifest_entries())


class GhostScriptResolver:
    """Manifest lines with no script behind them — the mirror image.

    This is the direction people forget. It is NOT covered by the baseline's
    staleness check: staleness asks "is this accepted finding still real?",
    while this asks "is this documented script still real?" Different
    question, so it needs its own resolver with the roles swapped.
    """

    kind = "ghost-script"

    def candidates(self):
        return set(manifest_entries())

    def reachable(self):
        return set(scripts_on_disk())


def misfiled_findings() -> list[Finding]:
    """Scripts documented under the wrong section.

    Deliberately not a resolver: both sides agree the script exists, so
    nothing is unreachable. It is a third shape — the sets match but a
    property disagrees — and the baseline manages it just the same.
    """
    disk, documented = scripts_on_disk(), manifest_entries()
    return [
        Finding(
            kind="misfiled-script",
            key=name,
            message=f"lives under {disk[name]}, documented under {documented[name]}",
        )
        for name in sorted(disk.keys() & documented.keys())
        if disk[name] != documented[name]
    ]


def test_dead_code(ratchet):
    ratchet.check("vulture", vulture_findings([HERE / "app"], root=HERE))


def test_orphan_templates(ratchet):
    ratchet.check("templates", unreachable_findings(TemplateResolver()))


def test_unmounted_handlers(ratchet):
    ratchet.check("handlers", unreachable_findings(HandlerResolver()))


def test_scripts_are_all_documented(ratchet):
    ratchet.check("scripts-unlisted", unreachable_findings(UnlistedScriptResolver()))


def test_manifest_has_no_ghosts(ratchet):
    ratchet.check("scripts-ghost", unreachable_findings(GhostScriptResolver()))


def test_scripts_are_filed_correctly(ratchet):
    ratchet.check("scripts-misfiled", misfiled_findings())
