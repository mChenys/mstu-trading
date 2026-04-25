# Market Data Archive Design

## Goal

Preserve minute-level market data inside the repository so future agents can build longer backtest windows even after Yahoo's rolling minute-data limit expires.

## Layout

- `data/latest/`: current working copy for daily use
- `data/archive/<symbol>/<interval>/`: immutable dated snapshots
- `data/merged/<symbol>/<interval>.csv`: deduplicated long-history file rebuilt from archive snapshots

## Rules

- Never hand-edit or overwrite files under `data/archive/`
- Rebuild `data/merged/` only from archived snapshots
- `data/latest/` may be refreshed, but should always come from archived snapshots or the latest download
- Keep this data tracked in Git so future agents inherit the accumulated history

## Workflow

1. Download the latest 60-day market data window
2. Save it to `data/archive/` under a snapshot date
3. Refresh `data/latest/`
4. Rebuild `data/merged/`
5. Use `data/latest/` for normal short-window work and `data/merged/` for long-window backtests

## Automation

- Provide a repository-local CLI for snapshot and merge operations
- Document a periodic runner command for cron/launchd
- Make comments and README warnings explicit so agents do not delete or overwrite archived data
