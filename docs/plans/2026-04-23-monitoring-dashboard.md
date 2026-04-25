# Monitoring Dashboard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a local monitoring dashboard with a lightweight Flask backend that visualizes live quote data, strategy output, position state, and backtest summary without changing the existing trading logic.

**Architecture:** Add a thin aggregation layer in front of the existing Python modules. Serve one dashboard page plus one main JSON endpoint so the frontend can poll a consistent snapshot of quote, signal, position, and backtest summary.

**Tech Stack:** Python, Flask, unittest, HTML, CSS, vanilla JavaScript

---

### Task 1: Add Flask dependency and test scaffold

**Files:**
- Modify: `requirements.txt`
- Create: `test_dashboard_service.py`

**Step 1: Write the failing test**

Add a test that imports the future dashboard service module and expects a normalized payload structure.

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest test_dashboard_service.py`
Expected: FAIL because `dashboard_service.py` does not exist yet.

**Step 3: Write minimal implementation**

Create a placeholder `dashboard_service.py` with a `build_dashboard_snapshot()` function that returns a stable dictionary.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest test_dashboard_service.py`
Expected: PASS

### Task 2: Build dashboard aggregation service

**Files:**
- Create: `dashboard_service.py`
- Test: `test_dashboard_service.py`

**Step 1: Write the failing test**

Add tests for:
- successful aggregation path
- quote failure path
- missing position file path
- missing optimization results path

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest test_dashboard_service.py`
Expected: FAIL on missing behavior.

**Step 3: Write minimal implementation**

Implement:
- quote fetch + signal analysis
- position state loader with defaults
- optimization summary loader with safe fallback
- stable response schema with `status` and `error` fields

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest test_dashboard_service.py`
Expected: PASS

### Task 3: Add Flask app and API routes

**Files:**
- Create: `web_app.py`
- Test: `test_dashboard_service.py`

**Step 1: Write the failing test**

Add Flask client tests for:
- `GET /api/health`
- `GET /api/dashboard`
- `GET /`

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest test_dashboard_service.py`
Expected: FAIL because `web_app.py` and routes do not exist.

**Step 3: Write minimal implementation**

Implement Flask app factory with:
- `GET /`
- `GET /api/health`
- `GET /api/dashboard`

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest test_dashboard_service.py`
Expected: PASS

### Task 4: Create dashboard HTML shell

**Files:**
- Create: `templates/dashboard.html`
- Modify: `web_app.py`

**Step 1: Write the failing test**

Extend the `/` route test to assert the rendered page contains dashboard section markers such as `Live Signal`, `Backtest Overview`, and `MSTR -> Signal`.

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest test_dashboard_service.py`
Expected: FAIL because the page shell is not present yet.

**Step 3: Write minimal implementation**

Create the Jinja template with semantic sections and placeholders for JS hydration.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest test_dashboard_service.py`
Expected: PASS

### Task 5: Add frontend styles and polling logic

**Files:**
- Create: `static/dashboard.css`
- Create: `static/dashboard.js`
- Modify: `templates/dashboard.html`

**Step 1: Write the failing test**

Add route tests that request the static assets and verify `200` responses.

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest test_dashboard_service.py`
Expected: FAIL because the assets do not exist yet.

**Step 3: Write minimal implementation**

Implement:
- page layout and visual system
- periodic fetch for `/api/dashboard`
- DOM rendering for quote, signal, position, and backtest summary
- graceful error state rendering

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest test_dashboard_service.py`
Expected: PASS

### Task 6: Verify existing strategy tests still pass

**Files:**
- Test: `test_strategy_guards.py`
- Test: `test_trade_message_handler.py`
- Test: `test_momentum_alignment.py`
- Test: `test_confirmation.py`

**Step 1: Run the verification suite**

Run:
- `.venv/bin/python -m unittest test_dashboard_service.py test_strategy_guards.py test_trade_message_handler.py test_momentum_alignment.py`
- `.venv/bin/python test_confirmation.py`
- `.venv/bin/python -m py_compile web_app.py dashboard_service.py strategy.py fetcher.py backtest.py`

Expected:
- all tests PASS
- `py_compile` succeeds

### Task 7: Document how to launch the dashboard

**Files:**
- Modify: `README.md`

**Step 1: Write the failing documentation gap**

Identify the missing usage section for launching the dashboard locally.

**Step 2: Add minimal documentation**

Document:
- dependency install
- app startup command
- local URL
- what the page shows

**Step 3: Verify docs are accurate**

Run the startup command once and confirm the Flask app boots.
