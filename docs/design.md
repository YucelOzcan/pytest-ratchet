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

## Resolver protocol (v1, as implemented)

Reachability guards for what no scanner can see: references resolved at
runtime (templates by filename, handlers by name from a routes table, plugin
classes from config). Guided, not automatic — the user writes the resolver,
because only they know how their project resolves names.

- A resolver is any object with `kind: str`, `candidates() -> Iterable[str]`
  (everything that exists) and `reachable() -> Iterable[str]` (everything
  the runtime resolution actually reaches). `unreachable_findings(resolver)`
  turns `candidates - reachable` into ordinary `Finding`s, so the baseline
  manages them exactly like scanner output.
- **Reachability is the special case, not the ceiling.** The general shape
  the primitive serves is *two sources describing the same fact, and whether
  they still agree*: code versus runtime resolution, directory versus
  manifest, config versus what reads it. A resolver expresses that when the
  disagreement is "exists but is never reached"; when it is a mismatched
  property rather than an absence, skip the resolver and return `Finding`s
  directly — the baseline does not care which produced them. The manifest
  recipe in `examples/webapp` demonstrates all three: mirrored resolvers for
  the two absence directions, and a plain function for the property
  mismatch.
- **Zero candidates is an error**, not an empty result: the usual cause is a
  wrong path or glob, and a guard that sees nothing guards nothing
  (no-silent-green). `allow_empty=True` opts out where genuinely valid.
- Extra `reachable()` items are ignored — reachable sets are naturally wider
  (builtins, third-party names).
- A broken resolver is additionally caught by the ratchet itself: if
  candidates vanish because a path moved, every existing baseline entry for
  that section goes STALE and the run turns red.
- `examples/webapp` is the runnable recipe set: dynamic `getattr` dispatch
  that vulture flags wholesale (accepted with reasons), plus two resolvers —
  orphan templates and unmounted handlers — including the case where the
  vulture entry is legitimately accepted while the resolver still finds the
  real problem.

## Findings from first production dogfooding (2026-08-12)

Ran against a real 238-module backend alongside its hand-written dead-code
ratchet. The adapter reproduced the existing baseline exactly (5/5, no extra,
no missing) and runtime was indistinguishable (1.60s vs 1.59s — both
dominated by the vulture scan). What the exercise surfaced:

- **The probe trap** (most important). Our own "prove the gate" advice walks
  users into a silent green: a probe like `import json` is absorbed by
  vulture's whole-corpus name analysis, so the guard stays green and the user
  believes the gate was proven. Documented in README with the unique-name
  fix. **A `ratchet probe` subcommand** — inject, verify red, revert — is the
  machine-checked version of that advice and the natural v1.1 feature; it is
  deliberately not v1 because writing to a user's source tree deserves its
  own design pass. **Its central requirement, learned from the incident:
  uniqueness must be verified, not assumed** — the command must search the
  target corpus for its candidate name and pick another if it occurs,
  because "this name is surely unique" is exactly the human intuition that
  failed. A random suffix alone is not enough; the search is the point.
  **Second constraint, found by a stress test in the same project:** the
  generated name must also not appear in any existing baseline entry. A probe
  that reuses a recorded name can *remove* that finding — adding code in one
  file made an unused import in another file stop being reported, and the run
  failed with STALE instead of NEW. The probe must not be able to heal the
  thing it is testing.
- **`--added` shipped**: inherited baselines need the real acceptance date,
  not today's, or the TODO-age report lies from day one.
- **Numeric budgets are a genuine gap**: an entry carrying an allowed value
  (max function length, cap on total entries) is a third class — neither new
  nor stale, but *over budget*. One guard of the eleven in that project
  cannot migrate because of it. Recorded as a known limit; if it ships it is
  a separate verb, not a stretched set difference.
- **Adoption forces a skip one level up**: before the plugin is a pinned
  dependency, `pytest.importorskip` is the practical wrapper — and that makes
  the guard pass silently, the exact thing the primitive forbids one layer
  down. Concrete argument for prioritizing the PyPI release.
- **Reasons now sit apart from the guard's thresholds**, unlike an inline
  dict. A real trade-off of the file-based design, recorded rather than
  argued away.
- **Wanted: a `tag`/class field** on entries (permanent accepted pattern vs
  temporary debt), which would let the summary report them separately.

### Planned next migration (deferred on purpose)

That project's provider-abstraction guard — the one-directional one, its
`ALLOWED_EXCEPTIONS` a plain set with no staleness check — is portable:
findings take the shape `<pipeline-file>::forbidden-import::<module>`, no
numeric budget involved. Migrating it is not a port but a *repair*: the
second direction arrives for free.

