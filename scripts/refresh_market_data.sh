#!/usr/bin/env bash
set -euo pipefail

# Refresh tracked market data safely.
# This script is the recommended entrypoint for humans and future agents.
# It intentionally delegates to backtest.py because the backtest download flow
# now archives snapshots, updates data/latest, and rebuilds data consumers from
# one place.

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

INTERVAL="${1:-15m}"
PERIOD="${2:-60d}"

.venv/bin/python backtest.py --strategy combined --download --interval "$INTERVAL" --period "$PERIOD" >/tmp/mstu_data_refresh.log
tail -n 20 /tmp/mstu_data_refresh.log
