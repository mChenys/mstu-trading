# Changelog

## 2026-04-25

### Review Strategy Sync

This update syncs the strategy enhancements from `mstu-trading-review` back into the main `mstu-trading` project.

### Added

- BTC market tone inputs in `config.py`, including BTC symbol, EMA periods, and daily tone bias settings.
- BTC trend fetching and daily tone calculation in `fetcher.py`.
- Daily tone state persistence in `strategy.py`, including forward and reverse bias adjustments.
- Enhanced MACD signal analysis in both `strategy.py` and `backtest.py`:
  - bottom and top divergence detection
  - histogram shrinking and color-flip detection
  - golden/dead cross classification above and below the zero axis

### Changed

- Synced the review-branch strategy logic into the main project files:
  - `backtest.py`
  - `config.py`
  - `fetcher.py`
  - `scheduler.py`
  - `strategy.py`
  - `test_strategy_guards.py`
- Updated premarket monitoring language in `scheduler.py` to reflect active T-trading mode.
- Expanded signal output detail in `strategy.py` to include EMA, MACD, VWAP, volume ratio, RSI, and KDJ context.
- Kept `start_all.sh` aligned with the main project's `.venv/bin/python` runtime instead of the review copy's `venv/bin/python` path.

### Operational Notes

- Initialized the local project as a Git repository and connected it to `git@github.com:mChenys/mstu-trading.git`.
- Added `.gitignore` entries for virtual environments, caches, logs, local state files, and generated historical data files.

### Verification

- Python syntax check passed for the updated runtime, strategy, scheduler, and test modules.
- Import smoke check passed for `web_app.py` and `webhook_daemon.py`.
- Test suite passed:
  - `67 passed in 1.83s`

