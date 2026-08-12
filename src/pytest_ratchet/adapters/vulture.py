"""Vulture adapter: dead-code findings, keyed by symbol, not by line.

Key shape: <relative-posix-path>::<typ>::<name>
e.g. src/pbx/handlers.py::function::on_hangup

Line numbers appear in messages only — identity must survive unrelated edits
(docs/design.md, Decision 2).
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from pytest_ratchet.adapters import ScannerUnavailableError
from pytest_ratchet.core import Finding


def vulture_findings(
    paths: Sequence[str | Path],
    *,
    min_confidence: int = 0,
    exclude: Sequence[str] = (),
    root: str | Path | None = None,
) -> list[Finding]:
    """Run vulture over `paths` and normalize its findings.

    `root` (default: cwd) anchors the relative paths used in keys, so the
    same baseline matches regardless of where the checkout lives.
    """
    try:
        from vulture import Vulture
    except ImportError as exc:
        raise ScannerUnavailableError(
            "vulture is not installed, so the dead-code ratchet cannot run "
            "(skipping here would silently disable the baseline). "
            "Install it: pip install vulture"
        ) from exc

    root_path = (Path(root) if root is not None else Path.cwd()).resolve()
    scanner = Vulture(verbose=False)
    scanner.scavenge([str(p) for p in paths], exclude=list(exclude) or None)

    findings: list[Finding] = []
    for item in scanner.get_unused_code(min_confidence=min_confidence):
        path = Path(str(item.filename)).resolve()
        try:
            path = path.relative_to(root_path)
        except ValueError:
            pass  # outside root: keep the path as vulture reported it
        findings.append(
            Finding(
                kind=str(item.typ),
                key=f"{path.as_posix()}::{item.typ}::{item.name}",
                message=str(item.message),
                line=int(item.first_lineno),
            )
        )
    return findings
