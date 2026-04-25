const activityLogState = [];
let webhookConfigLoaded = false;
let selectedTradeId = "";

function byId(id) {
  return document.getElementById(id);
}

const refs = {
  mstrPrice: byId("mstrPrice"),
  mstrMeta: byId("mstrMeta"),
  mstrTrend: byId("mstrTrend"),
  mstuPrice: byId("mstuPrice"),
  mstuMeta: byId("mstuMeta"),
  mstuSession: byId("mstuSession"),
  tradingDate: byId("tradingDate"),
  marketPhase: byId("marketPhase"),
  signalAction: byId("signalAction"),
  signalReason: byId("signalReason"),
  signalList: byId("signalList"),
  positionSummary: byId("positionSummary"),
  keyLevelsSummary: byId("keyLevelsSummary"),
  backtestSummary: byId("backtestSummary"),
  backtestModel: byId("backtestModel"),
  daemonStatus: byId("daemonStatus"),
  daemonHeartbeat: byId("daemonHeartbeat"),
  daemonCycle: byId("daemonCycle"),
  refreshFlow: byId("refreshFlow"),
  activityLog: byId("activityLog"),
  opsSummary: byId("opsSummary"),
  pendingTrades: byId("pendingTrades"),
  tradeDetail: byId("tradeDetail"),
  opsRecoverButton: byId("opsRecoverButton"),
  webhookUrl: byId("webhookUrl"),
  webhookMode: byId("webhookMode"),
  webhookEnabled: byId("webhookEnabled"),
  webhookStatus: byId("webhookStatus"),
  saveWebhookButton: byId("saveWebhookButton"),
  testWebhookButton: byId("testWebhookButton"),
  webhookLastPushAt: byId("webhookLastPushAt"),
  webhookLastSignal: byId("webhookLastSignal"),
  lastUpdated: byId("lastUpdated"),
  systemLine: byId("systemLine"),
  refreshButton: byId("refreshButton"),
};

function safeSetText(node, value) {
  if (node) {
    node.textContent = value;
  }
}

function safeSetHtml(node, value) {
  if (node) {
    node.innerHTML = value;
  }
}

function formatMoney(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "--";
  }
  return `$${Number(value).toFixed(2)}`;
}

