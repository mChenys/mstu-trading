# Market Data Scheduling

## Goal

Provide a portable scheduling reference for refreshing intraday market data
without tying the project to one specific machine or OS.

The scheduler should always execute the same repository-local command:

```bash
./scripts/refresh_market_data.sh 15m 60d
```

Run it from the repository root.

## Recommended Cadence

- Minimum safe cadence: once every 30 days
- Recommended cadence: once per week

Weekly refreshes leave enough overlap in Yahoo's rolling window to reduce the
risk of missing a segment if one scheduled run fails.

## Portable Cron Template

```cron
0 9 * * 1 cd /path/to/mstu-trading && ./scripts/refresh_market_data.sh 15m 60d >> logs/data-refresh.log 2>&1
```

Notes:

- Replace `/path/to/mstu-trading` with the repository checkout path in that environment.
- Create the `logs/` directory first if you want file logging.
- If the environment does not have cron, use an equivalent scheduler.

## launchd Template

For macOS environments, create a local plist outside the repository that runs:

```bash
/bin/zsh -lc 'cd /path/to/mstu-trading && ./scripts/refresh_market_data.sh 15m 60d >> logs/data-refresh.log 2>&1'
```

Keep the plist outside the repo because it is machine-specific.

## CI / Bot / External Scheduler

If OpenClaw runs in a managed environment:

- check out the repository
- restore or pull the latest branch
- execute the refresh script from repo root
- commit and push new archived snapshots only when appropriate for that workflow

## Safety Rules

- The scheduler must never delete old `data/archive/` files.
- If a refresh fails, do not clean up archive history as part of retry logic.
- If the repository is not writable in that environment, run the refresh in a
  writable checkout and push the resulting data changes back through normal Git flow.
