# Dashboard Responsive Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the monitoring dashboard so it communicates trading state more clearly on desktop, remains usable on mobile, and exposes refresh/loading/stale feedback without changing backend trading logic.

**Architecture:** Keep the existing Flask + server-rendered single-page dashboard, but restructure the HTML into clearer information zones, enrich the frontend state model for refresh lifecycle handling, and tighten CSS around responsive composition and accessibility. The data contract stays on `/api/dashboard`; this work is a UI and interaction-layer refactor with light backend support only if a small extra field is needed.

**Tech Stack:** Flask, Jinja HTML templates, vanilla JavaScript, CSS, pytest/unittest-style existing test suite

---

### Task 1: Define the new page information hierarchy

**Files:**
- Modify: `templates/dashboard.html`
- Review: `static/dashboard.js`
- Review: `static/dashboard.css`

- [ ] **Step 1: Update the HTML shell to match the new content hierarchy**

Replace the current top-of-page structure with:

```html
<html lang="zh-CN">
  <body>
    <div class="shell">
      <header class="hero">
        <div>
          <p class="eyebrow">MSTU Trading Monitor</p>
          <h1>Live Signal</h1>
          <p class="hero-copy">MSTR -> Signal, MSTU -> Execution</p>
        </div>
        <div class="hero-actions">
          <div id="refreshStatusBadge" class="status-badge status-badge-neutral">Idle</div>
          <button id="refreshButton" class="refresh-button" type="button">Refresh</button>
        </div>
      </header>

      <section class="summary-strip" aria-label="关键摘要">
        <article class="summary-card summary-card-primary">
          <span class="summary-label">Decision</span>
          <strong id="summaryDecision" class="summary-value">--</strong>
          <small id="summaryReason">Waiting for snapshot...</small>
        </article>
        <article class="summary-card">
          <span class="summary-label">Market Phase</span>
          <strong id="summaryPhase" class="summary-value">--</strong>
          <small id="summaryTradingDate">--</small>
        </article>
        <article class="summary-card">
          <span class="summary-label">Data Freshness</span>
          <strong id="summaryFreshness" class="summary-value">--</strong>
          <small id="summaryLastSuccess">--</small>
        </article>
        <article class="summary-card">
          <span class="summary-label">Ops Alert</span>
          <strong id="summaryOps" class="summary-value">--</strong>
          <small id="summaryOpsHint">--</small>
        </article>
      </section>
    </div>
  </body>
</html>
```

Keep the existing main panels, but place the new summary strip above the grid so the first screen answers:
- what is the current decision
- whether data is fresh
- whether an operator action is needed

- [ ] **Step 2: Preserve existing panel IDs that already power JS rendering**

Retain these nodes so the refactor does not break current rendering paths:

```text
#mstrPrice
#mstrMeta
#mstrTrend
#mstuPrice
#mstuMeta
#mstuSession
#tradingDate
#marketPhase
#signalAction
#signalReason
#signalList
#positionSummary
#keyLevelsSummary
#backtestSummary
#backtestModel
#refreshFlow
#activityLog
#opsSummary
#pendingTrades
#tradeDetail
#webhookStatus
#webhookLastPushAt
#webhookLastSignal
#systemLine
#lastUpdated
```

- [ ] **Step 3: Add semantic live regions for status changes**

Add these accessibility-focused nodes:

```html
<div id="refreshAnnouncer" class="sr-only" aria-live="polite"></div>
<div id="dashboardErrorBanner" class="banner banner-hidden" role="status" aria-live="polite"></div>
```

Expected result:
- screen readers hear refresh state changes
- users see a clear non-modal error or stale banner at the top

- [ ] **Step 4: Verify the shell still renders**

Run:

```bash
python -m pytest test_dashboard_service.py -q
```

Expected:
- existing dashboard route tests still pass
- any template assertion updates are limited to changed headings or wrapper structure

### Task 2: Add refresh lifecycle state to the frontend

**Files:**
- Modify: `static/dashboard.js`
- Review: `templates/dashboard.html`

- [ ] **Step 1: Introduce a single in-memory UI state object**

At the top of `static/dashboard.js`, replace scattered refresh bookkeeping with:

