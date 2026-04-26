const uiState = {
  activityLog: [],
  webhookConfigLoaded: false,
  selectedTradeId: "",
  refreshInFlight: false,
  lastSuccessAt: "",
  locale: "zh-CN",
};

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
  toneDirection: byId("toneDirection"),
  toneSummary: byId("toneSummary"),
  toneBias: byId("toneBias"),
  toneMeta: byId("toneMeta"),
  technicalSignals: byId("technicalSignals"),
  positionSummary: byId("positionSummary"),
  keyLevelsSummary: byId("keyLevelsSummary"),
  backtestSummary: byId("backtestSummary"),
  backtestModel: byId("backtestModel"),
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
  languageSwitcher: byId("languageSwitcher"),
};

const I18N = {
  "zh-CN": {
    "page.title": "MSTU 监控看板",
    "language.label": "页面语言",
    "hero.eyebrow": "MSTU 交易监控台",
    "hero.title": "实时信号看板",
    "hero.copy": "MSTR -> 信号判断，MSTU -> 执行落地",
    "buttons.refresh": "立即刷新",
    "buttons.saveConfig": "保存配置",
    "buttons.sendTest": "发送测试消息",
    "buttons.runRecovery": "执行恢复扫描",
    "summary.decision": "当前决策",
    "summary.phase": "市场阶段",
    "summary.freshness": "数据新鲜度",
    "summary.ops": "待处理事项",
    "panels.signalChain": "信号链路",
    "panels.strategyAction": "策略动作",
    "panels.positionState": "仓位状态",
    "panels.technicalTone": "技术信号与做T基调",
    "panels.keyLevels": "关键价位",
    "panels.backtestOverview": "回测概览",
    "panels.webhookPush": "Webhook 推送",
    "panels.agentOps": "Agent 运维",
    "panels.refreshFlow": "刷新链路",
    "feeds.mstr": "MSTR 信号源",
    "feeds.mstu": "MSTU 执行标的",
    "feeds.chainCopy": "MSTR -> Signal -> MSTU",
    "labels.tradingDate": "交易日期",
    "labels.marketPhase": "市场阶段",
    "labels.decisionStatus": "决策状态",
    "labels.tModelBreakdown": "做T模型拆解",
    "labels.activityLog": "活动日志",
    "webhook.config": "推送配置",
    "webhook.status": "推送状态",
    "webhook.url": "飞书 Webhook 地址",
    "webhook.mode": "推送模式",
    "webhook.modeTradeOnly": "仅推送 BUY/SELL",
    "webhook.modeAll": "推送所有状态",
    "webhook.enable": "启用推送",
    "webhook.lastPushTime": "最近推送时间",
    "webhook.lastSignal": "最近推送信号",
    "webhook.placeholder": "https://open.feishu.cn/open-apis/bot/v2/hook/...",
    "ops.actionRequiredTrades": "待处理交易",
    "ops.tradeDetail": "交易详情",
    "ops.tradeDetailEmpty": "选择一条待处理交易后，这里会显示完整上下文。",
    "ops.pendingNone": "当前没有待处理交易。",
    "ops.viewDetail": "查看详情",
    "ops.markExpired": "标记过期",
    "ops.summary": "待处理 {count} | 事件 {events} | 推送 {outbound} | 自动过期 {expired}",
    "ops.summaryHintPending": "打开 Agent Ops 查看待处理交易",
    "ops.summaryHintClear": "当前无需人工处理",
    "ops.countPending": "{count} 条待处理",
    "ops.countClear": "已清空",
    "ops.latestEvents": "最近事件",
    "technical.empty": "当前暂无可展示的技术信号。",
    "technical.unavailable": "当前无法渲染技术信号，请刷新页面或检查服务。",
    "technical.group.structure": "结构与趋势",
    "technical.group.indicator": "动量与指标",
    "technical.group.risk": "位置与风险",
    "technical.group.other": "补充说明",
    "technical.title": "技术信号",
    "tone.kicker": "综合 MSTR + BTC 判断",
    "tone.neutral": "中性节奏",
    "tone.bullish": "偏正T节奏",
    "tone.bullish_strong": "强正T节奏",
    "tone.bearish": "偏反T节奏",
    "tone.bearish_strong": "强反T节奏",
    "tone.waiting": "等待基调判断...",
    "tone.noDirection": "暂无明显的 MSTR + BTC 共振方向。",
    "tone.bias": "正T阈值 {forward} / 反T阈值 {reverse}",
    "tone.meta": "当前动作倾向：{action}。这个节奏会影响盘中更偏正T还是反T。",
    "tone.errorSummary": "无法获取做T基调，请检查行情与策略服务。",
    "tone.errorBias": "正T阈值 / 反T阈值：--",
    "tone.errorMeta": "基调数据缺失时，建议先确认 MSTR 与 BTC 行情链路。",
    "status.idle": "空闲",
    "status.loadingManual": "手动刷新中",
    "status.loadingAuto": "自动刷新中",
    "status.live": "实时",
    "status.stale": "数据过期",
    "status.offline": "服务异常",
    "status.skipped": "本次跳过",
    "status.success": "成功",
    "status.waitingSnapshot": "等待快照加载...",
    "status.loadingSignalSource": "正在加载信号源...",
    "status.loadingExecutionQuote": "正在加载执行报价...",
    "status.trendPlaceholder": "趋势：--",
    "status.sessionPlaceholder": "时段：--",
    "freshness.initial": "等待首轮刷新",
    "freshness.live": "实时 ({age}s)",
    "freshness.aging": "趋于陈旧 ({age}s)",
    "freshness.stale": "数据过期 ({age}s)",
    "freshness.lastSuccess": "最近成功刷新：{time}",
    "freshness.lastSuccessEmpty": "最近成功刷新：--",
    "banner.stale": "数据已进入陈旧状态，请检查网络或后台服务。",
    "banner.renderError": "前端渲染失败",
    "banner.snapshotUnavailable": "Dashboard snapshot unavailable",
    "announce.refreshManual": "正在手动刷新仪表盘",
    "announce.refreshAuto": "正在自动刷新仪表盘",
    "announce.refreshDone": "仪表盘刷新完成",
    "announce.refreshError": "仪表盘刷新失败",
    "market.PREMARKET": "盘前",
    "market.REGULAR": "盘中",
    "market.OVERNIGHT": "夜盘",
    "market.CLOSED": "休市",
    "market.OFFLINE": "离线",
    "market.UNKNOWN": "未知",
    "session.regular": "盘中",
    "session.premarket": "盘前",
    "session.overnight": "夜盘",
    "session.closed": "休市",
    "session.unknown": "未知",
    "decision.BUY": "买入",
    "decision.SELL": "卖出",
    "decision.HOLD": "持有",
    "decision.WATCH": "观察",
    "decision.BLOCKED": "暂不操作",
    "decision.SETUP": "待确认",
    "decision.ERROR": "异常",
    "decision.OFFLINE": "离线",
    "decision.PREMARKET": "盘前观察",
    "meta.change": "涨跌",
    "meta.high": "高点",
    "meta.low": "低点",
    "meta.ema": "EMA",
    "meta.macd": "MACD",
    "meta.bullish": "多头",
    "meta.mixed": "混合",
    "meta.confirmed": "确认",
    "meta.watch": "观察",
    "meta.session": "时段",
    "meta.trend": "趋势",
    "summary.noSignalReason": "暂无动作原因",
    "strategy.buy": "满足当前开仓条件，可以按节奏考虑正T执行。",
    "strategy.sell": "当前更偏兑现或减仓节奏，优先检查止盈止损与仓位释放。",
    "strategy.timeBlocked": "当前触发了时段限制，信号成立也不建议新开仓。",
    "strategy.premarket": "当前仍处于盘前观察阶段，等待正式交易时段确认。",
    "strategy.hold": "当前未形成更优的盘中执行动作，继续观察。",
    "error.signalList": "请刷新页面或重启 web_app.py",
    "error.signalSourceUnavailable": "信号源暂不可用",
    "error.executionUnavailable": "执行报价暂不可用",
    "error.webhookUnavailable": "Webhook 不可用",
    "error.summaryOps": "检查系统",
    "error.summaryOpsHint": "请刷新页面或检查服务",
    "error.errorTitle": "异常",
    "position.holdingShares": "持仓股数",
    "position.buyPrice": "买入价格",
    "position.target": "目标价",
    "position.stop": "止损价",
    "position.cash": "可用资金",
    "position.source": "仓位来源",
    "keyLevels.s1": "第一支撑",
    "keyLevels.s2": "第二支撑",
    "keyLevels.pivot": "中枢位",
    "keyLevels.r1": "第一压力",
    "keyLevels.r2": "第二压力",
    "keyLevels.executionApprox": "{symbol} 约",
    "keyLevels.currentZone": "当前区间",
    "keyLevels.currentZoneNote": "信号参考 {signal}，执行落在 {execution}",
    "keyLevels.nearestSupport": "最近支撑",
    "keyLevels.nearestResistance": "最近压力",
    "keyLevels.currentHit": "当前命中",
    "keyLevels.continueWatch": "继续观察",
    "keyLevels.level.S1": "第一支撑",
    "keyLevels.level.S2": "第二支撑",
    "keyLevels.level.S3": "第三支撑",
    "keyLevels.level.R1": "第一压力",
    "keyLevels.level.R2": "第二压力",
    "keyLevels.level.R3": "第三压力",
    "tone.reason.NO_CLEAR_DIRECTION": "无明显方向信号",
    "tone.reason.BTC_BULLISH": "BTC 涨{change_pct}%并保持多头结构",
    "tone.reason.BTC_BEARISH": "BTC 跌{change_pct}%并保持空头结构",
    "tone.reason.MSTR_GAP_UP": "MSTR 高开 {change_pct}%",
    "tone.reason.MSTR_GAP_DOWN": "MSTR 低开 {change_pct}%",
    "tone.reason.MSTR_BTC_RESONANCE_BULLISH": "MSTR + BTC 均线共振多头",
    "tone.reason.MSTR_BTC_RESONANCE_BEARISH": "MSTR + BTC 均线共振空头",
    "backtest.status": "状态",
    "backtest.winRate": "胜率",
    "backtest.return": "收益率",
    "backtest.finalValue": "最终资产",
    "backtest.closedTrades": "已平仓次数",
    "backtest.recommendedGapUp": "推荐高开阈值",
    "trace.daemonStatus": "守护进程状态",
    "trace.lastHeartbeat": "最近心跳：{value}",
    "trace.lastCycle": "最近周期：{value}",
    "trace.step.webhook": "webhook",
    "trace.step.position": "仓位",
    "trace.step.backtest": "回测",
    "trace.step.ops": "运维",
    "trace.step.daemon": "守护进程",
    "trace.step.quote": "行情",
    "trace.step.signal": "策略",
    "trace.step.snapshot": "快照",
    "trace.status.running": "进行中",
    "trace.status.success": "成功",
    "trace.status.error": "异常",
    "trace.status.offline": "离线",
    "trace.status.stale": "过期",
    "trace.status.idle": "空闲",
    "trace.detail.WEBHOOK_CONFIG_LOADING": "读取 Webhook 配置",
    "trace.detail.WEBHOOK_CONFIG_LOADED": "Webhook 配置已加载",
    "trace.detail.POSITION_LOADING": "读取持仓状态",
    "trace.detail.POSITION_LOADED": "持仓状态已加载",
    "trace.detail.BACKTEST_LOADING": "读取回测摘要",
    "trace.detail.BACKTEST_LOADED": "回测摘要已加载",
    "trace.detail.OPS_LOADING": "读取 Agent 运维视图",
    "trace.detail.OPS_LOADED": "Agent 运维视图已加载",
    "trace.detail.DAEMON_LOADING": "读取 webhook daemon 心跳",
    "trace.detail.DAEMON_STATUS": "daemon 状态：{status}",
    "trace.detail.QUOTE_LOADING": "获取 MSTU/MSTR 行情",
    "trace.detail.QUOTE_LOADED": "行情获取完成",
    "trace.detail.QUOTE_ERROR": "行情获取失败：{error}",
    "trace.detail.SIGNAL_ANALYZING": "执行策略分析",
    "trace.detail.SIGNAL_ACTION": "策略动作：{action}",
    "trace.detail.SNAPSHOT_DONE": "本次刷新完成",
    "trace.detail.WEBHOOK_DEDUPED": "Webhook 去重，未重复推送",
    "trace.detail.WEBHOOK_PUSHING": "推送飞书 Webhook",
    "trace.detail.WEBHOOK_PUSH_SUCCESS": "Webhook 推送成功",
    "trace.detail.WEBHOOK_PUSH_ERROR": "Webhook 推送失败：{error}",
    "system.line": "信号源：{signal} | 执行标的：{execution}",
    "system.lastUpdated": "最近更新：{time}",
    "webhook.statusLine": "状态：{status} | {message}",
    "webhook.message.WEBHOOK_SKIPPED_BY_MODE": "当前模式下不触发推送",
    "webhook.message.WEBHOOK_DEDUPED": "同一信号已推送，已去重",
    "webhook.message.WEBHOOK_PUSH_SUCCESS": "推送成功",
    "webhook.message.WEBHOOK_PUSH_ERROR": "推送失败：{error}",
    "webhook.message.WEBHOOK_URL_MISSING": "未配置 Webhook URL",
    "webhook.message.WEBHOOK_TEST_SUCCESS": "测试消息已发送",
    "webhook.message.WEBHOOK_TEST_ERROR": "测试消息发送失败：{error}",
    "trade.actionSummary": "{action} {shares} @ {price} | {time}",
    "trade.detailUnavailable": "Trade detail unavailable.",
    "trade.loadDetail": "加载 trade 详情: {id}",
    "trade.loadDetailError": "Trade 详情加载失败: {error}",
    "trade.expireStart": "手动过期 trade: {id}",
    "trade.expireDone": "Trade 已过期: {id}",
    "trade.expireError": "Trade 过期失败: {error}",
    "trade.detailFields.id": "交易 ID",
    "trade.detailFields.status": "状态",
    "trade.detailFields.action": "动作",
    "trade.detailFields.reason": "原因",
    "trade.detailFields.positionShares": "当前持仓",
    "trade.detailFields.eventCount": "事件数量",
    "trade.detailFields.outboundCount": "推送数量",
    "log.status.info": "信息",
    "log.status.success": "成功",
    "log.status.error": "异常",
    "log.dashboardLoaded": "Dashboard JS 已加载",
    "log.requestStart": "开始请求 /api/dashboard",
    "log.requestSkip": "已有刷新进行中，本次请求跳过",
    "log.responseReceived": "收到响应 {status}",
    "log.renderStart": "开始渲染 dashboard",
    "log.refreshDone": "刷新完成: {status}",
    "log.recoveryStart": "执行恢复扫描",
    "log.recoveryDone": "恢复扫描完成，自动过期 {count} 条",
    "log.recoveryError": "恢复扫描失败: {error}",
    "log.webhookLoading": "加载 Webhook 配置",
    "log.webhookLoaded": "Webhook 配置已回填",
    "log.webhookLoadError": "Webhook 配置加载失败: {error}",
    "log.webhookSaving": "保存 Webhook 配置",
    "log.webhookSaved": "Webhook 配置已保存",
    "log.webhookSaveError": "Webhook 保存失败: {error}",
    "log.webhookBlockedSave": "Webhook 配置尚未加载完成，已阻止覆盖保存",
    "log.webhookBlockedTest": "Webhook 配置尚未加载完成，暂不发送测试消息",
    "log.webhookTestStart": "发送测试 Webhook 消息",
    "log.webhookTestError": "测试消息发送失败: {error}",
    "log.opsAutoExpired": "恢复扫描自动过期 {count} 条 proposal",
  },
  "en-US": {
    "page.title": "MSTU Monitoring Dashboard",
    "language.label": "Page language",
    "hero.eyebrow": "MSTU Trading Monitor",
    "hero.title": "Live Signal",
    "hero.copy": "MSTR -> Signal, MSTU -> Execution",
    "buttons.refresh": "Refresh Now",
    "buttons.saveConfig": "Save Config",
    "buttons.sendTest": "Send Test Message",
    "buttons.runRecovery": "Run Recovery Scan",
    "summary.decision": "Current Decision",
    "summary.phase": "Market Phase",
    "summary.freshness": "Data Freshness",
    "summary.ops": "Pending Ops",
    "panels.signalChain": "Signal Chain",
    "panels.strategyAction": "Strategy Action",
    "panels.positionState": "Position State",
    "panels.technicalTone": "Technical Signals & T-Tone",
    "panels.keyLevels": "Key Levels",
    "panels.backtestOverview": "Backtest Overview",
    "panels.webhookPush": "Webhook Push",
    "panels.agentOps": "Agent Ops",
    "panels.refreshFlow": "Refresh Flow",
    "feeds.mstr": "MSTR Signal Feed",
    "feeds.mstu": "MSTU Execution Feed",
    "feeds.chainCopy": "MSTR -> Signal -> MSTU",
    "labels.tradingDate": "Trading Date",
    "labels.marketPhase": "Market Phase",
    "labels.decisionStatus": "Decision Status",
    "labels.tModelBreakdown": "T Model Breakdown",
    "labels.activityLog": "Activity Log",
    "webhook.config": "Push Config",
    "webhook.status": "Push Status",
    "webhook.url": "Feishu Webhook URL",
    "webhook.mode": "Push Mode",
    "webhook.modeTradeOnly": "Only BUY/SELL",
    "webhook.modeAll": "All statuses",
    "webhook.enable": "Enable Push",
    "webhook.lastPushTime": "Last Push Time",
    "webhook.lastSignal": "Last Pushed Signal",
    "webhook.placeholder": "https://open.feishu.cn/open-apis/bot/v2/hook/...",
    "ops.actionRequiredTrades": "Action Required Trades",
    "ops.tradeDetail": "Trade Detail",
    "ops.tradeDetailEmpty": "Select a pending trade to inspect its full context.",
    "ops.pendingNone": "No pending trades right now.",
    "ops.viewDetail": "View Detail",
    "ops.markExpired": "Mark Expired",
    "ops.summary": "Action required {count} | Events {events} | Outbound {outbound} | Auto expired {expired}",
    "ops.summaryHintPending": "Open Agent Ops to inspect pending trades",
    "ops.summaryHintClear": "No manual trade action required",
    "ops.countPending": "{count} pending",
    "ops.countClear": "Clear",
    "ops.latestEvents": "Latest Events",
    "technical.empty": "No technical signals are available right now.",
    "technical.unavailable": "Technical signals could not be rendered. Refresh or check the service.",
    "technical.group.structure": "Structure & Trend",
    "technical.group.indicator": "Momentum & Indicators",
    "technical.group.risk": "Position & Risk",
    "technical.group.other": "Additional Notes",
    "technical.title": "Technical Signals",
    "tone.kicker": "Combined MSTR + BTC View",
    "tone.neutral": "Neutral Rhythm",
    "tone.bullish": "Forward-T Bias",
    "tone.bullish_strong": "Strong Forward-T Bias",
    "tone.bearish": "Reverse-T Bias",
    "tone.bearish_strong": "Strong Reverse-T Bias",
    "tone.waiting": "Waiting for tone analysis...",
    "tone.noDirection": "No clear MSTR + BTC resonance yet.",
    "tone.bias": "Forward-T threshold {forward} / Reverse-T threshold {reverse}",
    "tone.meta": "Current action tilt: {action}. This rhythm shifts the intraday balance between forward-T and reverse-T.",
    "tone.errorSummary": "The T-tone is unavailable. Check market data and strategy services.",
    "tone.errorBias": "Forward-T / Reverse-T thresholds: --",
    "tone.errorMeta": "When tone data is missing, verify the MSTR and BTC market-data chain first.",
    "status.idle": "Idle",
    "status.loadingManual": "Refreshing",
    "status.loadingAuto": "Auto Refresh",
    "status.live": "Live",
    "status.stale": "Stale",
    "status.offline": "Offline",
    "status.skipped": "Skipped",
    "status.success": "Success",
    "status.waitingSnapshot": "Waiting for snapshot...",
    "status.loadingSignalSource": "Loading signal source...",
    "status.loadingExecutionQuote": "Loading execution quote...",
    "status.trendPlaceholder": "Trend: --",
    "status.sessionPlaceholder": "Session: --",
    "freshness.initial": "Waiting for first refresh",
    "freshness.live": "Fresh ({age}s)",
    "freshness.aging": "Aging ({age}s)",
    "freshness.stale": "Stale ({age}s)",
    "freshness.lastSuccess": "Last success: {time}",
    "freshness.lastSuccessEmpty": "Last success: --",
    "banner.stale": "Data is stale. Check the network or backend services.",
    "banner.renderError": "Frontend render failure",
    "banner.snapshotUnavailable": "Dashboard snapshot unavailable",
    "announce.refreshManual": "Refreshing dashboard manually",
    "announce.refreshAuto": "Refreshing dashboard automatically",
    "announce.refreshDone": "Dashboard refresh completed",
    "announce.refreshError": "Dashboard refresh failed",
    "market.PREMARKET": "Premarket",
    "market.REGULAR": "Regular",
    "market.OVERNIGHT": "Overnight",
    "market.CLOSED": "Closed",
    "market.OFFLINE": "Offline",
    "market.UNKNOWN": "Unknown",
    "session.regular": "regular",
    "session.premarket": "premarket",
    "session.overnight": "overnight",
    "session.closed": "closed",
    "session.unknown": "unknown",
    "decision.BUY": "Buy",
    "decision.SELL": "Sell",
    "decision.HOLD": "Hold",
    "decision.WATCH": "Watch",
    "decision.BLOCKED": "Blocked",
    "decision.SETUP": "Setup",
    "decision.ERROR": "Error",
    "decision.OFFLINE": "Offline",
    "decision.PREMARKET": "Premarket Watch",
    "meta.change": "Change",
    "meta.high": "High",
    "meta.low": "Low",
    "meta.ema": "EMA",
    "meta.macd": "MACD",
    "meta.bullish": "bullish",
    "meta.mixed": "mixed",
    "meta.confirmed": "confirmed",
    "meta.watch": "watch",
    "meta.session": "Session",
    "summary.noSignalReason": "No signal reason",
    "strategy.buy": "Entry conditions are met. Forward-T execution can be considered.",
    "strategy.sell": "The rhythm favors trimming or taking profit. Re-check take-profit, stop-loss, and position release.",
    "strategy.timeBlocked": "The time window is blocked. Even if the signal holds, no new position should be opened.",
    "strategy.premarket": "Still in a premarket observation state. Wait for confirmation during regular trading hours.",
    "strategy.hold": "No higher-quality intraday action is available yet. Keep watching.",
    "error.signalList": "Refresh the page or restart web_app.py",
    "error.signalSourceUnavailable": "Signal source unavailable",
    "error.executionUnavailable": "Execution quote unavailable",
    "error.webhookUnavailable": "Webhook unavailable",
    "error.summaryOps": "Check system",
    "error.summaryOpsHint": "Refresh the page or inspect the service",
    "error.errorTitle": "Error",
    "position.holdingShares": "Holding Shares",
    "position.buyPrice": "Buy Price",
    "position.target": "Target",
    "position.stop": "Stop",
    "position.cash": "Cash",
    "position.source": "Source",
    "keyLevels.s1": "S1 Support",
    "keyLevels.s2": "S2 Support",
    "keyLevels.pivot": "Pivot",
    "keyLevels.r1": "R1 Resistance",
    "keyLevels.r2": "R2 Resistance",
    "keyLevels.executionApprox": "{symbol} approx",
    "keyLevels.currentZone": "Current Zone",
    "keyLevels.currentZoneNote": "Signal uses {signal}; execution lands on {execution}",
    "keyLevels.nearestSupport": "Nearest Support",
    "keyLevels.nearestResistance": "Nearest Resistance",
    "keyLevels.currentHit": "Current Hit",
    "keyLevels.continueWatch": "Keep watching",
    "keyLevels.level.S1": "S1 Support",
    "keyLevels.level.S2": "S2 Support",
    "keyLevels.level.S3": "S3 Support",
    "keyLevels.level.R1": "R1 Resistance",
    "keyLevels.level.R2": "R2 Resistance",
    "keyLevels.level.R3": "R3 Resistance",
    "tone.reason.NO_CLEAR_DIRECTION": "No clear directional signal",
    "tone.reason.BTC_BULLISH": "BTC is up {change_pct}% with a bullish structure",
    "tone.reason.BTC_BEARISH": "BTC is down {change_pct}% with a bearish structure",
    "tone.reason.MSTR_GAP_UP": "MSTR gapped up {change_pct}%",
    "tone.reason.MSTR_GAP_DOWN": "MSTR gapped down {change_pct}%",
    "tone.reason.MSTR_BTC_RESONANCE_BULLISH": "MSTR and BTC moving-average resonance is bullish",
    "tone.reason.MSTR_BTC_RESONANCE_BEARISH": "MSTR and BTC moving-average resonance is bearish",
    "backtest.status": "Status",
    "backtest.winRate": "Win Rate",
    "backtest.return": "Return",
    "backtest.finalValue": "Final Value",
    "backtest.closedTrades": "Closed Trades",
    "backtest.recommendedGapUp": "Recommended Gap Up",
    "trace.daemonStatus": "Daemon Status",
    "trace.lastHeartbeat": "Last heartbeat: {value}",
    "trace.lastCycle": "Last cycle: {value}",
    "trace.step.webhook": "webhook",
    "trace.step.position": "position",
    "trace.step.backtest": "backtest",
    "trace.step.ops": "ops",
    "trace.step.daemon": "daemon",
    "trace.step.quote": "quote",
    "trace.step.signal": "signal",
    "trace.step.snapshot": "snapshot",
    "trace.status.running": "running",
    "trace.status.success": "success",
    "trace.status.error": "error",
    "trace.status.offline": "offline",
    "trace.status.stale": "stale",
    "trace.status.idle": "idle",
    "trace.detail.WEBHOOK_CONFIG_LOADING": "Loading webhook config",
    "trace.detail.WEBHOOK_CONFIG_LOADED": "Webhook config loaded",
    "trace.detail.POSITION_LOADING": "Loading position state",
    "trace.detail.POSITION_LOADED": "Position state loaded",
    "trace.detail.BACKTEST_LOADING": "Loading backtest summary",
    "trace.detail.BACKTEST_LOADED": "Backtest summary loaded",
    "trace.detail.OPS_LOADING": "Loading agent ops view",
    "trace.detail.OPS_LOADED": "Agent ops view loaded",
    "trace.detail.DAEMON_LOADING": "Loading webhook daemon heartbeat",
    "trace.detail.DAEMON_STATUS": "daemon status: {status}",
    "trace.detail.QUOTE_LOADING": "Fetching MSTU/MSTR quotes",
    "trace.detail.QUOTE_LOADED": "Quotes fetched",
    "trace.detail.QUOTE_ERROR": "Quote fetch failed: {error}",
    "trace.detail.SIGNAL_ANALYZING": "Running strategy analysis",
    "trace.detail.SIGNAL_ACTION": "Strategy action: {action}",
    "trace.detail.SNAPSHOT_DONE": "Snapshot completed",
    "trace.detail.WEBHOOK_DEDUPED": "Webhook deduped; no duplicate push sent",
    "trace.detail.WEBHOOK_PUSHING": "Pushing Feishu webhook",
    "trace.detail.WEBHOOK_PUSH_SUCCESS": "Webhook push succeeded",
    "trace.detail.WEBHOOK_PUSH_ERROR": "Webhook push failed: {error}",
    "system.line": "Signal: {signal} | Execution: {execution}",
    "system.lastUpdated": "Last updated: {time}",
    "webhook.statusLine": "Status: {status} | {message}",
    "webhook.message.WEBHOOK_SKIPPED_BY_MODE": "No push under the current mode",
    "webhook.message.WEBHOOK_DEDUPED": "This signal was already pushed and has been deduplicated",
    "webhook.message.WEBHOOK_PUSH_SUCCESS": "Push succeeded",
    "webhook.message.WEBHOOK_PUSH_ERROR": "Push failed: {error}",
    "webhook.message.WEBHOOK_URL_MISSING": "Webhook URL is not configured",
    "webhook.message.WEBHOOK_TEST_SUCCESS": "Test message sent",
    "webhook.message.WEBHOOK_TEST_ERROR": "Test message failed: {error}",
    "trade.actionSummary": "{action} {shares} @ {price} | {time}",
    "trade.detailUnavailable": "Trade detail unavailable.",
    "trade.loadDetail": "Loading trade detail: {id}",
    "trade.loadDetailError": "Failed to load trade detail: {error}",
    "trade.expireStart": "Expiring trade manually: {id}",
    "trade.expireDone": "Trade expired: {id}",
    "trade.expireError": "Failed to expire trade: {error}",
    "trade.detailFields.id": "Trade ID",
    "trade.detailFields.status": "Status",
    "trade.detailFields.action": "Action",
    "trade.detailFields.reason": "Reason",
    "trade.detailFields.positionShares": "Position Shares",
    "trade.detailFields.eventCount": "Event Count",
    "trade.detailFields.outboundCount": "Outbound Count",
    "log.status.info": "info",
    "log.status.success": "success",
    "log.status.error": "error",
    "log.dashboardLoaded": "Dashboard JS loaded",
    "log.requestStart": "Requesting /api/dashboard",
    "log.requestSkip": "A refresh is already in flight, skipping this request",
    "log.responseReceived": "Received response {status}",
    "log.renderStart": "Rendering dashboard",
    "log.refreshDone": "Refresh complete: {status}",
    "log.recoveryStart": "Running recovery scan",
    "log.recoveryDone": "Recovery scan complete, auto-expired {count}",
    "log.recoveryError": "Recovery scan failed: {error}",
    "log.webhookLoading": "Loading webhook config",
    "log.webhookLoaded": "Webhook config restored",
    "log.webhookLoadError": "Failed to load webhook config: {error}",
    "log.webhookSaving": "Saving webhook config",
    "log.webhookSaved": "Webhook config saved",
    "log.webhookSaveError": "Failed to save webhook config: {error}",
    "log.webhookBlockedSave": "Webhook config has not loaded yet; save is blocked",
    "log.webhookBlockedTest": "Webhook config has not loaded yet; test message is blocked",
    "log.webhookTestStart": "Sending test webhook message",
    "log.webhookTestError": "Failed to send test webhook message: {error}",
    "log.opsAutoExpired": "Recovery scan auto-expired {count} proposals",
  },
};