function formatDisplayTime(value) {
  if (!value) {
    return "--";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  const year = date.getFullYear();
  const month = date.getMonth() + 1;
  const day = date.getDate();
  const hour = String(date.getHours()).padStart(2, "0");
  const minute = String(date.getMinutes()).padStart(2, "0");
  const second = String(date.getSeconds()).padStart(2, "0");
  return `${year}年${month}月${day}日 ${hour}:${minute}:${second}`;
}

function buildTradingDateLabel(dateLabel) {
  const now = new Date();
  const hour = String(now.getHours()).padStart(2, "0");
  const minute = String(now.getMinutes()).padStart(2, "0");
  const second = String(now.getSeconds()).padStart(2, "0");
  return `${dateLabel || "--"} ${hour}:${minute}:${second}`;
}

function metricRow(label, value) {
  return `<div class="metric-row"><span>${label}</span><strong>${value}</strong></div>`;
}

function levelChip(label, value, tone = "neutral", secondaryLabel = "", secondaryValue = "") {
  return `
    <article class="level-chip level-chip-${tone}">
      <span class="level-chip-label">${escapeHtml(label)}</span>
      <strong class="level-chip-value">${escapeHtml(value)}</strong>
      ${secondaryValue ? `<small class="level-chip-subvalue">${escapeHtml(secondaryLabel)} ${escapeHtml(secondaryValue)}</small>` : ""}
    </article>
  `;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function dedupeSignalDetails(signal) {
  const reason = String(signal?.reason || "").trim();
  const signalLines = Array.isArray(signal?.signals) ? signal.signals.map((item) => String(item).trim()).filter(Boolean) : [];
  const joined = signalLines.join(" | ");
  if (!signalLines.length) {
    return { reason, details: "" };
  }
  if (reason && (reason === joined || joined.includes(reason) || reason.includes(joined))) {
    return { reason, details: "" };
  }
  return { reason, details: joined };
}

function translateMarketPhase(value) {
  const map = {
    PREMARKET: "盘前",
    REGULAR: "盘中",
    OVERNIGHT: "夜盘",
    CLOSED: "休市",
    OFFLINE: "离线",
    UNKNOWN: "未知",
  };
  return map[String(value || "").toUpperCase()] || String(value || "--");
}

function translateDecisionStatus(value) {
  const map = {
    BUY: "买入",
    SELL: "卖出",
    HOLD: "持有",
    WATCH: "观察",
    BLOCKED: "暂不操作",
    SETUP: "待确认",
    ERROR: "异常",
    OFFLINE: "离线",
  };
  return map[String(value || "").toUpperCase()] || String(value || "--");
}

function pushLog(status, detail) {
  activityLogState.unshift({
    time: new Date().toLocaleTimeString(),
    status,
    detail,
  });
  activityLogState.splice(20);
  renderActivityLog();
}

function renderActivityLog() {
  safeSetHtml(
    refs.activityLog,
    activityLogState
      .map(
        (item) => `
          <div class="log-row">
            <span class="log-time">${item.time}</span>
            <span class="log-status">${item.status}</span>
            <span class="log-detail">${item.detail}</span>
          </div>
        `
      )
      .join("")
  );
}

function renderTrace(trace) {
  if (!Array.isArray(trace)) {
    safeSetHtml(refs.refreshFlow, "");
    return;
  }
  const cards = trace.map(
    (item) => `
      <article class="trace-card ${item.status}">
        <strong>${item.step}</strong>
        <span>${item.status}</span>
        <small>${item.detail}</small>
      </article>
    `
  );
  cards.push(`
    <article class="trace-card ${String((window.__lastDaemonStatus || "offline")).toLowerCase()}">
      <strong>Daemon Status</strong>
      <span>${String(window.__lastDaemonStatus || "offline").toUpperCase()}</span>
      <small>Last heartbeat: ${window.__lastDaemonHeartbeat || "--"}</small>
      <small>Last cycle: ${window.__lastDaemonCycle || "--"}</small>
    </article>
  `);
  safeSetHtml(refs.refreshFlow, cards.join(""));
}

function renderWebhook(webhook) {
  const data = webhook || {};
  if (refs.webhookUrl) refs.webhookUrl.value = data.url || "";
  if (refs.webhookMode) refs.webhookMode.value = data.mode || "trade_only";
  if (refs.webhookEnabled) refs.webhookEnabled.checked = Boolean(data.enabled);
  safeSetText(
    refs.webhookStatus,
    `Status: ${data.last_push_status || "idle"} | ${data.last_push_message || "未发生推送"}`
  );
  safeSetText(refs.webhookLastPushAt, formatDisplayTime(data.last_push_at));
  safeSetText(refs.webhookLastSignal, data.last_signal_summary || "--");
  if (refs.saveWebhookButton) refs.saveWebhookButton.disabled = false;
  if (refs.testWebhookButton) refs.testWebhookButton.disabled = false;
}

function renderDaemon(daemon) {
  const data = daemon || {};
  window.__lastDaemonStatus = String(data.status || "offline");
  window.__lastDaemonHeartbeat = formatDisplayTime(data.last_heartbeat_at);
  window.__lastDaemonCycle = data.last_cycle_status || "--";
}

function summarizePendingTrade(item) {
  const action = String(item?.action || "--").toUpperCase();
  const shares = item?.shares ?? "--";
  const price = formatMoney(item?.price);
  const createdAt = formatDisplayTime(item?.created_at);
  return `${action} ${shares} @ ${price} | ${createdAt}`;
}

function renderTradeDetail(payload) {
  if (!payload || !payload.proposal) {
    safeSetHtml(refs.tradeDetail, "Select a pending trade to inspect its full context.");
    return;
  }
  const proposal = payload.proposal || {};
  const events = Array.isArray(payload.events) ? payload.events : [];
  const outbound = Array.isArray(payload.outbound_messages) ? payload.outbound_messages : [];
  const position = payload.position || {};
  safeSetHtml(
    refs.tradeDetail,
    `
      <div class="ops-detail-grid">
        ${metricRow("Trade ID", escapeHtml(proposal.trade_id || "--"))}
        ${metricRow("Status", escapeHtml(proposal.status || "--"))}
        ${metricRow("Action", escapeHtml(proposal.action || "--"))}
        ${metricRow("Reason", escapeHtml(proposal.reason || "--"))}
        ${metricRow("Position Shares", escapeHtml(position.holding_shares ?? "--"))}
        ${metricRow("Event Count", escapeHtml(events.length))}
        ${metricRow("Outbound Count", escapeHtml(outbound.length))}
        <div class="status-caption">Latest Events</div>
        <pre class="ops-detail-pre">${escapeHtml(
          JSON.stringify(events.slice(0, 5), null, 2)
        )}</pre>
      </div>
    `
  );
}

async function loadTradeDetail(tradeId) {
  if (!tradeId) {
    renderTradeDetail(null);
    return;
  }
  selectedTradeId = tradeId;
  pushLog("info", `加载 trade 详情: ${tradeId}`);
  try {
    const response = await fetch(`/api/trades/${encodeURIComponent(tradeId)}?t=${Date.now()}`, {
      cache: "no-store",
      headers: { "Cache-Control": "no-cache" },
    });
    if (!response.ok) {
      throw new Error(`detail ${response.status}`);
    }
    const data = await response.json();
    renderTradeDetail(data);
  } catch (error) {
    pushLog("error", `Trade 详情加载失败: ${error?.message || ""}`);
    safeSetHtml(refs.tradeDetail, "Trade detail unavailable.");
  }
}

function renderOps(ops) {
  const data = ops || {};
  const pendingTrades = Array.isArray(data.action_required_trades)
    ? data.action_required_trades
    : Array.isArray(data.pending_trades)
      ? data.pending_trades
      : [];
  const stats = data.stats || {};
  const recovery = data.recovery || {};

  safeSetText(
    refs.opsSummary,
    `Action required ${stats.action_required_trade_count ?? stats.pending_trade_count ?? 0} | Events ${stats.recent_event_count ?? 0} | Outbound ${stats.recent_outbound_count ?? 0} | Auto expired ${stats.recent_auto_expired ?? 0}`
  );

  if (!pendingTrades.length) {
    safeSetHtml(refs.pendingTrades, '<div class="ops-empty">No pending trades right now.</div>');
    if (!selectedTradeId) {
      renderTradeDetail(null);
    }
  } else {
    safeSetHtml(
      refs.pendingTrades,
      pendingTrades
        .map(
          (item) => `
            <article class="ops-card">
              <div class="ops-card-header">
                <div class="ops-card-title">${escapeHtml(item.trade_id || "--")}</div>
                <div class="status-pill">${escapeHtml(item.status || "--")}</div>
              </div>
              <div class="ops-card-meta">${escapeHtml(summarizePendingTrade(item))}</div>
              <div class="ops-actions">
                <button class="ops-button" type="button" data-action="detail" data-trade-id="${escapeHtml(item.trade_id || "")}">View Detail</button>
                <button class="ops-button danger" type="button" data-action="expire" data-trade-id="${escapeHtml(item.trade_id || "")}">Mark Expired</button>
              </div>
            </article>
          `
        )
        .join("")
    );
    if (!selectedTradeId && pendingTrades[0]?.trade_id) {
      loadTradeDetail(pendingTrades[0].trade_id);
    }
  }

  if (!pendingTrades.some((item) => item.trade_id === selectedTradeId) && selectedTradeId) {
    renderTradeDetail(null);
    selectedTradeId = "";
  }

  if ((recovery.expired_count || 0) > 0) {
    pushLog("info", `恢复扫描自动过期 ${recovery.expired_count} 条 proposal`);
  }
}

function renderSnapshot(data) {
  const quote = data.quote || {};
  const signal = data.signal || {};
  const position = data.position || {};
  const backtest = data.backtest || {};
  const keyLevels = quote.key_levels || {};
  const mstr = quote.mstr || {};
  const ui = data.ui || {};
  const signalContent = dedupeSignalDetails(signal);

  safeSetText(refs.mstrPrice, formatMoney(mstr.price));
  safeSetText(
    refs.mstrMeta,
    `Change ${mstr.change_pct ?? "--"}% | EMA ${mstr.ema_bullish ? "bullish" : "mixed"} | MACD ${mstr.macd_bullish ? "bullish" : "mixed"}`
  );
  safeSetText(refs.mstrTrend, `Trend: ${mstr.ema_bullish && mstr.macd_bullish ? "confirmed" : "watch"}`);

  safeSetText(refs.mstuPrice, formatMoney(quote.price));
  safeSetText(
    refs.mstuMeta,
    `Change ${quote.change_pct ?? "--"}% | High ${formatMoney(quote.high)} | Low ${formatMoney(quote.low)}`
  );
  safeSetText(refs.mstuSession, `Session: ${quote.session || "unknown"}`);

  safeSetText(refs.tradingDate, buildTradingDateLabel(ui.date_label || "--"));
  safeSetText(refs.marketPhase, translateMarketPhase(ui.market_phase || "UNKNOWN"));
  safeSetText(refs.signalAction, translateDecisionStatus(ui.decision_status || signal.action || "ERROR"));
  if (refs.signalAction) {
    refs.signalAction.className = `signal-action ${String(ui.decision_status || signal.action || "").toLowerCase()}`;
  }
  safeSetText(refs.signalReason, signalContent.reason || "No signal reason");
  safeSetText(refs.signalList, signalContent.details);

  safeSetHtml(
    refs.positionSummary,
    [
      metricRow("Holding Shares", position.holding_shares ?? 0),
      metricRow("Buy Price", formatMoney(position.buy_price)),
      metricRow("Target", formatMoney(position.target_price)),
      metricRow("Stop", formatMoney(position.stop_price)),
      metricRow("Cash", formatMoney(position.available_cash)),
      metricRow("Source", position.position_source || "--"),
    ].join("")
  );

  const levelSignals = Array.isArray(keyLevels.active_signals)
    ? keyLevels.active_signals.map((item) => `${item.label}${item.distance_pct !== undefined ? ` (${item.distance_pct > 0 ? "+" : ""}${item.distance_pct}%)` : ""}`).join(" | ")
    : "";
  const mstuEquivalent = keyLevels.mstu_equivalent || {};
  const executionSymbol = keyLevels.execution_symbol || "MSTU";
  const signalSymbol = keyLevels.signal_symbol || "MSTR";

  safeSetHtml(
    refs.keyLevelsSummary,
    `
      <section class="key-levels-composer">
        <div class="key-levels-top">
          <div class="key-levels-core">
            ${levelChip("第一支撑", formatMoney(keyLevels.s1), "support", `${executionSymbol} 约`, formatMoney(mstuEquivalent.s1))}
            ${levelChip("第二支撑", formatMoney(keyLevels.s2), "support-soft", `${executionSymbol} 约`, formatMoney(mstuEquivalent.s2))}
            ${levelChip("中枢位", formatMoney(keyLevels.pivot), "pivot", `${executionSymbol} 约`, formatMoney(mstuEquivalent.pivot))}
            ${levelChip("第一压力", formatMoney(keyLevels.r1), "resistance", `${executionSymbol} 约`, formatMoney(mstuEquivalent.r1))}
            ${levelChip("第二压力", formatMoney(keyLevels.r2), "resistance-soft", `${executionSymbol} 约`, formatMoney(mstuEquivalent.r2))}
          </div>
          <aside class="key-levels-spotlight">
            <div class="key-levels-spotlight-label">当前区间</div>
            <div class="key-levels-spotlight-value">${escapeHtml(keyLevels.zone_label || "--")}</div>
            <div class="key-levels-spotlight-note">信号参考 ${escapeHtml(signalSymbol)}，执行落在 ${escapeHtml(executionSymbol)}</div>
          </aside>
        </div>
        <div class="key-levels-bottom">
          <article class="key-levels-meta-card">
            <span>最近支撑</span>
            <strong>${escapeHtml(keyLevels.nearest_support_label || "--")}</strong>
            <em>${signalSymbol} ${formatMoney(keyLevels.nearest_support)} | ${executionSymbol} 约 ${formatMoney(mstuEquivalent[keyLevels.nearest_support_label === "第一支撑" ? "s1" : keyLevels.nearest_support_label === "第二支撑" ? "s2" : "s3"])}</em>
          </article>
          <article class="key-levels-meta-card">
            <span>最近压力</span>
            <strong>${escapeHtml(keyLevels.nearest_resistance_label || "--")}</strong>
            <em>${signalSymbol} ${formatMoney(keyLevels.nearest_resistance)} | ${executionSymbol} 约 ${formatMoney(mstuEquivalent[keyLevels.nearest_resistance_label === "第一压力" ? "r1" : keyLevels.nearest_resistance_label === "第二压力" ? "r2" : "r3"])}</em>
          </article>
          <article class="key-levels-meta-card key-levels-meta-emphasis">
            <span>当前命中</span>
            <strong>${escapeHtml(levelSignals || "--")}</strong>
            <em>${escapeHtml(signal.reason || "继续观察")}</em>
          </article>
        </div>
      </section>
    `
  );

  const best = backtest.best_result || {};
  safeSetHtml(
    refs.backtestSummary,
    [
      metricRow("Status", backtest.status || "--"),
      metricRow("Win Rate", best.win_rate !== undefined ? `${best.win_rate}%` : "--"),
      metricRow("Return", best.return_pct !== undefined ? `${best.return_pct}%` : "--"),
      metricRow("Final Value", formatMoney(best.final_value)),
      metricRow("Closed Trades", best.total_closed ?? "--"),
      metricRow("Recommended Gap Up", backtest.recommended?.gap_up_pct ?? "--"),
    ].join("")
  );

  safeSetHtml(
    refs.backtestModel,
    Array.isArray(backtest.model_breakdown)
      ? backtest.model_breakdown
          .map(
            (item) => `
              <article class="model-card">
                <strong>${item.label}</strong>
                <span>${item.value}</span>
                <small>${item.description}</small>
              </article>
            `
          )
          .join("")
      : ""
  );

  renderTrace(data.trace);
  renderDaemon(data.daemon);
  renderOps(data.ops);
  renderWebhook(data.webhook);
  safeSetText(
    refs.systemLine,
    `Signal: ${data.system?.signal_symbol || "MSTR"} | Execution: ${data.system?.execution_symbol || "MSTU"}`
  );
  safeSetText(refs.lastUpdated, `Last updated: ${new Date().toLocaleTimeString()}`);
  pushLog("success", `刷新完成: ${ui.decision_status || signal.action || "UNKNOWN"}`);
}

function renderError(message, errorDetail = "") {
  safeSetText(refs.tradingDate, "--");
  safeSetText(refs.marketPhase, "UNKNOWN");
  safeSetText(refs.signalAction, "ERROR");
  if (refs.signalAction) {
    refs.signalAction.className = "signal-action sell";
  }
  safeSetText(refs.signalReason, message);
  safeSetText(refs.signalList, errorDetail || "请刷新页面或重启 web_app.py");
  safeSetText(refs.mstrMeta, "Signal source unavailable");
  safeSetText(refs.mstuMeta, "Execution quote unavailable");
  safeSetHtml(refs.backtestModel, "");
  window.__lastDaemonStatus = "offline";
  window.__lastDaemonHeartbeat = "--";
  window.__lastDaemonCycle = "--";
  safeSetText(refs.webhookStatus, "Webhook unavailable");
  safeSetText(refs.lastUpdated, `Last updated: ${new Date().toLocaleTimeString()}`);
  pushLog("error", `${message}${errorDetail ? ` | ${errorDetail}` : ""}`);
}

async function saveWebhookConfig() {
  if (!webhookConfigLoaded) {
    pushLog("error", "Webhook 配置尚未加载完成，已阻止覆盖保存");
    return;
  }
  pushLog("info", "保存 Webhook 配置");
  try {
    const response = await fetch("/api/webhook-config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: refs.webhookUrl?.value || "",
        mode: refs.webhookMode?.value || "trade_only",
        enabled: Boolean(refs.webhookEnabled?.checked),
      }),
    });
    const data = await response.json();
    renderWebhook(data);
    pushLog("success", "Webhook 配置已保存");
  } catch (error) {
    pushLog("error", `Webhook 保存失败: ${error?.message || ""}`);
  }
}

