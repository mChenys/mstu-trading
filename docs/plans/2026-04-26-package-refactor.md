# Package Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move the repository from a flat root-level module layout to a structured `mstu_trading` package while preserving runtime behavior and current entrypoint commands.

**Architecture:** Build the new package in place, move code by dependency layer, and keep root-level wrapper scripts as compatibility shims. Delay large dependency hubs like realtime strategy and backtest engine until shared infrastructure has already moved, then migrate tests into `tests/` and verify package-based execution end to end.

**Tech Stack:** Python, Flask, unittest, Backtrader, yfinance, SQLite

---

### Task 1: Create package skeleton

**Files:**
- Create: `mstu_trading/__init__.py`
- Create: `mstu_trading/strategy/__init__.py`
- Create: `mstu_trading/backtest/__init__.py`
- Create: `mstu_trading/market_data/__init__.py`
- Create: `mstu_trading/trading/__init__.py`
- Create: `mstu_trading/integrations/__init__.py`
- Create: `mstu_trading/web/__init__.py`
- Create: `mstu_trading/storage/__init__.py`
- Test: `tests/test_package_imports.py`

**Step 1: Write the failing test**

Create `tests/test_package_imports.py` with import smoke tests for every package namespace listed above.

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_package_imports -v`
Expected: FAIL because the package directories or `__init__.py` files do not exist yet.

**Step 3: Write minimal implementation**

Create the package directories and minimal `__init__.py` marker files.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest tests.test_package_imports -v`
Expected: PASS

**Step 5: Commit**

```bash
git add mstu_trading tests/test_package_imports.py
git commit -m "refactor: add package skeleton"
```

### Task 2: Move low-level shared modules into package

**Files:**
- Create: `mstu_trading/app_runtime.py`
- Create: `mstu_trading/config.py`
- Create: `mstu_trading/strategy/fee_model.py`
- Create: `mstu_trading/strategy/indicators.py`
- Create: `mstu_trading/strategy/indicators_enhanced.py`
- Create: `mstu_trading/storage/sqlite_storage.py`
- Create: `mstu_trading/market_data/store.py`
- Modify: `app_runtime.py`
- Modify: `config.py`
- Modify: `fee_model.py`
- Modify: `indicators.py`
- Modify: `indicators_enhanced.py`
- Modify: `sqlite_storage.py`
- Modify: `market_data_store.py`
- Test: `tests/test_package_imports.py`
- Test: `test_fee_model.py`
- Test: `test_sqlite_storage.py`
- Test: `test_market_data_store.py`

**Step 1: Write the failing test**

Extend `tests/test_package_imports.py` to import:
- `mstu_trading.app_runtime`
- `mstu_trading.config`
- `mstu_trading.strategy.fee_model`
- `mstu_trading.strategy.indicators`
- `mstu_trading.strategy.indicators_enhanced`
- `mstu_trading.storage.sqlite_storage`
- `mstu_trading.market_data.store`

**Step 2: Run test to verify it fails**

Run:
- `.venv/bin/python -m unittest tests.test_package_imports -v`
- `.venv/bin/python -m unittest test_fee_model.py test_sqlite_storage.py test_market_data_store.py -v`

Expected: import failures because the package modules are not implemented.

**Step 3: Write minimal implementation**

- Move module bodies into package locations.
- Convert internal imports to `mstu_trading...` absolute imports.
- Replace root files with thin compatibility wrappers that re-export the public names from the new package modules.

**Step 4: Run test to verify it passes**

Run:
- `.venv/bin/python -m unittest tests.test_package_imports -v`
- `.venv/bin/python -m unittest test_fee_model.py test_sqlite_storage.py test_market_data_store.py -v`
- `.venv/bin/python -m py_compile app_runtime.py config.py fee_model.py indicators.py indicators_enhanced.py sqlite_storage.py market_data_store.py`

Expected: PASS

**Step 5: Commit**

```bash
git add mstu_trading app_runtime.py config.py fee_model.py indicators.py indicators_enhanced.py sqlite_storage.py market_data_store.py tests/test_package_imports.py
git commit -m "refactor: move shared modules into package"
```

### Task 3: Move market-data fetcher and Feishu gateway