function interpolate(template, params = {}) {
  return String(template).replace(/\{(\w+)\}/g, (_, key) => String(params[key] ?? `{${key}}`));
}

function t(key, params = {}) {
  const dict = I18N[uiState.locale] || I18N["zh-CN"];
  const fallback = I18N["zh-CN"];
  const template = dict[key] ?? fallback[key] ?? key;
  return interpolate(template, params);
}

function detectPreferredLocale() {
  const saved = window.localStorage.getItem("dashboard.locale");
  if (saved && I18N[saved]) {
    return saved;
  }
  const browser = String(navigator.language || "").toLowerCase();
  if (browser.startsWith("en")) {
    return "en-US";
  }
  return "zh-CN";
}

function setLocale(locale) {
  uiState.locale = I18N[locale] ? locale : "zh-CN";
  document.documentElement.lang = uiState.locale;
  document.title = t("page.title");
  if (refs.languageSwitcher) {
    refs.languageSwitcher.value = uiState.locale;
    refs.languageSwitcher.setAttribute("aria-label", t("language.label"));
  }
  window.localStorage.setItem("dashboard.locale", uiState.locale);
  applyStaticTranslations();
}

function applyStaticTranslations() {
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    const key = node.getAttribute("data-i18n");
    node.textContent = t(key);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((node) => {
    const key = node.getAttribute("data-i18n-placeholder");
    node.setAttribute("placeholder", t(key));
  });
}

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

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
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
  if (uiState.locale === "en-US") {
    return date.toLocaleString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
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
  const timeLabel = now.toLocaleTimeString(uiState.locale === "en-US" ? "en-US" : "zh-CN", {
    hour12: false,
  });
  const value = String(dateLabel || "--");
  if (uiState.locale === "en-US") {
    const match = value.match(/(\d{4})年(\d{1,2})月(\d{1,2})日\((周.)\)/);
    if (match) {
      const weekdayMap = {
        周一: "Mon",
        周二: "Tue",
        周三: "Wed",
        周四: "Thu",
        周五: "Fri",
        周六: "Sat",
        周日: "Sun",
      };
      return `${match[1]}-${String(match[2]).padStart(2, "0")}-${String(match[3]).padStart(2, "0")} (${weekdayMap[match[4]] || match[4]}) ${timeLabel}`;
    }
  }
  return `${value} ${timeLabel}`;
}