async function sendTestWebhook() {
  if (!webhookConfigLoaded) {
    pushLog("error", "Webhook 配置尚未加载完成，暂不发送测试消息");
    return;
  }
  pushLog("info", "发送测试 Webhook 消息");
  try {
    const response = await fetch("/api/webhook-test", { method: "POST" });
    const data = await response.json();
    if (data.webhook) {
      renderWebhook(data.webhook);
    }
    pushLog(data.ok ? "success" : "error", data.message || "测试消息已处理");
  } catch (error) {
    pushLog("error", `测试消息发送失败: ${error?.message || ""}`);
  }
}

async function loadWebhookConfig() {
  pushLog("info", "加载 Webhook 配置");
  if (refs.saveWebhookButton) refs.saveWebhookButton.disabled = true;
  if (refs.testWebhookButton) refs.testWebhookButton.disabled = true;
  try {
    const response = await fetch(`/api/webhook-config?t=${Date.now()}`, {
      cache: "no-store",
      headers: { "Cache-Control": "no-cache" },
    });
    const data = await response.json();
    webhookConfigLoaded = true;
    renderWebhook(data);
    pushLog("success", "Webhook 配置已回填");
  } catch (error) {
    webhookConfigLoaded = false;
    pushLog("error", `Webhook 配置加载失败: ${error?.message || ""}`);
  }
}