```js
const uiState = {
  activityLog: [],
  webhookConfigLoaded: false,
  selectedTradeId: "",
  refreshInFlight: false,
  lastSuccessAt: "",
  lastAttemptAt: "",
  staleTimerId: 0,
};
```

Then update existing references:
- `activityLogState` -> `uiState.activityLog`
- `webhookConfigLoaded` -> `uiState.webhookConfigLoaded`
- `selectedTradeId` -> `uiState.selectedTradeId`

- [ ] **Step 2: Add refresh status helpers**

Implement these functions:

```js
function setRefreshBadge(tone, label) {
  if (!refs.refreshStatusBadge) return;
  refs.refreshStatusBadge.className = `status-badge status-badge-${tone}`;
  refs.refreshStatusBadge.textContent = label;
}

function announceRefresh(message) {
  safeSetText(refs.refreshAnnouncer, message);
}

function setErrorBanner(message = "", tone = "neutral") {
  if (!refs.dashboardErrorBanner) return;
  refs.dashboardErrorBanner.className = message
    ? `banner banner-${tone}`
    : "banner banner-hidden";
  refs.dashboardErrorBanner.textContent = message;
}

function computeFreshnessLabel() {
  if (!uiState.lastSuccessAt) return "No data yet";
  const ageMs = Date.now() - new Date(uiState.lastSuccessAt).getTime();
  const ageSec = Math.max(0, Math.floor(ageMs / 1000));
  if (ageSec < 45) return `Fresh (${ageSec}s)`;
  if (ageSec < 120) return `Aging (${ageSec}s)`;
  return `Stale (${ageSec}s)`;
}
```

- [ ] **Step 3: Guard against overlapping refreshes**

Refactor `loadDashboard()` so it exits early when a refresh is already running:

```js
async function loadDashboard({ manual = false } = {}) {
  if (uiState.refreshInFlight) {
    pushLog("info", "已有刷新进行中，本次请求跳过");
    return;
  }
  uiState.refreshInFlight = true;
  uiState.lastAttemptAt = new Date().toISOString();
  setRefreshBadge("loading", manual ? "Refreshing..." : "Auto refresh...");
  announceRefresh(manual ? "正在手动刷新仪表盘" : "正在自动刷新仪表盘");
  if (refs.refreshButton) refs.refreshButton.disabled = true;

  try {
    const response = await fetch(`/api/dashboard?t=${Date.now()}`, {
      cache: "no-store",
      headers: { "Cache-Control": "no-cache" },
    });
    if (!response.ok) {
      throw new Error(`dashboard ${response.status}`);
    }
    const data = await response.json();
    uiState.lastSuccessAt = new Date().toISOString();
    renderSnapshot(data);
    setErrorBanner("");
    setRefreshBadge("success", "Live");
    announceRefresh("仪表盘刷新完成");
  } catch (error) {
    renderError("Dashboard snapshot unavailable", error?.message || "");
  } finally {
    uiState.refreshInFlight = false;
    if (refs.refreshButton) refs.refreshButton.disabled = false;
    renderFreshness();
  }
}
```

- [ ] **Step 4: Add periodic freshness rendering**

Implement:

```js
function renderFreshness() {
  const freshness = computeFreshnessLabel();
  safeSetText(refs.summaryFreshness, freshness);
  safeSetText(
    refs.summaryLastSuccess,
    uiState.lastSuccessAt
      ? `Last success: ${formatDisplayTime(uiState.lastSuccessAt)}`
      : "Last success: --"
  );

  if (freshness.startsWith("Stale")) {
    setRefreshBadge("warning", "Stale");
    setErrorBanner("数据已进入陈旧状态，请检查网络或后台服务。", "warning");
  }
}
```

And initialize:

```js
window.setInterval(() => {
  renderFreshness();
}, 1000);

window.setInterval(() => {
  loadDashboard({ manual: false });
}, 30000);
```

- [ ] **Step 5: Verify refresh behavior manually**

Run:

```bash
python web_app.py
```

Then verify in the browser:
- clicking `Refresh` disables the button until the request finishes
- auto refresh does not stack duplicate requests
- stale messaging appears if requests fail or stop succeeding

### Task 3: Bind the new summary strip to live data

**Files:**
- Modify: `static/dashboard.js`
- Modify: `templates/dashboard.html`

- [ ] **Step 1: Add refs for the new summary nodes**

