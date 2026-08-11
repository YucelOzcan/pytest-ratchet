# pytest-ratchet

A pytest plugin for baselines that cannot lie.

Most baseline tools are one-way: known debt is frozen, new violations fail CI,
and when debt gets *fixed* nobody notices — the baseline file quietly starts
lying. pytest-ratchet enforces the other direction too: every baseline entry
carries a written justification, and an entry that no longer matches a real
finding fails CI until it is removed.

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

## Roadmap

- [ ] Prior-art survey (betterer, semgrep/ruff/mypy baselines, import-linter,
      pytest-archon, deptry) — differences stated explicitly before any claim
- [ ] Core primitive: justified allowlist + new-violation check + staleness check
- [ ] `ratchet init` scaffolding (first integration: vulture)
- [ ] Resolver protocol + reachability guard recipes with a runnable example
      project under `examples/`
- [ ] Own CI, docs, PyPI release