function localizeSignalText(text) {
  const raw = String(text ?? "");
  if (!raw || uiState.locale === "zh-CN") {
    return raw;
  }
  const replacements = [
    [/未发生推送/g, "no push yet"],
    [/推送成功/g, "push succeeded"],
    [/当前模式下不触发推送/g, "not pushed under current mode"],
    [/同一信号已推送，已去重/g, "duplicate signal suppressed"],
    [/读取 Webhook 配置/g, "load webhook config"],
    [/Webhook 配置已加载/g, "webhook config loaded"],
    [/读取持仓状态/g, "load position state"],
    [/持仓状态已加载/g, "position state loaded"],
    [/读取回测摘要/g, "load backtest summary"],
    [/回测摘要已加载/g, "backtest summary loaded"],
    [/读取 Agent 运维视图/g, "load agent ops view"],
    [/Agent 运维视图已加载/g, "agent ops view loaded"],
    [/读取 webhook daemon 心跳/g, "load webhook daemon heartbeat"],
    [/获取 MSTU\/MSTR 行情/g, "fetch MSTU/MSTR quotes"],
    [/行情获取完成/g, "quotes fetched"],
    [/执行策略分析/g, "run strategy analysis"],
    [/策略动作:/g, "strategy action:"],
    [/本次刷新完成/g, "snapshot completed"],
    [/行情获取失败:/g, "quote fetch failed:"],
    [/daemon 状态:/g, "daemon status:"],
    [/Webhook 推送成功/g, "webhook pushed successfully"],
    [/Webhook 推送失败:/g, "webhook push failed:"],
    [/Webhook 去重，未重复推送/g, "webhook deduped, not sent again"],
    [/推送飞书 Webhook/g, "push Feishu webhook"],
    [/当前没有待处理交易。/g, "No pending trades right now."],
    [/当前无法渲染技术信号，请刷新页面或检查服务。/g, "Technical signals are unavailable. Refresh or inspect the service."],
    [/当前暂无可展示的技术信号。/g, "No technical signals are available right now."],
    [/MSTR强结构/g, "MSTR strong structure"],
    [/MSTR弱结构/g, "MSTR weak structure"],
    [/MSTR结构偏弱/g, "MSTR structure is weak"],
    [/牛熊线持续走强且双线抬升/g, "bull/bear lines keep rising with both lines trending up"],
    [/短线底轨站上长线底轨，价格站上长期牛线/g, "short-term base is above the long-term base and price is above the long bull line"],
    [/牛熊线未完成有效上移/g, "bull/bear lines have not completed a valid upward shift"],
    [/VWAP上穿/g, "VWAP cross-up"],
    [/VWAP上方延续启动/g, "VWAP continuation above"],
    [/跌回VWAP下方/g, "fell back below VWAP"],
    [/RSI底部反弹/g, "RSI bottom rebound"],
    [/KDJ变盘转多/g, "KDJ turning bullish"],
    [/MACD增强/g, "MACD enhancement"],
    [/MACD底背离/g, "MACD bullish divergence"],
    [/MACD顶背离/g, "MACD bearish divergence"],
    [/绿柱缩短\(空头衰竭\)/g, "green histogram shrinking (bear exhaustion)"],
    [/红柱缩短\(多头衰竭\)/g, "red histogram shrinking (bull exhaustion)"],
    [/MACD绿转红\(金叉\)/g, "MACD green to red (golden cross)"],
    [/MACD红转绿\(死叉\)/g, "MACD red to green (death cross)"],
    [/零轴上方金叉/g, "golden cross above zero"],
    [/零轴下方金叉/g, "golden cross below zero"],
    [/零轴上方死叉/g, "death cross above zero"],
    [/零轴下方死叉/g, "death cross below zero"],
    [/上升趋势/g, "uptrend"],
    [/下跌趋势/g, "downtrend"],
    [/放量上涨，强势信号/g, "volume expansion on rise, strong signal"],
    [/放量下跌，注意风险/g, "volume expansion on drop, watch risk"],
    [/缩量下跌，可能见底/g, "shrinking volume on drop, possible bottom"],
    [/缩量上涨，动能不足/g, "shrinking volume on rise, weak momentum"],
    [/日内低点区/g, "intraday low zone"],
    [/偏低位置/g, "relatively low zone"],
    [/日内高点区/g, "intraday high zone"],
    [/偏高位置/g, "relatively high zone"],
    [/中性位置/g, "neutral zone"],
    [/接近日内支撑/g, "near intraday support"],
    [/信号参考/g, "signal from"],
    [/执行标的/g, "execution symbol"],
    [/隔夜持仓浮盈/g, "overnight position PnL"],
    [/优先平仓/g, "prefer closing first"],
    [/等反弹出/g, "wait for rebound to exit"],
    [/收盘前/g, "before close "],
    [/分钟禁止新开仓/g, " minutes before close: no new position"],
    [/继续观察/g, "keep watching"],
    [/可用资金不足/g, "insufficient cash"],
    [/已有持仓/g, "already holding position"],
    [/无明确信号/g, "no clear signal"],
    [/盘前观察/g, "premarket watch"],
    [/偏强区间/g, "bullish zone"],
    [/偏弱区间/g, "bearish zone"],
    [/强势区间/g, "strong bullish zone"],
    [/弱势区间/g, "strong bearish zone"],
    [/中性区间/g, "neutral zone"],
    [/第一支撑/g, "S1 Support"],
    [/第二支撑/g, "S2 Support"],
    [/第三支撑/g, "S3 Support"],
    [/第一压力/g, "R1 Resistance"],
    [/第二压力/g, "R2 Resistance"],
    [/第三压力/g, "R3 Resistance"],
    [/买入/g, "Buy"],
    [/卖出/g, "Sell"],
    [/持有/g, "Hold"],
    [/观察/g, "Watch"],
  ];
  let output = raw;
  replacements.forEach(([pattern, replacement]) => {
    output = output.replace(pattern, replacement);
  });
  return output;
}