Extend `refs` with:

```js
summaryDecision: byId("summaryDecision"),
summaryReason: byId("summaryReason"),
summaryPhase: byId("summaryPhase"),
summaryTradingDate: byId("summaryTradingDate"),
summaryFreshness: byId("summaryFreshness"),
summaryLastSuccess: byId("summaryLastSuccess"),
summaryOps: byId("summaryOps"),
summaryOpsHint: byId("summaryOpsHint"),
refreshStatusBadge: byId("refreshStatusBadge"),
refreshAnnouncer: byId("refreshAnnouncer"),
dashboardErrorBanner: byId("dashboardErrorBanner"),
```

- [ ] **Step 2: Populate summary values from the snapshot**

Inside `renderSnapshot(data)`, after computing `signalContent`, set:

```js
safeSetText(refs.summaryDecision, translateDecisionStatus(ui.decision_status || signal.action || "ERROR"));
safeSetText(refs.summaryReason, signalContent.reason || "No signal reason");
safeSetText(refs.summaryPhase, translateMarketPhase(ui.market_phase || "UNKNOWN"));
safeSetText(refs.summaryTradingDate, buildTradingDateLabel(ui.date_label || "--"));
```

Use existing ops stats to produce a short operator summary:

```js
const actionRequiredCount = data.ops?.stats?.action_required_trade_count
  ?? data.ops?.stats?.pending_trade_count
  ?? 0;
safeSetText(refs.summaryOps, actionRequiredCount > 0 ? `${actionRequiredCount} pending` : "Clear");
safeSetText(
  refs.summaryOpsHint,
  actionRequiredCount > 0
    ? "Open Agent Ops to inspect pending trades"
    : "No manual trade action required"
);
```

- [ ] **Step 3: Give the summary decision a stateful tone**

Add:

```js
function setDecisionTone(decision) {
  const normalized = String(decision || "").toLowerCase();
  if (!refs.summaryDecision) return;
  refs.summaryDecision.className = `summary-value summary-value-${normalized || "neutral"}`;
}
```

Call it with:

```js
setDecisionTone(ui.decision_status || signal.action || "error");
```

- [ ] **Step 4: Make errors visible in the summary strip too**

Update `renderError()` so it also sets:

```js
safeSetText(refs.summaryDecision, "Error");
safeSetText(refs.summaryReason, message);
safeSetText(refs.summaryPhase, "Unknown");
safeSetText(refs.summaryTradingDate, "--");
safeSetText(refs.summaryOps, "Check system");
safeSetText(refs.summaryOpsHint, errorDetail || "请刷新页面或检查服务");
setDecisionTone("error");
setRefreshBadge("error", "Offline");
setErrorBanner(`${message}${errorDetail ? `：${errorDetail}` : ""}`, "error");
announceRefresh("仪表盘刷新失败");
```

- [ ] **Step 5: Verify the new first-screen experience**

Manual acceptance criteria:
- first screen on desktop shows decision, phase, freshness, ops alert before scrolling
- first screen on mobile still shows decision + freshness without scrolling past the fold too far

### Task 4: Recompose layout for mobile-first readability without sacrificing desktop density

**Files:**
- Modify: `static/dashboard.css`
- Review: `templates/dashboard.html`

- [ ] **Step 1: Add styles for the new summary strip and banners**

Create styles like:

```css
.hero-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.summary-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 18px;
}

.summary-card {
  padding: 18px;
  border-radius: 22px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(255, 255, 255, 0.03);
}

.banner {
  margin-bottom: 16px;
  padding: 14px 16px;
  border-radius: 16px;
}

.banner-hidden {
  display: none;
}
```

- [ ] **Step 2: Improve keyboard and focus states**

Add:

```css
.refresh-button:focus-visible,
.ops-button:focus-visible,
.webhook-input:focus-visible {
  outline: 2px solid rgba(198, 255, 127, 0.78);
  outline-offset: 2px;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
```

- [ ] **Step 3: Add stronger mobile breakpoints instead of one global collapse**

Split the responsive logic into at least two breakpoints:

