# Scripts

The documented inventory of `scripts/`. Guarded in both directions: a script
missing from this file fails CI, and a line here with no script behind it
fails CI too.

## Active

- `backfill_users.py` — re-run after every bulk import
- `send_digest.py` — nightly cron entry point

## Archived

- `old_import.py` — superseded by the CSV importer, kept for reference
