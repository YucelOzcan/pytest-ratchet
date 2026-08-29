# pytest-ratchet

**Debt is allowed. Lying about it is not.**

A pytest plugin for baselines that cannot lie.

Most baseline tools are one-way: known debt is frozen, new violations fail CI,
and when debt gets *fixed* nobody notices — the baseline file quietly starts
lying. pytest-ratchet enforces the other direction too: every baseline entry
carries a reason field that must be filled in — `TODO` is a legal value, but
it is counted and reported on every run until someone replaces it — and an
entry that no longer matches a real finding fails CI until it is removed.

**Status: v0.2.0 on main (v0.1.0 on PyPI).** The core primitive, `ratchet init`,
the resolver protocol and reason liveness are complete and tested. It runs in one production
repository's CI, backing two guards there: the dead-code gate, which ran
beside the hand-written test it replaced until that test was retired on
2026-08-29, and an architecture rule that had an exception list but no
staleness check until the migration gave it one.

## Quickstart

```
pip install "pytest-ratchet[vulture]"
ratchet init src/    # run vulture, seed ratchet-baseline.toml (reason = "TODO"),
                     # scaffold test_ratchet.py
pytest               # from then on: new finding = red, stale baseline entry = red
```

Run `ratchet init` from the directory pytest treats as its rootdir — that is
where the plugin looks for the baseline (init prints the path it wrote and
reminds you). In a monorepo, either run pytest from that directory or point
it at the file with `ratchet_baseline` in your pytest config.

Every seeded entry starts as `reason = "TODO"`; each run reports how many
TODOs remain and how old the oldest is. Replace them with real reasons at
your own pace — or set `ratchet_strict_todo = true` in pytest config to
force the issue.

- On an existing project: your debt becomes visible, justified, and frozen —
  it can shrink, it cannot silently grow, and the list never goes stale.
- On a greenfield project: the baseline starts empty and the tool keeps the
  cost of leaving zero visible — debt can only enter with a name and a reason.

This tool does not fix your code quality. It does one thing: it keeps your
baseline honest.

## Proving the gate (read this before you trust it)

A check you have never watched fail is a check you do not have. So after
wiring a guard, prove it: introduce a violation on purpose, watch CI go red,
then remove it.

**The probe itself has a trap, and it is the same trap this tool exists to
fight.** Scanners reason about your whole corpus, so an obvious probe can be
silently absorbed. With vulture, adding `import json` to a file proves
nothing: `json` is used elsewhere in the project, so vulture never reports
it, the guard stays green, and you walk away believing you proved something.
Use a name that cannot occur anywhere else:

```python
import json as _zzz_ratchet_probe   # unique name — vulture will report this
```

The same corpus-wide reasoning bites from the other side too, and this one
is nastier because the probe *works*: code you add in one file can make an
existing finding in a different file disappear, turning a healthy baseline
entry stale. It has happened to us — a probe importing a name that was
already recorded as an unused import elsewhere made that finding vanish, and
the run failed with STALE instead of NEW. So a probe name must satisfy two
conditions, not one: it must not occur anywhere in the corpus, **and** it
must not be a name your baseline already has an entry for.

Then prove the other direction too, which most people forget: add a fake
entry to the baseline for a finding that does not exist and confirm the run
fails with STALE. A ratchet that only bites in one direction is half a
ratchet, and the half that rots quietly is the one you didn't test.

If you enabled a ticket tracker (next section), prove that direction as
well: write a reason that cites a ticket you *know* is closed, watch the run
fail with CLOSED_TICKET, then put it back. And once, deliberately, run with
the tracker's credentials missing: without `ratchet_ticket_strict` the
summary must say `unresolved`, with it the run must go red. A liveness check
you have never seen fail on a dead ticket is a check you do not have.

## Reason liveness: tickets that closed behind your back

Most reasons point at a ticket: `DAC-355: fix once the parser grows`. That is
a claim about the tracker, and it can go false without anything in the code
changing — the ticket gets closed, the finding stays, the entry stays. NEW
cannot see it, STALE cannot see it, and the baseline now says "tracked"
while the tracker says "done". Nobody lied; the record is still wrong.