```css
@media (max-width: 1024px) {
  .summary-strip,
  .insight-grid,
  .ops-grid,
  .key-levels-bottom,
  .trace-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .key-levels-core {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .shell {
    width: min(100% - 20px, 100%);
    padding-top: 20px;
  }

  .summary-strip,
  .grid,
  .insight-grid,
  .ops-grid,
  .status-grid,
  .webhook-grid,
  .trace-grid,
  .model-grid,
  .key-levels-top,
  .key-levels-bottom,
  .key-levels-core {
    grid-template-columns: 1fr;
  }

  .hero,
  .hero-actions,
  .footer,
  .webhook-secondary-row,
  .ops-toolbar,
  .ops-card-header {
    flex-direction: column;
    align-items: stretch;
  }
}
```

- [ ] **Step 4: Prevent long logs and detail cards from becoming unreadable on phones**

Add:

```css
.activity-log,
.ops-detail {
  overflow: hidden;
}

.ops-detail-pre {
  max-height: 280px;
  overflow: auto;
}

.log-row {
  align-items: start;
}
```

- [ ] **Step 5: Verify layout at representative widths**

Check manually at:
- 1440px desktop
- 1024px narrow laptop/tablet landscape
- 390px phone width

Expected:
- desktop retains dense dashboard feel
- tablet keeps two-column readability where possible
- phone collapses cleanly without truncated primary decisions

### Task 5: Tighten copy, tones, and rendering consistency

**Files:**
- Modify: `static/dashboard.js`
- Modify: `templates/dashboard.html`
- Modify: `static/dashboard.css`

- [ ] **Step 1: Normalize visible copy around one language choice**

Use Chinese for operational labels and keep ticker symbols in English. Apply to:
- refresh badge labels
- error banners
- empty states
- summary labels

Examples:

```text
Decision -> 当前决策
Market Phase -> 市场阶段
Data Freshness -> 数据新鲜度
Ops Alert -> 待处理事项
Live -> 实时
Stale -> 数据过期
Offline -> 服务异常
```

- [ ] **Step 2: Ensure all status surfaces communicate with text and not only color**

For each of these, keep explicit text:
- `summaryDecision`
- `refreshStatusBadge`
- `dashboardErrorBanner`
- `status-pill`
- `trace-card`

Avoid designs where the only clue is green/yellow/red color.

- [ ] **Step 3: Keep rendering safe when using template strings**

Where data still goes through `innerHTML`, confirm all dynamic interpolations use `escapeHtml()` or already formatted primitives. Specifically review:
- `renderTrace()`
- `renderTradeDetail()`
- key levels composer block in `renderSnapshot()`
- backtest model card rendering

- [ ] **Step 4: Re-run the focused test suite**

Run:

```bash
python -m pytest test_dashboard_service.py -q
python -m py_compile web_app.py dashboard_service.py
```

Expected:
- tests pass
- no syntax errors in touched Python files

### Task 6: Smoke test the end-to-end dashboard behavior

**Files:**
- Verify only

- [ ] **Step 1: Start the local app**

Run:

```bash
python web_app.py
```

Expected:
- Flask boots successfully
- local dashboard loads at `http://127.0.0.1:5000`

- [ ] **Step 2: Validate desktop flow**

Check:
- summary strip updates after load
- manual refresh works
- auto refresh updates the “last success” freshness text
- no overlapping refresh requests appear in the log

- [ ] **Step 3: Validate mobile flow**

Use browser responsive mode and check:
- summary strip collapses cleanly
- decision and freshness remain visible early
- key levels, webhook form, and ops details do not overflow horizontally

- [ ] **Step 4: Validate degraded/error behavior**

Simulate temporary backend failure if practical, or stop/restart the app and verify:
- top banner shows an error or stale state
- refresh badge changes from live to error/stale
- existing content does not explode into broken markup

- [ ] **Step 5: Summarize verification evidence before merge**

Record:
- which widths were checked
- whether stale state was observed
- whether any residual mobile rough edges remain

## Self-Review

- Spec coverage check: this plan covers the selected “方案 2” by addressing structural re-layout, refresh lifecycle, mobile responsiveness, semantics/accessibility, and verification.
- Placeholder scan: no `TODO`/`TBD` markers remain; each task has concrete files, functions, CSS blocks, and commands.
- Type consistency check: the plan uses the existing Flask template/static structure and vanilla JS naming, and introduces consistent new IDs/classes for summary, banner, and refresh state handling.
