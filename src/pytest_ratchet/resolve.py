"""Resolver protocol: reachability guards for runtime-resolved references.

Static scanners cannot see dynamic resolution: templates loaded by name,
handlers mounted from a routes table, plugins picked from config. A Resolver
states the two sides that the code cannot state for itself:

    candidates() -- everything that exists
    reachable()  -- everything the runtime resolution can actually reach

Whatever exists but is never reached is a finding, and the ratchet manages it
like any scanner finding: accepted with a reason, or red.

Guided, not automatic (docs/design.md): you write the resolver, because only
you know how your project resolves names. examples/webapp has working recipes.
"""

from __future__ import annotations

from typing import Iterable, Protocol, runtime_checkable

from pytest_ratchet.core import Finding


class ResolverError(RuntimeError):
    """The resolver itself looks broken. Fail, never guess."""


@runtime_checkable
class Resolver(Protocol):
    kind: str

    def candidates(self) -> Iterable[str]: ...

    def reachable(self) -> Iterable[str]: ...


def unreachable_findings(resolver: Resolver, *, allow_empty: bool = False) -> list[Finding]:
    """Findings for every candidate the resolution never reaches.

    Items in reachable() that are not candidates are ignored: reachable sets
    are often naturally wider (builtins, third-party names). An *empty*
    candidate set fails instead — a guard that sees nothing guards nothing,
    and the usual cause is a wrong path or glob, not a clean project. Pass
    allow_empty=True when zero candidates is genuinely valid.
    """
    candidates = set(resolver.candidates())
    if not candidates and not allow_empty:
        raise ResolverError(
            f"resolver {type(resolver).__name__} produced zero candidates — "
            "wrong path or glob? Pass allow_empty=True if an empty candidate "
            "set is genuinely valid here."
        )
    reachable = set(resolver.reachable())
    return [
        Finding(
            kind=resolver.kind,
            key=key,
            message=f"{resolver.kind}: exists but is never reached",
        )
        for key in sorted(candidates - reachable)
    ]