Give the ratchet a tracker and it asks a third question on every run: *is
the cited ticket still open?*

```ini
# pytest.ini / pyproject [tool.pytest.ini_options]
ratchet_ticket_tracker = pytest_ratchet.adapters.plane:PlaneTracker
ratchet_ticket_strict = true        # in CI: "could not tell" is red, not green
```

```
  CLOSED_TICKET (reason cites a closed ticket — reopen the ticket, or fix the
  debt and delete the entry, or point the reason at a live ticket):
    src/pbx/handlers.py::function::on_hangup   DAC-355 is closed (state Done (completed))
      reason was: "DAC-355: fix once the parser grows"
```

The convention is deliberately narrow: a reason cites tickets by **starting**
with one or more ids — `DAC-355: ...` or `DAC-355, DAC-360: ...` (every id
in the list must be open). An id later in the text (`kept — see DAC-355`) is
prose, not a claim, and is ignored. Reasons that cite nothing are untouched;
`TODO` stays `TODO`. The id shape is `ratchet_ticket_pattern` (default
`^[A-Z][A-Z0-9]+-\d+`), and "closed" means the tracker's *completed* **or**
*cancelled* — a cancelled ticket kills a reason just as thoroughly.

When the tracker cannot answer — no credentials, network down, unknown id —
the entry is **unresolved**: never guessed either way, always shown in the
summary (`3 tickets checked (1 unresolved)`), and red only under
`ratchet_ticket_strict`. Run it unstrict on laptops so an offline run still
works, strict in CI so an outage cannot turn into a silent pass.