function localizeBacktestText(text) {
  const raw = String(text ?? "");
  if (!raw || uiState.locale === "zh-CN") {
    return raw
      .replace("Base Position", "底仓")
      .replace("Forward T", "正向做T")
      .replace("Reverse T", "反向做T")
      .replace("Cross-session T", "跨日做T")
      .replace("Low buy / high sell", "低买高卖")
      .replace("Trim then buy back", "先卖后买回")
      .replace("Enabled", "已启用");
  }
  return raw
    .replace("Base Position", "Base Position")
    .replace("Forward T", "Forward T")
    .replace("Reverse T", "Reverse T")
    .replace("Cross-session T", "Cross-session T")
    .replace("长期底仓，只做背景仓位", "Core long-only base position")
    .replace("低买高卖的正向做T", "Forward T: buy lower and sell higher")
    .replace("高抛已有底仓，再低位买回", "Reverse T: trim first, then buy back lower")
    .replace("允许T仓跨交易日持有", "Allow T positions to carry across trading days")
    .replace("偏强区间", "bullish zone")
    .replace("偏弱区间", "bearish zone")
    .replace("强势区间", "strong bullish zone")
    .replace("弱势区间", "strong bearish zone")
    .replace("中性区间", "neutral zone")
    .replace("第一支撑", "S1 Support")
    .replace("第二支撑", "S2 Support")
    .replace("第三支撑", "S3 Support")
    .replace("第一压力", "R1 Resistance")
    .replace("第二压力", "R2 Resistance")
    .replace("第三压力", "R3 Resistance");
}

