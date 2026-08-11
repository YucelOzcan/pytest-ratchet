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

## Planned shape

```
pip install pytest-ratchet
ratchet init      # run a scanner, seed the baseline (each entry gets a reason: TODO)
pytest            # from then on: new finding = red, stale baseline entry = red
```

- On an existing project: your debt becomes visible, justified, and frozen —
  it can shrink, it cannot silently grow, and the list never goes stale.
- On a greenfield project: the baseline starts empty and the tool keeps the
  cost of leaving zero visible — debt can only enter with a name and a reason.

This tool does not fix your code quality. It does one thing: it keeps your
baseline honest.

## Prior art

Baseline tools exist; most freeze debt in one direction only, and none of the
surveyed ones require a written reason per entry. Full survey with sources:
[docs/prior-art.md](docs/prior-art.md) (2026-08-11).

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
[docs/prior-art.md](docs/prior-art.md) for their rows and sources.

Scanners like vulture, deptry, and knip are not competitors here — they are
producers. The scanner finds; the ratchet keeps what it found justified,
frozen, and honest.

## Roadmap

- [x] Prior-art survey (betterer, semgrep/ruff/mypy baselines, import-linter,
      pytest-archon, deptry) — differences stated explicitly before any claim:
      [docs/prior-art.md](docs/prior-art.md)
- [ ] Core primitive: justified allowlist + new-violation check + staleness check
- [ ] `ratchet init` scaffolding (first integration: vulture)
- [ ] Resolver protocol + reachability guard recipes with a runnable example
      project under `examples/`
- [ ] Own CI, docs, PyPI release