async function loadDashboard() {
  pushLog("info", "开始请求 /api/dashboard");
  try {
    const response = await fetch(`/api/dashboard?t=${Date.now()}`, {
      cache: "no-store",
      headers: { "Cache-Control": "no-cache" },
    });
    pushLog("info", `收到响应 ${response.status}`);
    const data = await response.json();
    pushLog("info", "开始渲染 dashboard");
    renderSnapshot(data);
  } catch (error) {
    renderError("Dashboard snapshot unavailable", error?.message || "");
  }
}

async function runRecoveryScan() {
  pushLog("info", "执行恢复扫描");
  try {
    const response = await fetch("/api/ops/recover", { method: "POST" });
    const data = await response.json();
    pushLog("success", `恢复扫描完成，自动过期 ${data.expired_count || 0} 条`);
    await loadDashboard();
  } catch (error) {
    pushLog("error", `恢复扫描失败: ${error?.message || ""}`);
  }
}

async function expireTradeFromDashboard(tradeId) {
  if (!tradeId) {
    return;
  }
  pushLog("info", `手动过期 trade: ${tradeId}`);
  try {
    const response = await fetch(`/api/trades/${encodeURIComponent(tradeId)}/expire`, {
      method: "POST",
    });
    if (!response.ok) {
      throw new Error(`expire ${response.status}`);
    }
    const data = await response.json();
    pushLog("success", `Trade 已过期: ${data.trade_id || tradeId}`);
    selectedTradeId = tradeId;
    await loadDashboard();
    await loadTradeDetail(tradeId);
  } catch (error) {
    pushLog("error", `Trade 过期失败: ${error?.message || ""}`);
  }
}

window.addEventListener("error", (event) => {
  renderError("前端渲染失败", event.message || "");
});

if (refs.refreshButton) {
  refs.refreshButton.addEventListener("click", loadDashboard);
}
if (refs.saveWebhookButton) {
  refs.saveWebhookButton.addEventListener("click", saveWebhookConfig);
}
if (refs.testWebhookButton) {
  refs.testWebhookButton.addEventListener("click", sendTestWebhook);
}
if (refs.opsRecoverButton) {
  refs.opsRecoverButton.addEventListener("click", runRecoveryScan);
}
if (refs.pendingTrades) {
  refs.pendingTrades.addEventListener("click", (event) => {
    const target = event.target.closest("[data-action][data-trade-id]");
    if (!target) {
      return;
    }
    const tradeId = target.getAttribute("data-trade-id") || "";
    const action = target.getAttribute("data-action") || "";
    if (action === "detail") {
      loadTradeDetail(tradeId);
      return;
    }
    if (action === "expire") {
      expireTradeFromDashboard(tradeId);
    }
  });
}

pushLog("info", "Dashboard JS 已加载");
loadWebhookConfig();
loadDashboard();
window.setInterval(loadDashboard, 30000);
