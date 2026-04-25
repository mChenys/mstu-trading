# Market Data Archive

This directory stores tracked market data that future agents must preserve.

## Why This Exists

Yahoo minute-level history is a rolling window and can expire after roughly 60 days.
If we do not archive snapshots now, we cannot reconstruct long-window intraday backtests later.

This directory is a long-lived project asset, not a cache.

## Directory Rules

- `latest/`
  Current working copy used by normal backtests and experiments.
  These files may be refreshed.

- `archive/`
  Append-only historical snapshots.
  Do not edit, rename, or overwrite files here by hand.
  If a snapshot for the same date already exists, the tooling will create a suffixed file instead of overwriting it.

- `merged/`
  Rebuilt long-history datasets generated from `archive/`.
  These files may be regenerated, but only from archived snapshots.

## Agent Safety Rules

- Do not delete `archive/` to save space.
- Do not overwrite an archived snapshot with a newer download.
- Do not hand-edit CSV rows.
- If you need fresher data, run the refresh command and let the tooling update `latest/`, append to `archive/`, and rebuild `merged/`.

## Refresh Command

Use the repository script:

```bash
./scripts/refresh_market_data.sh 15m 60d
```

This will:

1. download the latest market data window
2. archive a dated snapshot
3. refresh `data/latest/`
4. rebuild `data/merged/`

## Periodic Refresh

Recommended minimum schedule:

- `15m`: run at least every 30 days
- `30m`: run at least every 30 days

Safer schedule:

- once per week

Example cron entry:

```cron
0 9 * * 1 cd /Users/chenyousheng/work/workspace/tranding/mstu-trading && ./scripts/refresh_market_data.sh 15m 60d >> logs/data-refresh.log 2>&1
```

Run the command from the repository root so all paths resolve correctly.