function localizeTraceStep(step) {
  return t(`trace.step.${String(step || "").toLowerCase()}`) || String(step || "--");
}

function localizeTraceStatus(status) {
  return t(`trace.status.${String(status || "").toLowerCase()}`) || String(status || "--");
}

function localizeLogStatus(status) {
  return t(`log.status.${String(status || "").toLowerCase()}`) || String(status || "--");
}

function translateSessionLabel(value) {
  return t(`session.${String(value || "unknown").toLowerCase()}`) || String(value || "unknown");
}

function translateKeyLevelLabel(levelKey, fallback = "--") {
  return levelKey ? t(`keyLevels.level.${levelKey}`) : fallback;
}

function renderToneReason(signal) {
  const parts = Array.isArray(signal?.tone_reason_parts) ? signal.tone_reason_parts : [];
  if (parts.length) {
    return parts
      .map((part) => t(`tone.reason.${part.code}`, part.params || {}))
      .join(" | ");
  }
  return localizeSignalText(signal?.tone_reason || t("tone.noDirection"));
}

function renderTraceDetail(item) {
  if (item?.detail_code) {
    return t(`trace.detail.${item.detail_code}`, item.detail_params || {});
  }
  return localizeSignalText(item?.detail || "");
}

function renderWebhookMessage(data) {
  if (data?.last_push_message_code) {
    return t(`webhook.message.${data.last_push_message_code}`, data.last_push_message_params || {});
  }
  return localizeSignalText(data?.last_push_message || "未发生推送");
}