**Files:**
- Create: `mstu_trading/market_data/fetcher.py`
- Create: `mstu_trading/integrations/feishu_gateway.py`
- Modify: `fetcher.py`
- Modify: `feishu_gateway.py`
- Test: `test_fetcher_quote.py`

**Step 1: Write the failing test**

Add or extend tests to import and exercise:
- `mstu_trading.market_data.fetcher`
- `mstu_trading.integrations.feishu_gateway`

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest test_fetcher_quote.py -v`
Expected: FAIL on broken imports after module movement.

**Step 3: Write minimal implementation**

- Move implementations into package modules.
- Update imports to reference moved config, indicators, and app runtime modules.
- Leave root modules as wrappers.

**Step 4: Run test to verify it passes**

Run:
- `.venv/bin/python -m unittest test_fetcher_quote.py -v`
- `.venv/bin/python -m py_compile fetcher.py feishu_gateway.py mstu_trading/market_data/fetcher.py mstu_trading/integrations/feishu_gateway.py`

Expected: PASS

**Step 5: Commit**

```bash
git add mstu_trading fetcher.py feishu_gateway.py test_fetcher_quote.py
git commit -m "refactor: move market data and feishu modules"
```

### Task 4: Move trading state and confirmation flow

**Files:**
- Create: `mstu_trading/trading/confirmation.py`
- Create: `mstu_trading/trading/message_handler.py`
- Create: `mstu_trading/trading/service.py`
- Create: `mstu_trading/trading/execution_notifier.py`
- Modify: `trade_confirmation.py`
- Modify: `trade_message_handler.py`
- Modify: `trade_service.py`
- Modify: `execution_notifier.py`
- Test: `test_confirmation.py`
- Test: `test_trade_message_handler.py`
- Test: `test_trade_service.py`

**Step 1: Write the failing test**

Add package import checks and ensure existing trade-flow tests exercise the moved modules through both package imports and compatibility wrappers.

**Step 2: Run test to verify it fails**

Run:
- `.venv/bin/python test_confirmation.py`
- `.venv/bin/python -m unittest test_trade_message_handler.py test_trade_service.py -v`

Expected: FAIL if imports still point at root module locations.

**Step 3: Write minimal implementation**

- Move the four trading modules into `mstu_trading/trading/`.
- Update imports to reference package paths for config, storage, integrations, and strategy helpers.
- Keep root wrappers stable.

**Step 4: Run test to verify it passes**

Run:
- `.venv/bin/python test_confirmation.py`
- `.venv/bin/python -m unittest test_trade_message_handler.py test_trade_service.py -v`
- `.venv/bin/python -m py_compile trade_confirmation.py trade_message_handler.py trade_service.py execution_notifier.py`

Expected: PASS

**Step 5: Commit**

```bash
git add mstu_trading trade_confirmation.py trade_message_handler.py trade_service.py execution_notifier.py test_confirmation.py test_trade_message_handler.py test_trade_service.py
git commit -m "refactor: move trading workflow modules"
```

### Task 5: Move web service implementation

**Files:**
- Create: `mstu_trading/web/dashboard_service.py`
- Create: `mstu_trading/web/app.py`
- Modify: `dashboard_service.py`
- Modify: `web_app.py`
- Test: `test_dashboard_service.py`

**Step 1: Write the failing test**

Update the dashboard tests so they import `mstu_trading.web.dashboard_service` and `mstu_trading.web.app`, while still exercising the root `web_app.py` wrapper.

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest test_dashboard_service.py -v`
Expected: FAIL because the imports or Flask app creation path are not yet package-based.

**Step 3: Write minimal implementation**

- Move the dashboard aggregation layer into `mstu_trading/web/dashboard_service.py`.
- Move the Flask app creation into `mstu_trading/web/app.py`.
- Ensure template and static discovery still resolves from the repository root.
- Reduce root `web_app.py` to a thin wrapper.

**Step 4: Run test to verify it passes**

Run:
- `.venv/bin/python -m unittest test_dashboard_service.py -v`
- `.venv/bin/python -m py_compile dashboard_service.py web_app.py mstu_trading/web/dashboard_service.py mstu_trading/web/app.py`

