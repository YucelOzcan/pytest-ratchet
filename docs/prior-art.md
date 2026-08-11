# Prior art survey

Surveyed 2026-08-11, before any pytest-ratchet code was written. Every claim
below carries a source; claims about the *absence* of a feature are marked as
absence-based (docs and issue trackers were searched, but a negative can never
be proven exhaustively).

## Dimensions

Each tool is scored on the properties pytest-ratchet is built around:

1. **Baseline file** — is there a committed artifact listing known findings?
2. **New finding fails** — does a violation not in the baseline fail CI?
3. **Stale entry fails** — if a listed finding no longer exists in the code,
   does anything fail until the entry is removed? (This is what keeps a
   baseline from lying.)
4. **Per-entry justification** — can/must a human-written reason be attached
   to each individual entry?
5. **Scanner-agnostic** — does it manage findings from arbitrary tools, or is
   it bound to one analyzer/domain?
6. **pytest-native** — does it run inside pytest, or is it its own runner/CLI?

## betterer (JS/TS)

The closest existing tool in spirit — "incremental improvement" snapshots for
any metric, most commonly ESLint/TypeScript errors.

- **Model.** Tests are defined in `.betterer.ts`; results are snapshotted into
  a committed `.betterer.results` file. File-based tests store per-issue
  entries as `[line, column, length, message, hash]`, keyed by file path +
  content hash. ([results file docs](https://phenomnomnominal.github.io/betterer/docs/results-file/),
  [tests docs](https://phenomnomnominal.github.io/betterer/docs/tests/))
- **Worse:** the run fails; regressions can be accepted with `--update`.
  **Better (local):** the results file is updated *automatically* — no human
  acknowledgment involved. ([running docs](https://phenomnomnominal.github.io/betterer/docs/running-betterer/),
  [updating docs](https://phenomnomnominal.github.io/betterer/docs/updating-results/))
- **`betterer ci` fails on any deviation from the snapshot, including
  improvements**: "If there is any difference between the new results and the
  expected results … Betterer will throw an error." So stale snapshots do fail
  CI — but the remedy is regenerating a machine-written file (or letting
  `betterer precommit` auto-stage it), not a human editing entries.
  ([running docs](https://phenomnomnominal.github.io/betterer/docs/running-betterer/),
  [issue #983](https://github.com/phenomnomnominal/betterer/issues/983))
- **Justification:** no field for a per-entry reason exists in the results
  format, and no issue/PR proposing one was found (absence-based).
- **Ecosystem:** own CLI/runner, TypeScript. Effectively dormant: last stable
  release 5.4.0 (2022-08), one alpha (2024-12), a single master commit in
  2025; nothing in 2026. ([npm registry](https://registry.npmjs.org/@betterer/cli),
  [repo](https://github.com/phenomnomnominal/betterer))

**Difference:** betterer's snapshot is machine-owned — it cannot lie, but it
also cannot explain. pytest-ratchet makes the baseline human-owned: every
entry carries a written reason, and removing a fixed entry is a deliberate
edit, not a regeneration.

## semgrep `--baseline-commit`

- The "baseline" is a **git commit, not a file**: semgrep scans current code
  and the baseline commit and reports only new findings. ([CLI reference](https://semgrep.dev/docs/cli-reference),
  [diff-scan docs](https://semgrep.dev/docs/kb/semgrep-ci/trigger-diff-scans-env-var))
- Nothing is stored, so nothing can go stale; fixed-finding tracking lives in
  the commercial cloud platform and never fails CI. ([findings docs](https://semgrep.dev/docs/semgrep-ci/findings-ci))
- `nosemgrep` inline suppressions have no reason field. ([ignore docs](https://docs.semgrep.dev/ignore-oss))

**Difference:** diff-vs-git answers "did this PR add findings?" but produces
no reviewable, justified inventory of accepted debt — and known debt is
invisible rather than listed.

## ruff

- **No native baseline** as of Feb 2026; the request
  ([astral-sh/ruff#1149](https://github.com/astral-sh/ruff/issues/1149), open
  since Dec 2022) is explicitly "not a top-priority feature" per maintainers.
- Practical workaround is bulk inline suppression: `ruff check --add-noqa`,
  which since 0.14.5 accepts **one global reason string per run**
  (`--add-noqa="# Baseline"`) — not a per-entry justification. It also
  rewrites source lines, which pollutes `git blame`; that objection is raised
  in the issue thread itself. ([0.14.5 release](https://github.com/astral-sh/ruff/releases/tag/0.14.5))
- **RUF100 (`unused-noqa`)** flags noqa comments that no longer suppress
  anything — real staleness enforcement, but only for inline suppressions,
  not for a baseline artifact. ([RUF100 docs](https://docs.astral.sh/ruff/rules/unused-noqa/))

**Difference:** ruff has the "suppressions cannot lie" idea (RUF100) but no
baseline file to apply it to, and reasons are global, not per-entry.

## mypy: mypy-baseline and basedmypy

[mypy-baseline](https://github.com/orsinium-labs/mypy-baseline) is the
strongest single piece of prior art for the staleness dimension:

- Committed `mypy-baseline.txt` (mypy output lines, line numbers zeroed);
  `mypy | mypy-baseline filter` surfaces only new errors.
  ([usage docs](https://mypy-baseline.orsinium.dev/usage))
- **Fails by default when baselined errors were fixed but the baseline wasn't
  re-synced** (`allow_unsynced = false`; the opt-out is explicit).
  ([config docs](https://mypy-baseline.orsinium.dev/config.html))
- No per-entry justification — entries are raw mypy output lines
  (absence-based). mypy-only; a stdout filter, not a pytest plugin.

[basedmypy](https://kotlinisland.github.io/basedmypy/baseline.html) has a
built-in `.mypy/baseline.json` (written with `--write-baseline`); when all
baselined errors are resolved it deletes the file automatically. No
justification support. (Behavior when only *some* errors are fixed:
unverified.)

**Difference:** mypy-baseline already enforces "the baseline cannot lie" —
for exactly one tool's output, with no reasons attached. pytest-ratchet
generalizes the enforcement across scanners and makes the reason mandatory.

## PHPStan (PHP, for context)

The most complete existing baseline implementation found in any ecosystem —
and the source of the strongest counter-doctrine to per-entry justification.

- **Model.** `--generate-baseline` writes `phpstan-baseline.neon` (a `.php`
  output format also exists), included from `phpstan.neon`. Each entry is
  exactly: a `message` regex, a `count` per file, and a `path` — deliberately
  no line numbers, because "the line information could get obsolete and the
  build would fail when the line with error shifts" (Ondřej Mirtes).
  ([baseline docs](https://phpstan.org/user-guide/baseline),
  [#2951](https://github.com/phpstan/phpstan/issues/2951#issuecomment-582392164))
- **New errors** fail normally; occurrences above the recorded `count` are
  reported. ([IgnoredErrorHelperResult.php](https://github.com/phpstan/phpstan-src/blob/2.1.x/src/Analyser/Ignore/IgnoredErrorHelperResult.php))
- **Stale entries fail by default.** `reportUnmatchedIgnoredErrors` defaults
  to `true` ([config.neon](https://github.com/phpstan/phpstan-src/blob/2.1.x/conf/config.neon));
  an entry with no matching error errors out — and that error itself is
  marked `canBeIgnored: false`, so a stale entry cannot be ignored away.
  Count decay also fails: fixing 1 of 5 baselined instances errors with
  "expected to occur 5 times, but occurred only 4" until the count is
  lowered. A full bidirectional ratchet, on by default.
  ([baseline docs](https://phpstan.org/user-guide/baseline),
  [IgnoredErrorHelperResult.php](https://github.com/phpstan/phpstan-src/blob/2.1.x/src/Analyser/Ignore/IgnoredErrorHelperResult.php))
- **Justification: excluded from the baseline by documented doctrine** (see
  the rebuttal section below). The sanctioned home for a reason is *inline*:
  `// @phpstan-ignore identifier (reason)` — and `reportIgnoresWithoutComments`
  (2.1.41+) can make a missing inline reason itself an error. That option is
  the closest existing analog to pytest-ratchet's required justification —
  applied to inline ignores only, never the baseline artifact.
  ([ignoring-errors docs](https://phpstan.org/user-guide/ignoring-errors))

**Difference:** PHPStan already has the honest baseline — but by design it is
a machine-owned burn-down list that cannot explain itself. pytest-ratchet
takes PHPStan's inline required-reason idea and moves it into the baseline.

## Psalm (PHP, for context)

- **Model.** `--set-baseline` writes a committed `psalm-baseline.xml`:
  per-file, per-issue-type entries with one `<code>` snippet per occurrence.
  Baselined issues are downgraded to INFO; new issues fail as usual.
  ([docs](https://psalm.dev/docs/running_psalm/dealing_with_code_issues/),
  [ErrorBaseline.php](https://github.com/vimeo/psalm/blob/master/src/Psalm/ErrorBaseline.php))
- **Stale entries fail by default.** `findUnusedBaselineEntry` defaults to
  `true`; leftover entries raise `UnusedBaselineEntry` as an error
  ("Baseline for issue X has N extra entries"). Remedy: `--update-baseline`,
  which removes fixed issues but never adds new ones.
  ([Config.php](https://github.com/vimeo/psalm/blob/master/src/Psalm/Config.php),
  [config.xsd](https://github.com/vimeo/psalm/blob/master/config.xsd),
  [IssueBuffer.php](https://github.com/vimeo/psalm/blob/master/src/Psalm/IssueBuffer.php))
- **No justification support**; the file is machine-regenerated wholesale, so
  hand-added XML comments would not survive a rewrite (inferred from the
  writer code). Active but thinly staffed (v6.16.1, 2026-03; one active
  maintainer). ([releases](https://github.com/vimeo/psalm/releases))

## RuboCop `.rubocop_todo.yml` (Ruby, for context)

- **Model.** `rubocop --auto-gen-config` writes `.rubocop_todo.yml` —
  per-cop `Exclude` file lists and `Max` ceilings, inherited via
  `inherit_from`, with auto-generated `# Offense count: N` comments. The
  generated header states the temporariness doctrine outright: "The point is
  for the user to remove these configuration records one by one as the
  offenses are removed from the code base."
  ([auto-gen docs](https://docs.rubocop.org/rubocop/latest/usage/auto_gen_config.html),
  [disabled_config_formatter.rb](https://github.com/rubocop/rubocop/blob/master/lib/rubocop/formatter/disabled_config_formatter.rb))
- **New-offense holes:** a file excluded for a cop is not inspected at all,
  so *new* offenses of that cop in that file pass silently; new code under a
  generated `Max` ceiling also passes (inferred from documented `Exclude`
  semantics). ([configuration docs](https://docs.rubocop.org/rubocop/latest/configuration.html))
- **Staleness: nothing in any released version** (≤1.89.0, 2026-08). The
  documented workflow is manual removal; `--regenerate-todo` rewrites the
  whole file and *absorbs new offenses too* — it re-baselines rather than
  ratchets. Notably, master (unreleased as of 2026-08-11) just gained
  `--report-unused-todo-entries` ([#13037](https://github.com/rubocop/rubocop/issues/13037)):
  stale `Exclude` entries fail the run, opt-in — convergent evidence for the
  stale-entry-fails design. ([master auto-gen docs](https://github.com/rubocop/rubocop/blob/master/docs/modules/ROOT/pages/usage/auto_gen_config.adoc))
- **Justification:** YAML comments only, wiped on regeneration.

## ESLint bulk suppressions (JS, for context)

- **Model.** Since v9.24.0 (2025-04): `--suppress-all` / `--suppress-rule`
  write a committed `eslint-suppressions.json` — per-file, per-rule violation
  **counts**, deliberately position-independent.
  ([suppressions docs](https://eslint.org/docs/latest/use/suppressions),
  [announcement](https://eslint.org/blog/2025/04/introducing-bulk-suppressions/))
- **New violations:** when a file+rule count is exceeded, ESLint reports
  *all* violations of that rule in that file (counts can't tell old from new).
- **Stale suppressions fail by default.** Docs verbatim: "it exits with a
  non-zero exit code and an error is reported about unused suppressions.
  This is because the violations have been resolved but the suppressions are
  still in place." Remedy: `--prune-suppressions`; opt-out:
  `--pass-on-unpruned-suppressions`.
  ([suppressions docs](https://eslint.org/docs/latest/use/suppressions))
- **Granularity caveat:** counts, not identities — fixing one violation while
  introducing another of the same rule in the same file passes silently.
- **Justification: no channel at all** — the schema is count-only JSON, and
  JSON forbids comments.

## SonarQube (platform, for context)

The one widely-used tool where per-finding human justification is a
first-class feature — implemented in exactly the way this project rejects.

- **Model.** Server-side analysis; the quality gate applies to a "new code"
  period, tolerating pre-existing issues wholesale. The baseline is implicit
  (a time/diff boundary), not an enumerated, reviewable artifact.
  ([Clean as You Code](https://docs.sonarsource.com/sonarqube-server/9.9/user-guide/clean-as-you-code))
- **Justification exists — optional and off-repo.** Issues can be resolved
  "Accepted" or "False positive" with a comment, but the docs mark it "your
  change comment (optional)"; it requires the Administer Issues permission
  and lives in the server database (issue Activity tab), not in a committed
  file that code review ever sees.
  ([managing issues](https://docs.sonarsource.com/sonarqube-server/user-guide/issues/managing))
- **Staleness: silent auto-close.** When the code behind an accepted issue is
  fixed or removed, the issue is closed "automatically when a subsequent
  analysis shows that the issue has been corrected" — the acceptance and its
  justification quietly disappear; nothing ever fails or alerts.
  ([issue lifecycle](https://docs.sonarsource.com/sonarqube-server/10.4/user-guide/issues))
- `//NOSONAR` has no reason field; SonarQube 2026.1's answer to suppression
  abuse is meta-rules that flag suppression comments themselves as issues.
  ([tracking inline comments](https://docs.sonarsource.com/sonarqube-server/2026.1/quality-standards-administration/managing-quality-gates/tracking-inline-comments))

**Difference:** SonarQube proves the demand for per-finding justification —
then makes it optional, stores it outside the repo, and lets it vanish
silently. pytest-ratchet makes it required, committed, and stale-visible.

## pylint

- **No native baseline**; longstanding requests
  ([#5403](https://github.com/pylint-dev/pylint/issues/5403),
  [#5604](https://github.com/pylint-dev/pylint/issues/5604)).
- [pylint-silent](https://github.com/udifuchs/pylint-silent) mass-inserts
  inline `# pylint: disable=` comments from a log; its `--signature` option
  appends a greppable marker, not a human reason. Staleness workflow is
  "reset everything and regenerate".
- `useless-suppression` (I0021) flags disables that never trigger — staleness
  enforcement for inline suppressions, **disabled by default**.
  ([docs](https://pylint.readthedocs.io/en/stable/user_guide/messages/information/useless-suppression.html))

## import-linter

Architecture contracts (layers, forbidden imports) checked by the standalone
`lint-imports` CLI. ([docs](https://import-linter.readthedocs.io/en/stable/))

- Known violations are allowlisted via `ignore_imports` per contract.
- **`unmatched_ignore_imports_alerting = error` is the default**: an
  `ignore_imports` expression matching no real import fails the run. This is
  the only Python tool surveyed with error-by-default staleness enforcement
  on an allowlist. ([contract types docs](https://import-linter.readthedocs.io/en/v2.1/contract_types.html))
- No per-entry justification field (absence-based); scoped to imports only;
  not pytest-integrated. Actively maintained (v2.13, 2026-07).

**Difference:** import-linter proves the stale-allowlist-fails design works
in practice — in one domain. pytest-ratchet applies it to any scanner's
findings and adds the mandatory reason.

## pytest-archon

Architecture rules written as ordinary pytest tests
([repo](https://github.com/jwbargsten/pytest-archon)) — fluent
`archrule(...).match(...).should_not_import(...)` API with a rule-level
`comment=` parameter. **No baseline/known-violations mechanism at all**: a
rule either passes or fails, so it cannot be adopted incrementally on a
codebase that already violates it (absence-based). pytest-native, early-stage
(v0.0.7, 2025-09).

## deptry

Finds missing/unused/transitive/misplaced dependencies
([usage docs](https://deptry.com/usage/)). Suppression via inline
`# deptry: ignore[...]` comments and `[tool.deptry.per_rule_ignores]` package
lists in pyproject. **No staleness detection** — an ignore for a
since-removed dependency sits silently forever (absence-based). No reason
fields beyond free-form TOML comments. Standalone CLI. Actively maintained
(v0.25.1, 2026-03).

## vulture (first planned scanner integration)

Dead-code finder; exits 3 on findings. ([repo](https://github.com/jendrikseipp/vulture))

- Its "whitelist" is **fake-usage Python code** (`--make-whitelist` generates
  a module that pretends to use the flagged names), not a findings list.
- **Staleness is a manual, optional step**: the README suggests you can
  "often" run `python whitelist.py` and let the interpreter catch entries
  whose code no longer exists. Nothing in vulture itself ever fails on a
  stale whitelist entry.
- No justification support beyond ordinary code comments; no pytest
  integration. Actively maintained (v2.16, 2026-03).

This gap is why vulture is the first integration: its own suppression story
is the weakest on exactly the dimensions pytest-ratchet supplies.

## knip (JS, for context)

Suppression via config ignores; no reason fields. Knip *does* detect stale
config entries ("configuration hints": "remove from ignoreDependencies" etc.)
but they are warnings unless `--treat-config-hints-as-errors` is set —
opt-in, versus import-linter's error-by-default and pytest-ratchet's
always-on. ([configuration hints](https://knip.dev/reference/configuration-hints),
[issue #1026](https://github.com/webpro-nl/knip/issues/1026))

## Existing pytest plugins

- `pytest-ratchet` and `pytest-baseline` do not exist on PyPI (both 404 on
  the PyPI JSON API, checked 2026-08-11).
- Nearest neighbor: [pytest-quarantine](https://pypi.org/project/pytest-quarantine/)
  — records currently *failing tests* and xfails them. It ratchets test
  outcomes, not scanner findings, has no justifications, and is unmaintained
  (last release 2019-11).
- Snapshot plugins (pytest-snapshot, syrupy) compare test outputs, not
  managed debt. No plugin doing a generic justified baseline of scanner
  findings was found (absence-based; the ~1500-plugin pytest list was not
  exhaustively enumerated).

## Summary table

| Tool | Baseline file | New finding fails | Stale entry fails | Per-entry reason | Scanner-agnostic | pytest-native |
|---|---|---|---|---|---|---|
| betterer | yes (machine-written) | yes | CI mode, on any snapshot diff | no | yes (JS) | no (own CLI, JS) |
| semgrep `--baseline-commit` | no (git commit) | yes (`--error`) | n/a (nothing stored) | no | semgrep-only | no |
| ruff + noqa | no ([#1149](https://github.com/astral-sh/ruff/issues/1149) open) | yes | RUF100, inline only | global string only | ruff-only | no |
| mypy-baseline | yes | yes | **yes, by default** | no | mypy-only | no |
| basedmypy | yes | yes | partial (auto-delete) | no | mypy-only | no |
| PHPStan baseline | yes | yes | **yes, by default** (incl. count decay) | no — by doctrine; inline reasons can be required | phpstan-only | no |
| Psalm baseline | yes | yes | **yes, by default** | no | psalm-only | no |
| RuboCop `.rubocop_todo.yml` | yes (config) | yes, with excluded-file holes | no release mechanism; opt-in flag on master | no | rubocop-only | no |
| ESLint bulk suppressions | yes (counts) | yes | **yes, by default** | no channel (count-only JSON) | eslint-only | no |
| SonarQube Accept/FP | no (server DB) | yes (new-code gate) | silent auto-close | optional comment, off-repo | platform | no |
| pylint (+pylint-silent) | no (inline) | yes | I0021, off by default | no | pylint-only | no |
| import-linter | allowlist in config | yes | **yes, by default** | no | imports-only | no |
| pytest-archon | no | yes | n/a | rule-level comment | imports-only | yes |
| deptry | ignores in config | yes | no | no | deps-only | no |
| vulture whitelist | fake-usage code | yes | manual, optional | no | vulture-only | no |
| pytest-quarantine | yes | yes | no | no | test outcomes only | yes |
| **pytest-ratchet (planned)** | **yes, human-owned** | **yes** | **yes, always** | **required field** | **yes** | **yes** |

## The claim, stated narrowly

Every ingredient exists somewhere:

- Stale-entry-fails-by-default: **PHPStan** (including count decay),
  **Psalm**, **mypy-baseline**, **ESLint bulk suppressions**,
  **import-linter** (import allowlists); betterer's CI mode (as a snapshot
  diff). Opt-in or partial: RUF100 / `useless-suppression` (inline comments
  only), knip's config hints, RuboCop's unreleased
  `--report-unused-todo-entries`. Bidirectional enforcement is not novel —
  it is close to becoming table stakes.
- Per-finding justification: **SonarQube** (first-class but optional, stored
  server-side, silently auto-closed); **PHPStan**'s
  `reportIgnoresWithoutComments` (a *required* reason — for inline ignores
  only, never the baseline).
- Scanner-agnostic ratcheting: **betterer** (JS, dormant, machine-owned
  snapshot).
- pytest-native architecture checks: **pytest-archon** (no baseline).

What we did not find anywhere, in any ecosystem (as of 2026-08-11): a
**committed baseline** where each entry carries a **required reason field**
(a `TODO` placeholder is legal, but it is counted and surfaced on every
run), combined with bidirectional enforcement (new finding fails, stale
entry fails), applied to **arbitrary scanner findings**, running **inside
pytest**. That narrow combination — plus the resolver protocol for
runtime-resolution reachability guards — is the layer pytest-ratchet adds.
Nothing more is claimed.

## Anticipated rebuttal: "baselines are not the place for comments"

The absence of justification fields in existing baselines is not an
oversight — in PHPStan's case it is doctrine. The official docs list it as a
known cost of the baseline: "**No comments**: Inline annotations allow you to
leave a comment to describe *why* an error is ignored. This is often crucial
and is not an option when using the baseline." And the reason it stays that
way: "The life goal of a baseline file is to not exist. By adding
'unresolvable' ignores to the baseline this becomes an impossible task."
([baseline docs](https://phpstan.org/user-guide/baseline), section
maintainer-merged via [PR #14052](https://github.com/phpstan/phpstan/pull/14052).)
The same logic is embedded in the mechanics elsewhere: Psalm and RuboCop
regenerate their files wholesale, so a hand-written comment cannot survive;
ESLint chose a count-only JSON schema with no annotation channel at all.

The doctrine is coherent — for one kind of debt. It assumes every baselined
entry is burn-down debt: temporary, regrettable, destined for deletion, so
documenting it is wasted motion. But real baselines also carry *accepted*
debt — findings a team has examined and decided to live with (a scanner
false-positive that can't be restructured away, dead code kept for a
protocol, a dependency pinned for a known reason). Those entries are
long-lived precisely because someone made a judgment call, and they are
exactly the entries whose reason gets lost. PHPStan itself concedes the
reason is "often crucial" and even *enforces* written reasons via
`reportIgnoresWithoutComments` — just only where a human owns the text
(inline), never in the machine-regenerated artifact. SonarQube demonstrates
the demand from the other side: justification comments are a first-class
platform feature — then made optional, stored off-repo, and silently
discarded when the issue closes.

pytest-ratchet's answer is not to bolt a comment field onto a generated
file — it is to change who owns the file. The baseline is human-edited:
`ratchet init` seeds entries with `reason: TODO`, a TODO reason is itself a
visible debt, and the staleness check keeps human ownership honest (a
machine-regenerated file never lies, but only because it never says
anything). Burn-down debt still burns down — the ratchet direction is
preserved — but debt that stays gets a name and a reason that survive
review, `git blame`, and time.