function metricRow(label, value) {
  return `<div class="metric-row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
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

function dedupeSignalDetails(signal) {
  const reason = String(signal?.reason || "").trim();
  const signalLines = Array.isArray(signal?.signals)
    ? signal.signals.map((item) => String(item).trim()).filter(Boolean)
    : [];
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
  const normalized = String(value || "").toUpperCase();
  return t(`market.${normalized}`) || String(value || "--");
}

function translateDecisionStatus(value) {
  const normalized = String(value || "").toUpperCase();
  return t(`decision.${normalized}`) || String(value || "--");
}

function translateToneDirection(value) {
  return t(`tone.${String(value || "neutral").toLowerCase()}`);
}

function toneClassName(value) {
  const normalized = String(value || "neutral").toLowerCase();
  return `tone-direction tone-direction-${normalized}`;
}

function buildToneBiasLabel(signal) {
  const forwardBias = Number(signal?.tone_forward_bias ?? 0);
  const reverseBias = Number(signal?.tone_reverse_bias ?? 0);
  return t("tone.bias", {
    forward: `${forwardBias >= 0 ? "+" : ""}${forwardBias.toFixed(2)}`,
    reverse: `${reverseBias >= 0 ? "+" : ""}${reverseBias.toFixed(2)}`,
  });
}

function classifySignalLine(line) {
  const value = String(line || "");
  if (!value) return "other";
  if (value.includes("MSTR强结构") || value.includes("MSTR弱结构") || value.includes("趋势未确认") || value.includes("上升趋势") || value.includes("下跌趋势") || value.includes("MSTR涨") || value.includes("MSTR跌")) {
    return "structure";
  }
  if (value.includes("VWAP") || value.includes("MACD") || value.includes("EMA") || value.includes("RSI") || value.includes("KDJ") || value.includes("放量") || value.includes("缩量")) {
    return "indicator";
  }
  if (value.includes("支撑") || value.includes("阻力") || value.includes("低点区") || value.includes("高点区") || value.includes("中性位置") || value.includes("隔夜持仓") || value.includes("禁止") || value.includes("谨慎买入") || value.includes("执行标的")) {
    return "risk";
  }
  return "other";
}

function buildTechnicalSignalGroups(signal) {
  const lines = Array.isArray(signal?.signals)
    ? signal.signals.map((item) => String(item).trim()).filter(Boolean)
    : [];
  const groups = {
    structure: [],
    indicator: [],
    risk: [],
    other: [],
  };
  lines.forEach((line) => {
    groups[classifySignalLine(line)].push(line);
  });
  return [
    { key: "structure", title: t("technical.group.structure"), items: groups.structure },
    { key: "indicator", title: t("technical.group.indicator"), items: groups.indicator },
    { key: "risk", title: t("technical.group.risk"), items: groups.risk },
    { key: "other", title: t("technical.group.other"), items: groups.other },
  ].filter((group) => group.items.length);
}

function renderTechnicalSignals(signal) {
  const groups = buildTechnicalSignalGroups(signal);
  if (!groups.length) {
    safeSetHtml(
      refs.technicalSignals,
      `<article class="technical-group"><div class="technical-group-title">${escapeHtml(t("technical.title"))}</div><div class="technical-empty">${escapeHtml(t("technical.empty"))}</div></article>`
    );
    return;
  }
  safeSetHtml(
    refs.technicalSignals,
    groups
      .map(
        (group) => `
          <article class="technical-group">
            <div class="technical-group-title">${escapeHtml(group.title)}</div>
            <div class="technical-chip-list">
              ${group.items
                .slice(0, 6)
                .map((item) => `<span class="technical-chip">${escapeHtml(localizeSignalText(item))}</span>`)
                .join("")}
            </div>
          </article>
        `
      )
      .join("")
  );
}

function renderTone(signal) {
  const tone = String(signal?.daily_tone || "neutral").toLowerCase();
  if (refs.toneDirection) {
    refs.toneDirection.className = toneClassName(tone);
  }
  safeSetText(refs.toneDirection, translateToneDirection(tone));
  safeSetText(refs.toneSummary, renderToneReason(signal));
  safeSetText(refs.toneBias, buildToneBiasLabel(signal));
  const action = translateDecisionStatus(signal?.action || "HOLD");
  safeSetText(refs.toneMeta, t("tone.meta", { action }));
}

function summarizeStrategyAction(signal, ui) {
  const decision = String(ui?.decision_status || signal?.action || "").toUpperCase();
  if (signal?.blocked_reason) {
    return signal.blocked_reason;
  }
  if (decision === "BUY") {
    return t("strategy.buy");
  }
  if (decision === "SELL") {
    return t("strategy.sell");
  }
  if (decision === "TIME_WINDOW_BLOCKED") {
    return t("strategy.timeBlocked");
  }
  if (decision === "PREMARKET") {
    return t("strategy.premarket");
  }
  return localizeSignalText(signal?.tone_reason || t("strategy.hold"));
}

function summarizeStrategySecondary(signal) {
  const signals = Array.isArray(signal?.signals)
    ? signal.signals.map((item) => String(item).trim()).filter(Boolean)
    : [];
  return signals.slice(0, 3).map(localizeSignalText).join(" · ");
}

function pushLog(status, detail) {
  uiState.activityLog.unshift({
    time: new Date().toLocaleTimeString(),
    status,
    detail,
  });
  uiState.activityLog.splice(20);
  renderActivityLog();
}

function renderActivityLog() {
  safeSetHtml(
    refs.activityLog,
    uiState.activityLog
      .map(
        (item) => `
          <div class="log-row">
            <span class="log-time">${escapeHtml(item.time)}</span>
            <span class="log-status">${escapeHtml(localizeLogStatus(item.status))}</span>
            <span class="log-detail">${escapeHtml(renderTraceDetail(item))}</span>
          </div>
        `
      )
      .join("")
  );
}

function setRefreshBadge(tone, label) {
  if (!refs.refreshStatusBadge) {
    return;
  }
  refs.refreshStatusBadge.className = `status-badge status-badge-${tone}`;
  refs.refreshStatusBadge.textContent = label;
}

function announceRefresh(message) {
  safeSetText(refs.refreshAnnouncer, message);
}

function setErrorBanner(message = "", tone = "neutral") {
  if (!refs.dashboardErrorBanner) {
    return;
  }
  refs.dashboardErrorBanner.className = message ? `banner banner-${tone}` : "banner banner-hidden";
  refs.dashboardErrorBanner.textContent = message;
}

function computeFreshnessLabel() {
  if (!uiState.lastSuccessAt) {
    return t("freshness.initial");
  }
  const ageMs = Date.now() - new Date(uiState.lastSuccessAt).getTime();
  const ageSec = Math.max(0, Math.floor(ageMs / 1000));
  if (ageSec < 45) {
    return t("freshness.live", { age: ageSec });
  }
  if (ageSec < 120) {
    return t("freshness.aging", { age: ageSec });
  }
  return t("freshness.stale", { age: ageSec });
}

function renderFreshness() {
  const freshness = computeFreshnessLabel();
  safeSetText(refs.summaryFreshness, freshness);
  safeSetText(
    refs.summaryLastSuccess,
    uiState.lastSuccessAt ? t("freshness.lastSuccess", { time: formatDisplayTime(uiState.lastSuccessAt) }) : t("freshness.lastSuccessEmpty")
  );
  if (freshness.startsWith(t("freshness.stale", { age: "" }).split(" ")[0]) && !uiState.refreshInFlight) {
    setRefreshBadge("warning", t("status.stale"));
    setErrorBanner(t("banner.stale"), "warning");
  }
}

function setDecisionTone(decision) {
  if (!refs.summaryDecision) {
    return;
  }
  const normalized = String(decision || "neutral").toLowerCase();
  refs.summaryDecision.className = `summary-value summary-value-${normalized}`;
}

function renderTrace(trace) {
  if (!Array.isArray(trace)) {
    safeSetHtml(refs.refreshFlow, "");
    return;
  }
  const cards = trace.map(
    (item) => `
      <article class="trace-card ${escapeHtml(item.status)}">
        <strong>${escapeHtml(localizeTraceStep(item.step))}</strong>
        <span>${escapeHtml(localizeTraceStatus(item.status))}</span>
        <small>${escapeHtml(renderTraceDetail(item))}</small>
      </article>
    `
  );
  cards.push(`
      <article class="trace-card ${escapeHtml(String(window.__lastDaemonStatus || "offline").toLowerCase())}">
      <strong>${escapeHtml(t("trace.daemonStatus"))}</strong>
      <span>${escapeHtml(localizeTraceStatus(String(window.__lastDaemonStatus || "offline")))}</span>
      <small>${escapeHtml(t("trace.lastHeartbeat", { value: window.__lastDaemonHeartbeat || "--" }))}</small>
      <small>${escapeHtml(t("trace.lastCycle", { value: window.__lastDaemonCycle || "--" }))}</small>
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
    t("webhook.statusLine", {
      status: localizeTraceStatus(data.last_push_status || "idle"),
      message: renderWebhookMessage(data),
    })
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
  return t("trade.actionSummary", { action, shares, price, time: createdAt });
}