Expected: PASS

**Step 5: Commit**

```bash
git add mstu_trading dashboard_service.py web_app.py test_dashboard_service.py
git commit -m "refactor: move web app implementation"
```

### Task 6: Move scheduler and webhook modules

**Files:**
- Create: `mstu_trading/integrations/scheduler.py`
- Create: `mstu_trading/integrations/webhook_worker.py`
- Create: `mstu_trading/integrations/webhook_daemon.py`
- Modify: `scheduler.py`
- Modify: `webhook_worker.py`
- Modify: `webhook_daemon.py`
- Test: `test_scheduler.py`
- Test: `test_webhook_worker.py`
- Test: `test_webhook_daemon.py`

**Step 1: Write the failing test**

Update tests to import the package modules first, then assert the root wrappers still expose the same callable entrypoints.

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest test_scheduler.py test_webhook_worker.py test_webhook_daemon.py -v`
Expected: FAIL on import errors or broken wrapper behavior.

**Step 3: Write minimal implementation**

- Move implementations into `mstu_trading/integrations/`.
- Update imports to package paths.
- Keep root command scripts thin and executable.

**Step 4: Run test to verify it passes**

Run:
- `.venv/bin/python -m unittest test_scheduler.py test_webhook_worker.py test_webhook_daemon.py -v`
- `.venv/bin/python -m py_compile scheduler.py webhook_worker.py webhook_daemon.py`

Expected: PASS

**Step 5: Commit**

```bash
git add mstu_trading scheduler.py webhook_worker.py webhook_daemon.py test_scheduler.py test_webhook_worker.py test_webhook_daemon.py
git commit -m "refactor: move scheduler and webhook modules"
```

### Task 7: Move realtime strategy and backtest engines

**Files:**
- Create: `mstu_trading/strategy/realtime.py`
- Create: `mstu_trading/backtest/engine.py`
- Create: `mstu_trading/backtest/optimize.py`
- Modify: `strategy.py`
- Modify: `backtest.py`
- Modify: `optimize_backtest.py`
- Modify: `main.py`
- Test: `test_strategy_guards.py`
- Test: `test_momentum_alignment.py`
- Test: `test_backtest_btc_tone.py`
- Test: `test_backtest_data_limits.py`
- Test: `test_backtest_experiments.py`

**Step 1: Write the failing test**

Extend or adjust tests to import:
- `mstu_trading.strategy.realtime`
- `mstu_trading.backtest.engine`
- `mstu_trading.backtest.optimize`

Also add smoke assertions that root wrappers still expose the expected entrypoints or classes.

**Step 2: Run test to verify it fails**

Run:
- `.venv/bin/python -m unittest test_strategy_guards.py test_momentum_alignment.py -v`
- `.venv/bin/python -m unittest test_backtest_btc_tone.py test_backtest_data_limits.py test_backtest_experiments.py -v`

Expected: FAIL until strategy and backtest imports are package-based.

**Step 3: Write minimal implementation**

- Move realtime strategy logic into `mstu_trading/strategy/realtime.py`.
- Move backtest engine and optimizer into package modules.
- Replace root files with wrappers or delegated `main()` execution.
- Remove local `sys.path.insert(...)` hacks.

**Step 4: Run test to verify it passes**

Run:
- `.venv/bin/python -m unittest test_strategy_guards.py test_momentum_alignment.py -v`
- `.venv/bin/python -m unittest test_backtest_btc_tone.py test_backtest_data_limits.py test_backtest_experiments.py -v`
- `.venv/bin/python -m py_compile strategy.py backtest.py optimize_backtest.py main.py`

Expected: PASS

**Step 5: Commit**

```bash
git add mstu_trading strategy.py backtest.py optimize_backtest.py main.py test_strategy_guards.py test_momentum_alignment.py test_backtest_btc_tone.py test_backtest_data_limits.py test_backtest_experiments.py
git commit -m "refactor: move strategy and backtest engines"
```

### Task 8: Move tests into tests package

**Files:**
- Create: `tests/__init__.py`
- Modify: `tests/test_package_imports.py`
- Move: `test_backtest_btc_tone.py` to `tests/test_backtest_btc_tone.py`
- Move: `test_backtest_data_limits.py` to `tests/test_backtest_data_limits.py`
- Move: `test_backtest_experiments.py` to `tests/test_backtest_experiments.py`
- Move: `test_confirmation.py` to `tests/test_confirmation.py`
- Move: `test_dashboard_service.py` to `tests/test_dashboard_service.py`
- Move: `test_fee_model.py` to `tests/test_fee_model.py`
- Move: `test_fetcher_quote.py` to `tests/test_fetcher_quote.py`
- Move: `test_market_data_health.py` to `tests/test_market_data_health.py`
- Move: `test_market_data_inventory.py` to `tests/test_market_data_inventory.py`
- Move: `test_market_data_inventory_table.py` to `tests/test_market_data_inventory_table.py`
- Move: `test_market_data_store.py` to `tests/test_market_data_store.py`
- Move: `test_momentum_alignment.py` to `tests/test_momentum_alignment.py`
- Move: `test_run_scripts.py` to `tests/test_run_scripts.py`
- Move: `test_scheduler.py` to `tests/test_scheduler.py`
- Move: `test_sqlite_storage.py` to `tests/test_sqlite_storage.py`
- Move: `test_strategy_guards.py` to `tests/test_strategy_guards.py`
- Move: `test_trade_message_handler.py` to `tests/test_trade_message_handler.py`
- Move: `test_trade_service.py` to `tests/test_trade_service.py`
- Move: `test_webhook_daemon.py` to `tests/test_webhook_daemon.py`
- Move: `test_webhook_worker.py` to `tests/test_webhook_worker.py`

**Step 1: Write the failing test**

Add or update a discovery smoke test so `python -m unittest discover -s tests -v` is the canonical test command.

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest discover -s tests -v`
Expected: FAIL until imports and moved file locations are corrected.