Trackers are plugins: anything with `is_open(ticket_id) -> bool | None`
(optionally `explain(ticket_id) -> str` for the report), built by the
`module:callable` named in `ratchet_ticket_tracker`; factories that accept a
`timeout` argument receive `ratchet_ticket_timeout` (default 10 s — a
GitHub runner talking to a self-hosted tracker needs more than you think).
One adapter ships today, [Plane](https://plane.so)
(`PLANE_BASE_URL`, `PLANE_API_KEY`, `PLANE_WORKSPACE_SLUG`; stdlib only,
one request per ticket, state lists cached per project). A GitHub Issues
adapter is next; writing your own is a dozen lines.

## Known limits

Stated plainly, because a tool about honest records should keep an honest
one about itself.

- **No numeric budgets.** Entries are matched as a set: a finding is present
  or absent. Baselines where each entry carries an allowed *number* — "this
  function may be up to 208 lines", "at most 16 exceptions may exist" — are
  not modeled, because exceeding a budget is neither a new finding nor a
  stale one. If your debt is measured rather than enumerated, this tool
  cannot hold it yet.
- **Reasons live apart from the check.** The baseline is a separate file, so
  a reviewer reading the guard's thresholds does not see the justifications
  on the same screen. That separation is what makes the reasons survive
  regeneration, but it is a real trade-off, not a free win.
- **Adoption can force the very skip the tool forbids.** A guard fails rather
  than skips when its scanner is missing — but while you are still evaluating
  pytest-ratchet, before it is a pinned dependency, wrapping the guard in
  `pytest.importorskip` is the practical move, and that guard then passes
  silently in CI. If you must do it, make it deliberate and dated, and delete
  it the moment the dependency is pinned.
- **No `tag` on entries.** Teams often want to distinguish permanent accepted
  patterns from temporary debt. Today the only machine-readable distinction
  is `reason = "TODO"` versus a written reason.
- **Ticket liveness only sees what the reason claims.** A ticket named in
  the middle of a sentence is not checked, by design; an unreachable tracker
  is a visible *unresolved*, not a failure, unless you turn on
  `ratchet_ticket_strict`. And "open" is all it asks — a ticket that is open
  but abandoned is a question for people, not for a plugin.

## Prior art

Baseline tools exist; most freeze debt in one direction only, and none of the
surveyed ones require a written reason per entry. Full survey with sources:
[docs/prior-art.md](https://github.com/YucelOzcan/pytest-ratchet/blob/master/docs/prior-art.md) (2026-08-11).

| Tool | Baseline file | New finding fails | Stale entry fails | Per-entry reason | Scanner-agnostic | pytest-native |
|---|---|---|---|---|---|---|
| [betterer](https://github.com/phenomnomnominal/betterer) (JS) | machine-written snapshot | yes | CI mode, any snapshot diff | no | yes | no |
| [semgrep `--baseline-commit`](https://semgrep.dev/docs/cli-reference) | no (diffs vs git commit) | yes | n/a — nothing stored | no | semgrep-only | no |
| [ruff](https://github.com/astral-sh/ruff/issues/1149) + noqa | no native baseline | yes | RUF100, inline noqa only | global string only | ruff-only | no |
| [mypy-baseline](https://github.com/orsinium-labs/mypy-baseline) | yes | yes | **yes, by default** | no | mypy-only | no |
| [pylint](https://pylint.readthedocs.io/en/stable/user_guide/messages/information/useless-suppression.html) (+pylint-silent) | no (inline disables) | yes | I0021, off by default | no | pylint-only | no |
| [import-linter](https://import-linter.readthedocs.io/en/stable/) | allowlist in config | yes | **yes, by default** | no | imports-only | no |
| [pytest-archon](https://github.com/jwbargsten/pytest-archon) | no baseline at all | yes | n/a | rule-level comment | imports-only | yes |
| [deptry](https://deptry.com/usage/) | ignores in config | yes | no | no | deps-only | no |
| [vulture](https://github.com/jendrikseipp/vulture) whitelist | fake-usage code | yes | manual, optional | no | vulture-only | no |
| **pytest-ratchet** | **human-owned, justified** | **yes** | **yes, always** | **required field** | **yes** | **yes** |

Credit where due: bidirectional enforcement is not novel. PHPStan (including
count decay), Psalm, mypy-baseline, and ESLint's bulk suppressions all fail
by default when a listed finding no longer exists, and import-linter does the
same for import allowlists — each within a single domain, none with
justifications. betterer's CI mode rejects any drift from its snapshot, but
the snapshot is machine-regenerated, not human-edited. SonarQube has
first-class per-finding justification comments — optional, stored server-side,
silently discarded when the issue closes. The per-entry reason is missing
from existing baselines by explicit doctrine, not oversight: PHPStan's docs
call the "why" comment "often crucial" and "not an option when using the
baseline" — the survey's rebuttal section addresses this directly. The layer
pytest-ratchet adds is the combination: a required per-entry reason field in
a committed, human-owned baseline + bidirectional enforcement + arbitrary
scanners + pytest. Nothing more is claimed.

The survey also covers PHPStan, Psalm, RuboCop's todo file, ESLint bulk
suppressions, and SonarQube in full — see
[docs/prior-art.md](https://github.com/YucelOzcan/pytest-ratchet/blob/master/docs/prior-art.md) for their rows and sources.

Scanners like vulture, deptry, and knip are not competitors here — they are
producers. The scanner finds; the ratchet keeps what it found justified,
frozen, and honest.

## Roadmap

- [x] Prior-art survey (betterer, semgrep/ruff/mypy baselines, import-linter,
      pytest-archon, deptry) — differences stated explicitly before any claim:
      [docs/prior-art.md](https://github.com/YucelOzcan/pytest-ratchet/blob/master/docs/prior-art.md)
- [x] Core primitive: justified allowlist + new-violation check + staleness
      check — `pytest_ratchet.core` + the `ratchet` fixture, with tests and CI
- [x] `ratchet init` scaffolding (first integration: vulture) — append-only
      seeding, guard-test scaffold, self-checked output
- [x] Resolver protocol + reachability guard recipes with a runnable example
      project under [`examples/webapp`](https://github.com/YucelOzcan/pytest-ratchet/tree/master/examples/webapp) — candidates minus
      reachable, managed by the same baseline
- [x] Own CI (tests + the example project, Python 3.11–3.13)
- [ ] Docs, license, PyPI release
