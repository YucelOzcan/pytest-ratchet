# Core primitive design

Status: draft, 2026-08-11. Covers the v1 core primitive only: the baseline
file format, the matching key, and the enforcement semantics. `ratchet init`,
the resolver protocol, and reachability recipes are designed separately.

Every decision here traces back to a failure mode documented in
[prior-art.md](prior-art.md). Those lessons are cited inline as
**[lesson: …]**.

## Concepts

- **Finding** — one item reported by a scanner, normalized by an adapter:
  a `kind` (e.g. `unused-function`) and a stable `key` identifying *what*
  the finding is about (not *where* it currently sits).
- **Baseline entry** — one accepted finding, recorded with a required
  human-written `reason`.
- **Scanner section** — entries are grouped per scanner, so multiple
  scanners can share one baseline file without key collisions.

## Decision 1 — file format: TOML, in a dedicated `.ratchet.toml`

```toml
# .ratchet.toml — every entry needs a reason; stale entries fail the run.

[vulture]

[[vulture.entry]]
key = "pbx/handlers.py::function::on_hangup"
reason = "dispatched dynamically by event name; vulture cannot see the call"
added = 2026-08-11

[[vulture.entry]]
key = "pbx/models.py::attribute::legacy_id"
reason = "TODO"
added = 2026-08-11
```

Why TOML:

- Readable and writable by stdlib (`tomllib`, Python ≥3.11) — no runtime
  dependency for the check path.
- **Comments are legal.** ESLint's bulk suppressions have *no annotation
  channel at all* because they chose bare JSON **[lesson: ESLint]**. Our
  reason lives in a field, but TOML comments additionally let teams annotate
  freely.
- Merge-friendly: one entry per `[[table]]` block diffs and conflicts at
  entry granularity, similar in spirit to mypy-baseline's
  one-line-per-error design.

Why a dedicated file (not `pyproject.toml`): the baseline changes at a
different cadence than project metadata, and review should see baseline
churn in isolation. The path is configurable; `.ratchet.toml` is the default.

**The file is human-owned and never regenerated wholesale.** Psalm and
RuboCop rewrite their files from scratch, so hand-written text cannot
survive; that mechanical fact is *why* those formats carry no reasons
**[lesson: Psalm, RuboCop]**. pytest-ratchet has no operation that rewrites
the file. `ratchet init` (designed separately) only creates or appends
entries; removal is always a human edit.

## Decision 2 — matching key: adapter-provided identity, no line numbers

A finding's key is built by the scanner adapter from stable coordinates:

```
<path>::<kind-specific identity>
e.g.  pbx/handlers.py::function::on_hangup
```

- **No line numbers, no column numbers.** Lines shift; identity-by-position
  goes stale on unrelated edits. PHPStan rejected line numbers for exactly
  this reason ("the line information could get obsolete and the build would
  fail when the line with error shifts") **[lesson: PHPStan]**, and
  betterer's position+hash tracking is what forces its results file to be
  machine-maintained **[lesson: betterer]**. Live positions still appear in
  *error messages* (taken from the current scan), just never in identity.
- **Set semantics, not counts.** The check computes two set differences per
  scanner section:
  - `findings - baseline` → **new findings** → fail.
  - `baseline - findings` → **stale entries** → fail.
  ESLint tracks per-file-per-rule *counts*, so fixing one violation while
  introducing a different one of the same rule in the same file passes
  silently **[lesson: ESLint]**. Symbol-level keys close that hole: the
  fixed finding goes stale (red) and the new one is new (red).
- **`count` exists only for true duplicates**, defaults to 1, and is exact.
  When a scanner genuinely reports the same identity twice (two unused
  variables named `x` in different functions of one file), the entry says
  `count = 2`. Actual > recorded fails as new; actual < recorded fails as
  stale — count decay is a failure, as in PHPStan **[lesson: PHPStan]**.
- Adapters own key stability. The contract: *renaming or moving the flagged
  symbol may invalidate the key; edits elsewhere in the file must not.*

## Decision 3 — the reason field

- `reason` is **required and must be non-empty**. A missing or empty reason
  is a baseline *format error* that fails the run — the analog of PHPStan's
  `reportIgnoresWithoutComments`, applied where PHPStan refuses to apply it:
  inside the baseline artifact **[lesson: PHPStan doctrine]**.
- `reason = "TODO"` is legal and deliberately cheap to write — `ratchet
  init` seeds it. TODO reasons are surfaced in every run's summary
  (`3 entries still have reason TODO`) so unexamined debt stays visible
  without blocking adoption. A strict mode can escalate TODO to failure
  later; v1 only reports.
- `added` (a TOML date) is optional but seeded by init — it costs nothing
  and answers "how long have we been carrying this?" in review.
- Justification is per *entry*, not per scanner or per run — the exact
  granularity SonarQube offers optionally and off-repo, made required and
  committed **[lesson: SonarQube]**.

## Enforcement semantics

Two failure classes, one report format, both red:

```
RATCHET: 2 problems in section [vulture]

  NEW (not in baseline — fix it or add it with a reason):
    pbx/api.py::function::export_csv   (vulture: unused function, line 214)

  STALE (in baseline but no longer found — delete the entry):
    pbx/models.py::attribute::legacy_id
      reason was: "TODO"
```

- **Stale failures cannot be suppressed.** There is no flag that tolerates a
  stale entry; the only fix is deleting it. PHPStan marks its unmatched-entry
  error `canBeIgnored: false` for the same reason — an escape hatch here
  would let the baseline lie again **[lesson: PHPStan]**. ESLint's
  `--pass-on-unpruned-suppressions` is the cautionary opposite
  **[lesson: ESLint]**.
- **No bulk-accept operation.** There is deliberately no `--update` that
  absorbs current findings into the baseline: betterer's `--update` and
  RuboCop's `--regenerate-todo` both re-baseline regressions wholesale
  **[lessons: betterer, RuboCop]**. Accepting a new finding means writing
  an entry — with a reason — by hand (or via init on first adoption).
- Messages always show the remedy in the failure text, because the failure
  fires in CI where nobody reads docs first.

## pytest integration (v1 shape)

The primitive is a library function plus a thin pytest layer:

```python
# ratchet/core.py — no pytest dependency
check(section: str, findings: Iterable[Finding], baseline: Baseline) -> Report

# test_ratchet.py — what a user writes
def test_dead_code(ratchet):
    ratchet.check("vulture", vulture_findings())
```

- `ratchet` is a fixture that loads `.ratchet.toml` once per session and
  fails the test with the report above.
- One test per scanner section keeps failures separately selectable
  (`pytest -k vulture`) and lets teams adopt scanners independently.
- Core stays pytest-free so the same primitive can back a CLI later.

## Out of scope for v1 (recorded so they're deliberate)

- Pin-alignment checks (withdrawn 2026-08-10; not a ratchet).
- Deadlines/expiry dates on entries, strict-TODO mode, per-entry owners.
- Any operation that edits the baseline besides `ratchet init` append.
