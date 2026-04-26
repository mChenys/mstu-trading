# Package Refactor Design

## Goal

Restructure the repository into a real Python package so the root directory only contains thin entrypoints, assets, scripts, and project metadata while preserving current runtime behavior.

## Scope

This refactor is structural, not behavioral.

- Keep strategy semantics unchanged.
- Keep data file formats and state file locations unchanged.
- Keep current user-facing commands working through compatibility entrypoints.
- Do not redesign the trading logic, backtest logic, or webhook flow in this phase.

## Problems To Solve

- Business code is flattened in the repository root with no domain boundaries.
- Runtime entrypoints and reusable modules are mixed together.
- Import relationships depend on root-level module layout and `sys.path` hacks.
- Tests are also flattened at the root, which makes future maintenance harder.

## Target Layout

```text
mstu_trading/
  __init__.py
  app_runtime.py
  config.py

  strategy/
    __init__.py
    realtime.py
    indicators.py
    indicators_enhanced.py
    fee_model.py

  backtest/
    __init__.py
    engine.py
    optimize.py

  market_data/
    __init__.py
    fetcher.py
    store.py

  trading/
    __init__.py
    confirmation.py
    message_handler.py
    service.py
    execution_notifier.py

  integrations/
    __init__.py
    feishu_gateway.py
    webhook_worker.py
    webhook_daemon.py
    scheduler.py

  web/
    __init__.py
    app.py
    dashboard_service.py

  storage/
    __init__.py
    sqlite_storage.py

tests/
```

## Root Directory Policy

Keep these at the repository root:

- thin compatibility entrypoints: `main.py`, `web_app.py`, `backtest.py`, `optimize_backtest.py`, `scheduler.py`, `webhook_worker.py`, `webhook_daemon.py`
- assets and content: `templates/`, `static/`, `data/`, `docs/`, `scripts/`
- metadata and setup files: `README.md`, `requirements.txt`, `.env.example`

Move reusable business logic into the `mstu_trading/` package.

## Package Boundaries

- `mstu_trading.strategy`: realtime strategy logic and indicator helpers
- `mstu_trading.backtest`: backtest engine and parameter optimization
- `mstu_trading.market_data`: quote fetching and managed market-data archive access
- `mstu_trading.trading`: trade proposal, confirmation, claim, and message handling
- `mstu_trading.integrations`: Feishu and webhook integration workflows
- `mstu_trading.web`: Flask app and dashboard aggregation
- `mstu_trading.storage`: SQLite-backed persistence helpers

## Compatibility Strategy

Use thin root-level wrappers during this phase.

- `web_app.py` imports `app` from `mstu_trading.web.app`
- `backtest.py` delegates to `mstu_trading.backtest.engine`
- `optimize_backtest.py` delegates to `mstu_trading.backtest.optimize`
- `scheduler.py`, `webhook_worker.py`, and `webhook_daemon.py` delegate to package modules

This keeps existing commands and external schedulers working while allowing internal imports to move to package paths.

## Migration Strategy

Migrate in phases rather than moving every file at once.

1. Create package skeleton and `__init__.py` files.
2. Move low-level shared modules first:
   - `app_runtime.py`
   - `config.py`
   - `fee_model.py`
   - `indicators.py`
   - `indicators_enhanced.py`
   - `sqlite_storage.py`
   - `market_data_store.py`
3. Move market-data and integration helpers:
   - `fetcher.py`
   - `feishu_gateway.py`
4. Move trading state and message flow:
   - `trade_confirmation.py`
   - `trade_message_handler.py`
   - `trade_service.py`
   - `execution_notifier.py`
5. Move web aggregation and Flask app:
   - `dashboard_service.py`
   - `web_app.py` implementation
6. Move scheduler and webhook modules.
7. Move strategy and backtest last because they sit at the top of the dependency graph.
8. Move tests into `tests/` once package imports are stable.

## Import Rules

- Stop using `sys.path.insert(...)` for local imports.
- Use absolute package imports from `mstu_trading...`.
- Keep wrapper scripts tiny and free of business logic.

## Path Safety Rules

Moving modules must not change how runtime files are resolved.

- Preserve state files managed by `app_runtime.py`
- Preserve `data/` archive semantics and append-only rules
- Preserve template and static asset discovery for Flask
- Preserve SQLite file resolution

Any path handling tied to `__file__` must be rechecked after module relocation.

## Testing Strategy

Use tests to validate structure before behavior.

- Add import smoke tests for package entrypoints
- Migrate existing tests into `tests/`
- Keep existing behavior-oriented tests green
- Add compile checks for moved modules
- Verify Flask app startup and key CLI entrypoints after wrapper conversion

## Acceptance Criteria

- Business logic lives under `mstu_trading/`
- Root directory contains only thin entrypoints, assets, docs, and metadata
- Existing commands still work through wrappers
- Tests run from `tests/` without relying on root-level import side effects
- No remaining `sys.path.insert(...)` hacks for in-repo imports
- Market-data archive rules remain intact

## Non-Goals

- No strategy tuning
- No backtest model redesign
- No config-system redesign
- No dashboard UI redesign
- No replacement of `unittest` with another framework

