# Core primitive design

Status: draft, 2026-08-11; revised same day after external review. Covers
the v1 core primitive only: the baseline file format, the matching key, and
the enforcement semantics. `ratchet init`, the resolver protocol, and
reachability recipes are designed separately.

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

## Decision 1 — file format: TOML, in a dedicated `ratchet-baseline.toml`

```toml
# ratchet-baseline.toml — every entry needs a reason; stale entries fail the run.

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
churn in isolation. Why a *visible* name and not a dotfile: this file is a
human-owned artifact that pull requests are supposed to look at; the dotfile
convention signals "tool config, ignore me", which is the opposite of the
product's thesis. PHPStan's visible `phpstan-baseline.neon` sets the
precedent. The path is configurable; `ratchet-baseline.toml` is the default.

**The file is human-owned and never regenerated wholesale.** Psalm and
RuboCop rewrite their files from scratch, so hand-written text cannot
survive; that mechanical fact is *why* those formats carry no reasons
**[lesson: Psalm, RuboCop]**. pytest-ratchet has no operation that rewrites
the file. `ratchet init` (designed separately) only creates or appends
entries; removal is always a human edit. Consequence for init: since stdlib
has no TOML *writer* (`tomllib` is read-only), init will do **plain-text
block appends** — no TOML-writing dependency, and mechanically incapable of
rewriting what a human wrote. This falls straight out of the
never-regenerate rule.

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
- **The tension, owned explicitly:** `reason = "TODO"` is legal, so what is
  required is the *field*, not yet a considered justification. This is a
  deliberate adoption trade-off, not a loophole we hope nobody notices:
  `ratchet init` must be able to seed a legacy codebase without demanding a
  hundred essays up front, and a forbidden placeholder would only produce a
  hundred fake reasons ("legacy", "old code"), which are TODOs that *can't*
  be counted. TODO is the honest placeholder: machine-recognizable,
  reported on every run, impossible to mistake for a decision. All public
  claim language follows this: "required reason field; TODO tolerated and
  surfaced", never "every entry is justified".
- **`strict_todo` ships in v1**, opt-in: with it enabled, a TODO reason
  fails the run like any other format error. Teams that want to force the
  essays can, from day one; "strict mode later" would be a weaker answer.
- Every run's summary reports TODO debt with its age:
  `2 TODO entries (oldest: 45 days)` — computed from `added`, so
  visibility pressure grows on its own.
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
- Report output is **deterministically ordered** (sorted by key within each
  class) so CI logs diff cleanly between runs.
- **Green runs are not silent.** A passing check prints one summary line —
  `section [vulture]: 12 entries OK, 2 TODO (oldest: 45 days)` — because an
  invisible success is indistinguishable from a check that didn't run.

## No silent green: edge behaviors

The failure mode this tool exists to kill is the check that quietly stops
checking. Three edge cases are therefore defined behavior, not accidents:

- **Scanner unavailable → failure, never skip.** If the adapter cannot run
  its scanner (vulture not installed, binary missing), the check **fails**
  with an install remedy. A skip would turn CI green while the baseline is
  effectively disabled — the exact silent-config-rollback wound this
  project was born from.
- **Baseline file missing → empty baseline, with guidance.** All current
  findings are reported as NEW (correct: nothing has been accepted), and
  the failure text recommends `ratchet init` for first-time setup. Not an
  error class of its own — a greenfield project with zero findings and no
  baseline file passes, by design.
- **Malformed baseline → format error, fail.** Duplicate keys within a
  section (legal TOML, human-producible) are a hard failure — there is no
  "first one wins". Unknown fields on an entry fail too: a typo like
  `reasn = "..."` must not silently degrade an entry (the missing `reason`
  check would catch that case anyway, but strict schema is cheap and
  catches typos in optional fields as well).

## Adapter contract (pointer)

Adapters are designed in the init/integration doc, not here; the primitive
only fixes the boundary:

- A `Finding` carries `kind`, `key`, and optional display-only context
  (message, current line number) that never participates in matching.
- Keys use `/` as the path separator on every platform — adapters
  normalize, so a baseline written on Linux matches on Windows.
- The `vulture_findings()` in the sketch below is a placeholder for that
  future adapter API; v1 ships exactly one real adapter (vulture).

## pytest integration (v1 shape)

The primitive is a library function plus a thin pytest layer:

```python
# pytest_ratchet/core.py — no pytest dependency
# (import package is pytest_ratchet: the bare `ratchet` name is already a
#  distribution on PyPI, so claiming its module namespace risks collision)
check(section: str, findings: Iterable[Finding], baseline: Baseline) -> Report

# test_ratchet.py — what a user writes
def test_dead_code(ratchet):
    ratchet.check("vulture", vulture_findings())
```

- `ratchet` is a fixture that loads `ratchet-baseline.toml` once per session
  and fails the test with the report above. Loading is read-only, so
  pytest-xdist workers each loading their own copy is harmless.
- One test per scanner section keeps failures separately selectable
  (`pytest -k vulture`) and lets teams adopt scanners independently.
- `strict_todo` is exposed as a pytest ini option; the core takes it as a
  plain argument.
- Core stays pytest-free so the same primitive can back a CLI later.

## ratchet init (v1, as implemented)

`ratchet init <paths>` gives the 15-minute adoption path: run vulture, seed
the baseline, scaffold the guard test.

- **Append-only, mechanically.** Creates `ratchet-baseline.toml` (with a
  header explaining the contract) or appends `[[vulture.entry]]` blocks for
  findings not yet listed. It parses the existing file only to *read* it
  (stdlib `tomllib`); writing is plain-text block append, so it cannot
  reorder, reformat, or delete anything a human wrote — re-running init on a
  covered project leaves the file byte-identical.
- Seeds `reason = "TODO"` and `added = <today>`; real duplicates get
  `count = N`.
- **Never edits existing entries.** If a key already in the baseline now
  occurs more often than its recorded count, init warns and leaves the entry
  alone — accepting more debt is a human edit, even during seeding.
- **Self-check:** after writing, init reloads the baseline through the same
  strict loader pytest uses; init must never write a file that fails to load.
- Scaffolds `test_ratchet.py` (vulture section, scanned paths baked in) only
  if the file does not exist; refuses to touch an existing one.
- A malformed existing baseline aborts init with the loader's error — seeding
  into a broken file would bury the breakage.

## Out of scope for v1 (recorded so they're deliberate)

- Pin-alignment checks (withdrawn 2026-08-10; not a ratchet).
- Deadlines/expiry dates on entries, per-entry owners.
- Any operation that edits the baseline besides `ratchet init` append.
