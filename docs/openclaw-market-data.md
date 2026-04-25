# OpenClaw Market Data Guide

## Purpose

This repository keeps tracked intraday market data inside Git so OpenClaw can
inherit previously archived history on any machine.

The goal is simple:

- preserve minute-level history before Yahoo's rolling window expires
- keep the workflow portable across environments
- prevent future agents from deleting or overwriting long-lived data assets

## What OpenClaw Should Know First

1. `data/archive/` is the durable source of truth.
   Never hand-edit or delete files there.

2. `data/latest/` is the working copy.
   Normal backtests and experiments should read from here unless they explicitly
   need long merged history.

3. `data/merged/` is rebuilt from `data/archive/`.
   If merged files look wrong, rebuild them from archive snapshots instead of
   editing them manually.

4. The refresh entrypoint is repository-local:

```bash
./scripts/refresh_market_data.sh 15m 60d
```

Because the command is relative to the repo, it works after the project is
cloned to another machine, worktree, or OpenClaw workspace.

## Directory Model

```text
data/
├── latest/
│   ├── mstu/15m.csv
│   ├── mstr/15m.csv
│   └── btc-usd/15m.csv
├── archive/
│   ├── mstu/15m/YYYY-MM-DD.csv
│   ├── mstr/15m/YYYY-MM-DD.csv
│   └── btc-usd/15m/YYYY-MM-DD.csv
└── merged/
    ├── mstu/15m.csv
    ├── mstr/15m.csv
    └── btc-usd/15m.csv
```

## Safe Agent Workflow

### Refresh the latest snapshot

```bash
./scripts/refresh_market_data.sh 15m 60d
```

This will:

1. download the latest rolling window
2. append a dated snapshot into `data/archive/`
3. update `data/latest/`
4. rebuild `data/merged/`

### Rebuild merged history only

```bash
.venv/bin/python market_data_store.py merge-all
```

Use this if archive files already exist and you only need to regenerate the
merged long-history files.

### Run a health check before trusting the data

```bash
.venv/bin/python market_data_store.py health-check
```

If this returns `"status": "ok"`, the tracked `latest / archive / merged`
layers are present and readable.

### Inspect the current data inventory

```bash
.venv/bin/python market_data_store.py inventory
```

Use this for a quick human-readable summary of:

- which symbols are present
- which intervals exist
- snapshot counts
- latest and merged time ranges

## Rules For Future Agents

- Do not delete `data/archive/` to reduce repository size.
- Do not replace an existing archive snapshot with a new file.
- Do not edit CSV rows by hand unless the user explicitly requests a repair.
- Do not move the data directory out of the repository unless the user asks for
  a different storage strategy.
- Prefer repository-relative commands in docs, scripts, and automation.

## Why The Data Is Tracked In Git

These files are intentionally versioned so OpenClaw can pull the accumulated
history on a fresh environment without depending on one specific machine.

Without tracked snapshots, future environments would only see the most recent
60-day intraday window and longer backtests would become impossible.
