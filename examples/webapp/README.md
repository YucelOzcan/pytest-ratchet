# Example: a webapp with dynamic dispatch

A miniature app built to show the two things pytest-ratchet does that static
scanners cannot: keep accepted findings *justified*, and see through
*runtime-resolved* references.

The app resolves everything by name at runtime:

- `routes.py` maps URL paths to handler **name strings** and dispatches with
  `getattr(handlers, name)` — so vulture reports every handler as dead code.
- Handlers load templates by **filename string** — so no tool can tell a
  live template from an orphaned one.

## Run it

From the repository root:

```
pip install -e '.[vulture]'
pytest examples/webapp
```

All green, and the summary tells you what is being carried:

```
section [vulture]: 4 entries OK
section [templates]: 1 entry OK, 1 TODO (oldest: 0 days)
section [handlers]: 1 entry OK
```

## The three guards

**`[vulture]` — dead-code scan.** vulture flags all three handlers plus
`dispatch()` as unused: dynamic dispatch is invisible to it. The baseline
accepts each one *with the reason written down* ("dispatched by name via
routes.ROUTES"). Compare this to a `# noqa`: the reason survives review,
`git blame`, and the person who wrote it leaving.

**`[handlers]` — unmounted-handler resolver.** vulture's entry for
`handle_export` says "dispatched once mounted" — but the resolver, which
reads the actual `ROUTES` table, knows it is *not mounted*. That gap between
"could be reached" and "is reached" is exactly what a resolver states:
`candidates()` (every `handle_*` function) minus `reachable()` (names in
`ROUTES`).

**`[templates]` — orphan-template resolver.** `welcome_email.html` exists,
nothing renders it. Its baseline entry still says `reason = "TODO"` — legal,
but counted and aged on every run until someone decides: delete the
template, or write down why it stays.

## Break it (the point of the exercise)

Each of these turns CI red — try them:

1. **Add debt:** write a new `def handle_beta(): ...` in `handlers.py` →
   `[vulture]` and `[handlers]` both fail with NEW. Debt can only enter with
   a name and a reason.
2. **Pay debt without saying so:** delete
   `app/templates/welcome_email.html` → `[templates]` fails with STALE: the
   baseline entry now lies, remove it to go green.
3. **Mount the export handler:** add `"/export.csv": "handle_export"` to
   `ROUTES` → `[handlers]` fails with STALE — the "not mounted yet" entry
   stopped being true, and the run makes you acknowledge it.

## Write your own resolver

A resolver is any object with a `kind` and two methods; wire it to a section
of the baseline with one test:

```python
from pytest_ratchet import unreachable_findings

class ConfigKeyResolver:
    kind = "orphan-config-key"

    def candidates(self):      # everything that exists
        return set(load_config_file())

    def reachable(self):       # everything the code actually reads
        return keys_read_by_the_app()

def test_orphan_config(ratchet):
    ratchet.check("config", unreachable_findings(ConfigKeyResolver()))
```

Rules the primitive enforces for you: an empty `candidates()` set is an
error (a guard that sees nothing guards nothing), extra `reachable()` items
are ignored, and findings are managed by the baseline like any scanner's —
new = red, stale = red, every acceptance carries a reason.