It is deliberately **not** being done before the PyPI release. Until the
plugin is a pinned dependency, the migrated guard must sit behind
`pytest.importorskip` and would therefore skip silently in CI — trading a
one-directional guard that *runs* for a bidirectional one that *doesn't*.
A net loss, and exactly the adoption tension recorded in the README limits.

## Reason liveness — CLOSED_TICKET (v0.2, as implemented)

**The gap.** A reason that cites a ticket ("DAC-355: fix once the parser
grows") is a claim about a tracker. It goes false when the ticket closes,
and neither direction of the set difference can see it: the finding is still
present (not NEW), the entry is still present (not STALE). Field evidence
(2026-08-29, the dogfooding project): a ticket was set Done on 2026-08-08
without a fix; the cases it justified stayed accepted for three weeks; only a
hand-written test that asked the tracker caught it. That test was the
reference implementation for this feature.

**Shape.** A third question in `core.check`, behind a `tracker` argument:

- `TicketTracker` protocol, one method: `is_open(ticket_id) -> bool | None`.
  Named *tracker*, not *resolver* — `Resolver` already means reachability.
  Optional, display-only `explain(ticket_id) -> str`.
- Convention: tickets are cited by the **leading** ids of the reason —
  `DAC-355: …` or `DAC-355, DAC-360: …` (all must be open). Ids elsewhere in
  the text are prose. The pattern (`ratchet_ticket_pattern`) is anchored at
  the start even if the user forgets the `^`; an unanchored pattern would
  turn every mention into a claim.
- Closed = tracker group *completed* **or** *cancelled*; the report says
  which (`state Done (completed)`), because the fix differs: reopen, or fix
  the debt and delete the entry, or point the reason at a live ticket. That
  three-way hint is printed with every CLOSED_TICKET.
- `None` (no credentials, network, unknown id) is **unresolved**: never a
  guess in either direction, counted in the summary line, red only under
  `ratchet_ticket_strict`. Rationale: an offline laptop run must not break;
  a CI run must not turn an outage into a pass. Same doctrine as "scanner
  missing = fail, never skip", applied one notch softer because the tracker
  is a network dependency the scanner is not.
- One tracker call per ticket per check (several entries often cite one
  ticket); the Plane adapter additionally caches items and per-project state
  lists across checks. Default timeout 10 s, configurable
  (`ratchet_ticket_timeout`, passed to factories that accept `timeout`): a
  GitHub runner talking to a self-hosted Plane timed out at 3 s in the field.
- Core stays dependency-free; `adapters/plane.py` is stdlib `urllib`.
  Configuration precedence: constructor arguments, then `PLANE_BASE_URL` /
  `PLANE_API_KEY` / `PLANE_WORKSPACE_SLUG`.
- The summary line names the shape of the check, not just a count:
  `2 entries cite 1 ticket` (v0.2.1, after the first production run showed
  "1 ticket checked" for two entries and read as if one was skipped). Unstrict
  unresolved tickets are listed one per line under the summary and, on GitHub
  Actions, raised as a `::warning::` annotation — a warning that only lives
  in a log is a warning nobody reads.
- Without `ratchet_ticket_tracker` nothing changes: no request, no new
  summary text, byte-identical reports. Misconfiguration of the tracker
  (bad `module:callable`, object without `is_open`) fails the test loudly —
  a tracker that silently does not exist would be a check that silently does
  not run.

**Deferred, on purpose.** A `ratchet tickets` CLI (list and verify every
cited ticket outside pytest) — cheap, low value until a second adapter
exists. A GitHub Issues adapter — next, same protocol. Jira — not planned.
**v0.3 candidate — self-justified findings** (from the dogfooding project,
2026-08-29): a fixture case marked `xfail: "DAC-355"` already carries its
ticket and its note, so a baseline entry for it is a second copy of the same
fact, edited in two files on every change. When a `Finding` carries its own
reason, the ratchet should need no entry and run only the liveness check.
That is the natural shape of every fixture-based ratchet; the set-difference
model stays for findings that cannot justify themselves.
Commit- and PR-level gates ("a bug-labelled ticket cannot close without a
repro") belong to the project, not to a test-time baseline tool.

## Out of scope (recorded so they're deliberate)

- Pin-alignment checks (withdrawn 2026-08-10; not a ratchet).
- Deadlines/expiry dates on entries, per-entry owners.
- Any operation that edits the baseline besides `ratchet init` append.
- Numeric budget entries and `ratchet probe` — both from dogfooding, both
  v1.1 candidates, both listed in the README as current limits.