**Step 3: Write minimal implementation**

- Move every test file into `tests/`.
- Update imports and any filesystem assumptions that depend on root-level test files.
- Keep the test suite runnable through standard `unittest discover`.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest discover -s tests -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests
git commit -m "refactor: move tests into tests package"
```

### Task 9: Verify entrypoint compatibility and documentation

**Files:**
- Modify: `README.md`
- Test: `tests/test_run_scripts.py`

**Step 1: Write the failing documentation gap**

Update the run-script tests or add smoke coverage for package-backed wrappers:
- `python web_app.py`
- `python backtest.py --help`
- `python optimize_backtest.py --help`
- `python scheduler.py`

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_run_scripts -v`
Expected: FAIL if wrapper scripts no longer match documented behavior.

**Step 3: Write minimal implementation**

- Update `README.md` to describe the package layout and preserved commands.
- Ensure wrapper scripts still work as documented.

**Step 4: Run test to verify it passes**

Run:
- `.venv/bin/python -m unittest tests.test_run_scripts -v`
- `.venv/bin/python -m py_compile web_app.py backtest.py optimize_backtest.py scheduler.py webhook_worker.py webhook_daemon.py main.py`

Expected: PASS

**Step 5: Commit**

```bash
git add README.md tests/test_run_scripts.py web_app.py backtest.py optimize_backtest.py scheduler.py webhook_worker.py webhook_daemon.py main.py
git commit -m "docs: document package-backed entrypoints"
```

### Task 10: Final verification

**Files:**
- Test: `tests/`

**Step 1: Run the verification suite**

Run:
- `.venv/bin/python -m unittest discover -s tests -v`
- `.venv/bin/python -m py_compile $(find mstu_trading -name '*.py' | sort) main.py web_app.py backtest.py optimize_backtest.py scheduler.py webhook_worker.py webhook_daemon.py`

Expected:
- all tests PASS
- all modules compile cleanly

**Step 2: Manual runtime smoke checks**

Run:
- `.venv/bin/python web_app.py`
- `.venv/bin/python backtest.py --help`
- `.venv/bin/python optimize_backtest.py --help`

Expected:
- Flask app boots
- CLI help renders without import errors

**Step 3: Commit**

```bash
git add -A
git commit -m "refactor: complete package layout migration"
```