function renderTradeDetail(payload) {
  if (!payload || !payload.proposal) {
    safeSetHtml(refs.tradeDetail, t("ops.tradeDetailEmpty"));
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
        ${metricRow(t("trade.detailFields.id"), proposal.trade_id || "--")}
        ${metricRow(t("trade.detailFields.status"), proposal.status || "--")}
        ${metricRow(t("trade.detailFields.action"), proposal.action || "--")}
        ${metricRow(t("trade.detailFields.reason"), localizeSignalText(proposal.reason || "--"))}
        ${metricRow(t("trade.detailFields.positionShares"), position.holding_shares ?? "--")}
        ${metricRow(t("trade.detailFields.eventCount"), events.length)}
        ${metricRow(t("trade.detailFields.outboundCount"), outbound.length)}
        <div class="status-caption">${escapeHtml(t("ops.latestEvents"))}</div>
        <pre class="ops-detail-pre">${escapeHtml(JSON.stringify(events.slice(0, 5), null, 2))}</pre>
      </div>
    `
  );
}

async function loadTradeDetail(tradeId) {
  if (!tradeId) {
    renderTradeDetail(null);
    return;
  }
  uiState.selectedTradeId = tradeId;
  pushLog("info", t("trade.loadDetail", { id: tradeId }));
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
    pushLog("error", t("trade.loadDetailError", { error: error?.message || "" }));
    safeSetHtml(refs.tradeDetail, t("trade.detailUnavailable"));
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
  const pendingCount = stats.action_required_trade_count ?? stats.pending_trade_count ?? 0;

  safeSetText(
    refs.opsSummary,
    t("ops.summary", {
      count: pendingCount,
      events: stats.recent_event_count ?? 0,
      outbound: stats.recent_outbound_count ?? 0,
      expired: stats.recent_auto_expired ?? 0,
    })
  );
  safeSetText(refs.summaryOps, pendingCount > 0 ? t("ops.countPending", { count: pendingCount }) : t("ops.countClear"));
  safeSetText(
    refs.summaryOpsHint,
    pendingCount > 0 ? t("ops.summaryHintPending") : t("ops.summaryHintClear")
  );

  if (!pendingTrades.length) {
    safeSetHtml(refs.pendingTrades, `<div class="ops-empty">${escapeHtml(t("ops.pendingNone"))}</div>`);
    if (!uiState.selectedTradeId) {
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
                <button class="ops-button" type="button" data-action="detail" data-trade-id="${escapeHtml(item.trade_id || "")}">${escapeHtml(t("ops.viewDetail"))}</button>
                <button class="ops-button danger" type="button" data-action="expire" data-trade-id="${escapeHtml(item.trade_id || "")}">${escapeHtml(t("ops.markExpired"))}</button>
              </div>
            </article>
          `
        )
        .join("")
    );
    if (!uiState.selectedTradeId && pendingTrades[0]?.trade_id) {
      loadTradeDetail(pendingTrades[0].trade_id);
    }
  }

  if (!pendingTrades.some((item) => item.trade_id === uiState.selectedTradeId) && uiState.selectedTradeId) {
    renderTradeDetail(null);
    uiState.selectedTradeId = "";
  }

  if ((recovery.expired_count || 0) > 0) {
    pushLog("info", t("log.opsAutoExpired", { count: recovery.expired_count }));
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

  safeSetText(refs.mstrPrice, formatMoney(mstr.price ?? mstr.mstr_price));
  safeSetText(
    refs.mstrMeta,
    `${t("meta.change")} ${mstr.change_pct ?? mstr.mstr_change_pct ?? "--"}% | ${t("meta.ema")} ${(mstr.ema_bullish ?? mstr.mstr_ema_bullish) ? t("meta.bullish") : t("meta.mixed")} | ${t("meta.macd")} ${(mstr.macd_bullish ?? mstr.mstr_macd_bullish) ? t("meta.bullish") : t("meta.mixed")}`
  );
  safeSetText(
    refs.mstrTrend,
    `${t("meta.trend")}: ${(mstr.ema_bullish ?? mstr.mstr_ema_bullish) && (mstr.macd_bullish ?? mstr.mstr_macd_bullish) ? t("meta.confirmed") : t("meta.watch")}`
  );

  safeSetText(refs.mstuPrice, formatMoney(quote.price));
  safeSetText(
    refs.mstuMeta,
    `${t("meta.change")} ${quote.change_pct ?? "--"}% | ${t("meta.high")} ${formatMoney(quote.high)} | ${t("meta.low")} ${formatMoney(quote.low)}`
  );
  safeSetText(refs.mstuSession, `${t("meta.session")}: ${translateSessionLabel(quote.session || "unknown")}`);

  safeSetText(refs.tradingDate, buildTradingDateLabel(ui.date_label || "--"));
  safeSetText(refs.marketPhase, translateMarketPhase(ui.market_phase || "UNKNOWN"));
  safeSetText(refs.signalAction, translateDecisionStatus(ui.decision_status || signal.action || "ERROR"));
  if (refs.signalAction) {
    refs.signalAction.className = `signal-action ${String(ui.decision_status || signal.action || "").toLowerCase()}`;
  }
  safeSetText(refs.signalReason, summarizeStrategyAction(signal, ui));
  safeSetText(refs.signalList, summarizeStrategySecondary(signal));

  safeSetText(refs.summaryDecision, translateDecisionStatus(ui.decision_status || signal.action || "ERROR"));
  safeSetText(refs.summaryReason, localizeSignalText(signalContent.reason || t("summary.noSignalReason")));
  safeSetText(refs.summaryPhase, translateMarketPhase(ui.market_phase || "UNKNOWN"));
  safeSetText(refs.summaryTradingDate, buildTradingDateLabel(ui.date_label || "--"));
  setDecisionTone(ui.decision_status || signal.action || "error");
  renderTone(signal);
  renderTechnicalSignals(signal);

  safeSetHtml(
    refs.positionSummary,
    [
      metricRow(t("position.holdingShares"), position.holding_shares ?? 0),
      metricRow(t("position.buyPrice"), formatMoney(position.buy_price)),
      metricRow(t("position.target"), formatMoney(position.target_price)),
      metricRow(t("position.stop"), formatMoney(position.stop_price)),
      metricRow(t("position.cash"), formatMoney(position.available_cash)),
      metricRow(t("position.source"), position.position_source || "--"),
    ].join("")
  );

  const levelSignals = Array.isArray(keyLevels.active_signals)
    ? keyLevels.active_signals
        .map((item) => `${item.label}${item.distance_pct !== undefined ? ` (${item.distance_pct > 0 ? "+" : ""}${item.distance_pct}%)` : ""}`)
        .join(" | ")
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
            ${levelChip(t("keyLevels.s1"), formatMoney(keyLevels.s1), "support", t("keyLevels.executionApprox", { symbol: executionSymbol }), formatMoney(mstuEquivalent.s1))}
            ${levelChip(t("keyLevels.s2"), formatMoney(keyLevels.s2), "support-soft", t("keyLevels.executionApprox", { symbol: executionSymbol }), formatMoney(mstuEquivalent.s2))}
            ${levelChip(t("keyLevels.pivot"), formatMoney(keyLevels.pivot), "pivot", t("keyLevels.executionApprox", { symbol: executionSymbol }), formatMoney(mstuEquivalent.pivot))}
            ${levelChip(t("keyLevels.r1"), formatMoney(keyLevels.r1), "resistance", t("keyLevels.executionApprox", { symbol: executionSymbol }), formatMoney(mstuEquivalent.r1))}
            ${levelChip(t("keyLevels.r2"), formatMoney(keyLevels.r2), "resistance-soft", t("keyLevels.executionApprox", { symbol: executionSymbol }), formatMoney(mstuEquivalent.r2))}
          </div>
          <aside class="key-levels-spotlight">
            <div class="key-levels-spotlight-label">${escapeHtml(t("keyLevels.currentZone"))}</div>
            <div class="key-levels-spotlight-value">${escapeHtml(localizeBacktestText(keyLevels.zone_label || "--"))}</div>
            <div class="key-levels-spotlight-note">${escapeHtml(t("keyLevels.currentZoneNote", { signal: signalSymbol, execution: executionSymbol }))}</div>
          </aside>
        </div>
        <div class="key-levels-bottom">
          <article class="key-levels-meta-card">
            <span>${escapeHtml(t("keyLevels.nearestSupport"))}</span>
            <strong>${escapeHtml(translateKeyLevelLabel(keyLevels.nearest_support_key, localizeBacktestText(keyLevels.nearest_support_label || "--")))}</strong>
            <em>${escapeHtml(signalSymbol)} ${escapeHtml(formatMoney(keyLevels.nearest_support))} | ${escapeHtml(executionSymbol)} 约 ${escapeHtml(formatMoney(mstuEquivalent[keyLevels.nearest_support_label === "第一支撑" ? "s1" : keyLevels.nearest_support_label === "第二支撑" ? "s2" : "s3"]))}</em>
          </article>
          <article class="key-levels-meta-card">
            <span>${escapeHtml(t("keyLevels.nearestResistance"))}</span>
            <strong>${escapeHtml(translateKeyLevelLabel(keyLevels.nearest_resistance_key, localizeBacktestText(keyLevels.nearest_resistance_label || "--")))}</strong>
            <em>${escapeHtml(signalSymbol)} ${escapeHtml(formatMoney(keyLevels.nearest_resistance))} | ${escapeHtml(executionSymbol)} 约 ${escapeHtml(formatMoney(mstuEquivalent[keyLevels.nearest_resistance_label === "第一压力" ? "r1" : keyLevels.nearest_resistance_label === "第二压力" ? "r2" : "r3"]))}</em>
          </article>
          <article class="key-levels-meta-card key-levels-meta-emphasis">
            <span>${escapeHtml(t("keyLevels.currentHit"))}</span>
            <strong>${escapeHtml(localizeSignalText(levelSignals || "--"))}</strong>
            <em>${escapeHtml(localizeSignalText(signal.reason || t("keyLevels.continueWatch")))}</em>
          </article>
        </div>
      </section>
    `
  );

  const best = backtest.best_result || {};
  safeSetHtml(
    refs.backtestSummary,
    [
      metricRow(t("backtest.status"), backtest.status || "--"),
      metricRow(t("backtest.winRate"), best.win_rate !== undefined ? `${best.win_rate}%` : "--"),
      metricRow(t("backtest.return"), best.return_pct !== undefined ? `${best.return_pct}%` : "--"),
      metricRow(t("backtest.finalValue"), formatMoney(best.final_value)),
      metricRow(t("backtest.closedTrades"), best.total_closed ?? "--"),
      metricRow(t("backtest.recommendedGapUp"), backtest.recommended?.gap_up_pct ?? "--"),
    ].join("")
  );

  safeSetHtml(
    refs.backtestModel,
    Array.isArray(backtest.model_breakdown)
      ? backtest.model_breakdown
          .map(
            (item) => `
              <article class="model-card">
                <strong>${escapeHtml(localizeBacktestText(item.label))}</strong>
                <span>${escapeHtml(localizeBacktestText(item.value))}</span>
                <small>${escapeHtml(localizeBacktestText(item.description))}</small>
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
    t("system.line", { signal: data.system?.signal_symbol || "MSTR", execution: data.system?.execution_symbol || "MSTU" })
  );
  safeSetText(refs.lastUpdated, t("system.lastUpdated", { time: new Date().toLocaleTimeString(uiState.locale) }));
  renderFreshness();
  pushLog("success", t("log.refreshDone", { status: ui.decision_status || signal.action || "UNKNOWN" }));
}

