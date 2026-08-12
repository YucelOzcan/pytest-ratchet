# pytest-ratchet

**Debt is allowed. Lying about it is not.**

A pytest plugin for baselines that cannot lie.

Most baseline tools are one-way: known debt is frozen, new violations fail CI,
and when debt gets *fixed* nobody notices — the baseline file quietly starts
lying. pytest-ratchet enforces the other direction too: every baseline entry
carries a reason field that must be filled in — `TODO` is a legal value, but
it is counted and reported on every run until someone replaces it — and an
entry that no longer matches a real finding fails CI until it is removed.

**Status: work in progress — not yet released.**

## Quickstart

Not on PyPI yet — install from the repository:

```
pip install "pytest-ratchet[vulture] @ git+https://github.com/YucelOzcan/pytest-ratchet"
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

Then prove the other direction too, which most people forget: add a fake
entry to the baseline for a finding that does not exist and confirm the run
fails with STALE. A ratchet that only bites in one direction is half a
ratchet, and the half that rots quietly is the one you didn't test.

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