function renderError(message, errorDetail = "") {
  safeSetText(refs.tradingDate, "--");
  safeSetText(refs.marketPhase, "UNKNOWN");
  safeSetText(refs.signalAction, "ERROR");
  if (refs.signalAction) {
    refs.signalAction.className = "signal-action sell";
  }
  safeSetText(refs.signalReason, message);
  safeSetText(refs.signalList, errorDetail || t("error.signalList"));
  safeSetText(refs.mstrMeta, t("error.signalSourceUnavailable"));
  safeSetText(refs.mstuMeta, t("error.executionUnavailable"));
  safeSetHtml(refs.backtestModel, "");
  window.__lastDaemonStatus = "offline";
  window.__lastDaemonHeartbeat = "--";
  window.__lastDaemonCycle = "--";
  safeSetText(refs.webhookStatus, t("error.webhookUnavailable"));
  safeSetText(refs.lastUpdated, t("system.lastUpdated", { time: new Date().toLocaleTimeString(uiState.locale) }));
  safeSetText(refs.summaryDecision, t("error.errorTitle"));
  safeSetText(refs.summaryReason, message);
  safeSetText(refs.summaryPhase, t("market.UNKNOWN"));
  safeSetText(refs.summaryTradingDate, "--");
  safeSetText(refs.summaryOps, t("error.summaryOps"));
  safeSetText(refs.summaryOpsHint, errorDetail || t("error.summaryOpsHint"));
  if (refs.toneDirection) {
    refs.toneDirection.className = toneClassName("neutral");
  }
  safeSetText(refs.toneDirection, t("tone.neutral"));
  safeSetText(refs.toneSummary, t("tone.errorSummary"));
  safeSetText(refs.toneBias, t("tone.errorBias"));
  safeSetText(refs.toneMeta, t("tone.errorMeta"));
  safeSetHtml(
    refs.technicalSignals,
    `<article class="technical-group"><div class="technical-group-title">${escapeHtml(t("technical.title"))}</div><div class="technical-empty">${escapeHtml(t("technical.unavailable"))}</div></article>`
  );
  setDecisionTone("error");
  setRefreshBadge("error", t("status.offline"));
  setErrorBanner(`${message}${errorDetail ? `：${errorDetail}` : ""}`, "error");
  announceRefresh(t("announce.refreshError"));
  renderFreshness();
  pushLog("error", `${message}${errorDetail ? ` | ${errorDetail}` : ""}`);
}

async function saveWebhookConfig() {
  if (!uiState.webhookConfigLoaded) {
    pushLog("error", t("log.webhookBlockedSave"));
    return;
  }
  pushLog("info", t("log.webhookSaving"));
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
    pushLog("success", t("log.webhookSaved"));
  } catch (error) {
    pushLog("error", t("log.webhookSaveError", { error: error?.message || "" }));
  }
}

async function sendTestWebhook() {
  if (!uiState.webhookConfigLoaded) {
    pushLog("error", t("log.webhookBlockedTest"));
    return;
  }
  pushLog("info", t("log.webhookTestStart"));
  try {
    const response = await fetch("/api/webhook-test", { method: "POST" });
    const data = await response.json();
    if (data.webhook) {
      renderWebhook(data.webhook);
    }
    pushLog(data.ok ? "success" : "error", data.message || "测试消息已处理");
  } catch (error) {
    pushLog("error", t("log.webhookTestError", { error: error?.message || "" }));
  }
}

async function loadWebhookConfig() {
  pushLog("info", t("log.webhookLoading"));
  if (refs.saveWebhookButton) refs.saveWebhookButton.disabled = true;
  if (refs.testWebhookButton) refs.testWebhookButton.disabled = true;
  try {
    const response = await fetch(`/api/webhook-config?t=${Date.now()}`, {
      cache: "no-store",
      headers: { "Cache-Control": "no-cache" },
    });
    const data = await response.json();
    uiState.webhookConfigLoaded = true;
    renderWebhook(data);
    pushLog("success", t("log.webhookLoaded"));
  } catch (error) {
    uiState.webhookConfigLoaded = false;
    pushLog("error", t("log.webhookLoadError", { error: error?.message || "" }));
  }
}

async function loadDashboard(options = {}) {
  const { manual = false } = options;
  if (uiState.refreshInFlight) {
    pushLog("info", t("log.requestSkip"));
    return;
  }
  uiState.refreshInFlight = true;
  setRefreshBadge("loading", manual ? t("status.loadingManual") : t("status.loadingAuto"));
  announceRefresh(manual ? t("announce.refreshManual") : t("announce.refreshAuto"));
  setErrorBanner("");
  if (refs.refreshButton) refs.refreshButton.disabled = true;
  pushLog("info", t("log.requestStart"));
  try {
    const response = await fetch(`/api/dashboard?t=${Date.now()}`, {
      cache: "no-store",
      headers: { "Cache-Control": "no-cache" },
    });
    if (!response.ok) {
      throw new Error(`dashboard ${response.status}`);
    }
    pushLog("info", t("log.responseReceived", { status: response.status }));
    const data = await response.json();
    pushLog("info", t("log.renderStart"));
    uiState.lastSuccessAt = new Date().toISOString();
    renderSnapshot(data);
    setRefreshBadge("success", t("status.live"));
    announceRefresh(t("announce.refreshDone"));
  } catch (error) {
    renderError(t("banner.snapshotUnavailable"), error?.message || "");
  } finally {
    uiState.refreshInFlight = false;
    if (refs.refreshButton) refs.refreshButton.disabled = false;
    renderFreshness();
  }
}

async function runRecoveryScan() {
  pushLog("info", t("log.recoveryStart"));
  try {
    const response = await fetch("/api/ops/recover", { method: "POST" });
    const data = await response.json();
    pushLog("success", t("log.recoveryDone", { count: data.expired_count || 0 }));
    await loadDashboard({ manual: true });
  } catch (error) {
    pushLog("error", t("log.recoveryError", { error: error?.message || "" }));
  }
}

async function expireTradeFromDashboard(tradeId) {
  if (!tradeId) {
    return;
  }
  pushLog("info", t("trade.expireStart", { id: tradeId }));
  try {
    const response = await fetch(`/api/trades/${encodeURIComponent(tradeId)}/expire`, {
      method: "POST",
    });
    if (!response.ok) {
      throw new Error(`expire ${response.status}`);
    }
    const data = await response.json();
    pushLog("success", t("trade.expireDone", { id: data.trade_id || tradeId }));
    uiState.selectedTradeId = tradeId;
    await loadDashboard({ manual: true });
    await loadTradeDetail(tradeId);
  } catch (error) {
    pushLog("error", t("trade.expireError", { error: error?.message || "" }));
  }
}

window.addEventListener("error", (event) => {
  renderError(t("banner.renderError"), event.message || "");
});

if (refs.refreshButton) {
  refs.refreshButton.addEventListener("click", () => loadDashboard({ manual: true }));
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

if (refs.languageSwitcher) {
  refs.languageSwitcher.addEventListener("change", (event) => {
    setLocale(event.target.value);
    renderFreshness();
    if (uiState.webhookConfigLoaded) {
      renderWebhook({
        url: refs.webhookUrl?.value || "",
        mode: refs.webhookMode?.value || "trade_only",
        enabled: Boolean(refs.webhookEnabled?.checked),
        last_push_status: "",
        last_push_message: "",
        last_push_at: refs.webhookLastPushAt?.textContent || "",
        last_signal_summary: refs.webhookLastSignal?.textContent || "--",
      });
    }
    loadDashboard({ manual: false });
  });
}

setLocale(detectPreferredLocale());
pushLog("info", t("log.dashboardLoaded"));
renderFreshness();
loadWebhookConfig();
loadDashboard();
window.setInterval(renderFreshness, 1000);
window.setInterval(() => loadDashboard({ manual: false }), 30000);
