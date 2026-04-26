"""MSTU 日内做T监控系统 - 配置文件。

重要约定：
- 实时策略现在优先参考 MSTR 的方向和强弱，再映射到 MSTU 上执行做T。
- 如果 OpenClaw 后续更新策略，请尽量让 config.py 和 backtest.py 的默认参数保持同一套口径。
"""

from mstu_trading.app_runtime import POSITION_STATE_FILE
from mstu_trading.app_runtime import env_bool, env_float, env_int, env_str


# ===== BTC 大盘配置 =====
# BTC 数据用于判断比特币市场基调，影响做T方向偏好
BTC_SYMBOL = env_str("BTC_SYMBOL", "BTC-USD")  # yfinance BTC 交易对
BTC_TREND_LOOKBACK = env_str("BTC_TREND_LOOKBACK", "1d")  # BTC 趋势回看周期
BTC_EMA_FAST_PERIOD = env_int("BTC_EMA_FAST_PERIOD", 9)
BTC_EMA_SLOW_PERIOD = env_int("BTC_EMA_SLOW_PERIOD", 21)

# ===== 每日基调配置 =====
# 基于盘前缺口和 BTC 趋势判断当日做T方向偏好
DAILY_TONE_ENABLED = env_bool("DAILY_TONE_ENABLED", True)
# 正T阈值调整：上涨基调时放宽
DAILY_TONE_BULLISH_FORWARD_BIAS = env_float("DAILY_TONE_BULLISH_FORWARD_BIAS", 0.25)
# 反T阈值调整：下跌基调时放宽
DAILY_TONE_BEARISH_REVERSE_BIAS = env_float("DAILY_TONE_BEARISH_REVERSE_BIAS", 0.25)

# ===== 飞书配置 =====
FEISHU_WEBHOOK = env_str("FEISHU_WEBHOOK", "")
FEISHU_APP_ID = env_str("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = env_str("FEISHU_APP_SECRET", "")
FEISHU_GROUP_ID = env_str("FEISHU_GROUP_ID", "")

# ===== 股票配置 =====
SYMBOL = env_str("MSTU_SYMBOL", "MSTU")
COST_PRICE = env_float("MSTU_COST_PRICE", 14.00)      # 成本价
CURRENT_PRICE = env_float("MSTU_CURRENT_PRICE", 7.27)  # 近期股价（仅参考）
POSITION = env_int("MSTU_BASE_POSITION", 3100)         # 底仓股数（不卖出）
AVAILABLE_CASH = env_float("MSTU_AVAILABLE_CASH", 4222)  # 可用资金

# ===== 手续费配置 =====
# 默认按美股 NMS 订单计费；印花税保留成显式开关，方便按券商实际账单切换。
STAMP_DUTY_ENABLED = env_bool("MSTU_STAMP_DUTY_ENABLED", False)
STAMP_DUTY_USD_TO_RM_FX = env_float("MSTU_STAMP_DUTY_USD_TO_RM_FX", 4.70)

# ===== 交易时间（北京时间 UTC+8）=====
# 夏令时（3月-11月）
PRE_MARKET_START = "16:00"   # 盘前开始
PRE_MARKET_END = "21:30"     # 盘前结束/盘中开始
REGULAR_START = "21:30"      # 盘中开始
REGULAR_END = "00:00"        # 用户关心的盘中结束（12点后睡觉）
AFTER_HOURS_START = "04:00"  # 盘后开始（用户睡觉，不监控）
AFTER_HOURS_END = "08:00"    # 盘后结束
OVERNIGHT_START = "08:00"    # 夜盘开始
OVERNIGHT_END = "16:00"      # 夜盘结束

# 用户不关心的时间段：00:00-08:00（睡觉时间）
SLEEP_START = "00:00"
SLEEP_END = "08:00"

# ===== 做T策略参数 =====
# 说明：以下阈值默认服务于“MSTR 发信号，MSTU 执行”的模式。
# 如果后续看到回测和实盘行为不一致，优先检查这里是否和 backtest.py 默认参数脱节。
# 仓位管理
TRADE_LOT_SIZE = 70       # 单次买入股数
MAX_LOTS_PER_DAY = 3      # 每日最多做T次数（盘中）
MIN_TRADE_AMOUNT = 250     # 最小交易金额
MAX_TRADE_AMOUNT = 250     # 盘中低吸单次最大买入金额（保守）

# 止盈止损（MSTR 信号、MSTU 执行）
TAKE_PROFIT_PCT = 0.02      # 盘中低吸止盈 2.0%
STOP_LOSS_PCT = 0.015       # 盘中低吸止损 1.5%
DAILY_MAX_LOSS = 100       # 日内最大亏损 $100

# ===== 跨时段策略参数 =====
# 盘前/夜盘买入 → 盘中卖出
PREMARKET_BUY_ENABLED = True      # 盘前买入开关
OVERNIGHT_BUY_ENABLED = True      # 夜盘买入开关
PREMARKET_MAX_BUY_AMT = 600      # 盘前单次最大买入金额
OVERNIGHT_MAX_BUY_AMT = 600      # 夜盘单次最大买入金额

# --- 低吸模式 (Buy the Dip) ---
PREMARKET_BUY_GAP_DOWN = -0.03    # MSTR 盘前低开3%以上才在 MSTU 上低吸
OVERNIGHT_BUY_DROP = -0.03        # MSTR 夜盘跌3%以上才在 MSTU 上低吸

# --- 追涨模式 (Momentum) ---
PREMARKET_MOMENTUM_ENABLED = True         # 盘前追涨开关
PREMARKET_MOMENTUM_GAP_UP = 0.012         # MSTR 盘前高开1.2%以上触发追涨
PREMARKET_MOMENTUM_MIN_GAP = 0.01         # 最低高开1.0%才考虑
OVERNIGHT_MOMENTUM_ENABLED = True         # 夜盘追涨开关
OVERNIGHT_MOMENTUM_RISE = 0.012           # MSTR 夜盘涨1.2%以上触发追涨
OVERNIGHT_MOMENTUM_MIN_RISE = 0.01        # 最低涨1%才考虑
MOMENTUM_PROFIT_PCT = 0.018               # 追涨止盈1.8%
MOMENTUM_STOP_PCT = 0.01                  # 追涨止损1.0%
MOMENTUM_MAX_CHASE_PCT = 0.04             # 涨幅超过4%不追（防追高）
MOMENTUM_MAX_BUY_AMT = 750                # 追涨模式买入上限（MSTR 强势时提高权重）

# --- 通用跨时段参数 ---
CROSS_SESSION_PROFIT_PCT = 0.02   # 跨时段低吸止盈2.0%
CROSS_SESSION_STOP_PCT = 0.015    # 跨时段低吸止损1.5%

# --- MSTR 趋势确认 ---
# 让实时盘中逻辑更接近双标回测：除了看 MSTR 当日涨跌，还看 EMA/MACD 是否共振。
MSTR_TREND_FILTER_ENABLED = True
MSTR_FAST_EMA_PERIOD = 9
MSTR_SLOW_EMA_PERIOD = 21
MSTR_TREND_LOOKBACK_PERIOD = "5d"
MSTR_TREND_LOOKBACK_INTERVAL = "15m"

# --- moomoo 指标精简接入 ---
# 只接高价值、易维护的部分：VWAP 突破、牛熊线过滤、RSI/KDJ 变盘。
MSTR_SHORT_BULL_HIGH_EMA = 24
MSTR_SHORT_BULL_LOW_EMA = 23
MSTR_LONG_BULL_HIGH_EMA = 89
MSTR_LONG_BULL_LOW_EMA = 90
MSTR_BULL_STRUCTURE_CONFIRM_BARS = 3
MSTR_VWAP_VOLUME_RATIO_PERIOD = 5
MSTR_VWAP_MIN_VOLUME_RATIO = 1.2
# momentum 不只认“VWAP 上穿当根”，也识别“上穿后继续站稳 VWAP 的启动段”。
MSTR_MOMENTUM_RUNUP_MIN = 0.012
MSTR_MOMENTUM_INTRADAY_POSITION_MIN = 0.55
MSTR_MOMENTUM_PULLBACK_MAX = 0.012
MSTR_GAP_BREAKOUT_LIMIT = 0.05
MSTR_RSI_REBOUND_THRESHOLD = 22
MSTR_RSI_RECOVERY_LEVEL = 20
MSTR_KDJ_TURN_BULL_LEVEL = 30

# --- moomoo K线形态精简接入 ---
# 形态只用于 MSTR 侧确认，不直接单独触发交易。
MSTR_PATTERN_FILTER_ENABLED = True
MSTR_MORNING_STAR_FIRST_BAR_MAX = 0.95
MSTR_MORNING_STAR_THIRD_BAR_MIN = 1.05
MSTR_EVENING_STAR_FIRST_BAR_MIN = 1.03
MSTR_EVENING_STAR_THIRD_BAR_MAX = 0.97
MSTR_DOJI_BODY_MAX = 0.03
MSTR_INSIDE_BAR_MOTHER_BODY_MIN = 0.7

# ===== 量价分析参数 =====
VOLUME_MA_PERIOD = 5       # 均量周期
VOLUME_HIGH_MULTIPLE = 1.5 # 放量倍数
VOLUME_LOW_MULTIPLE = 0.7  # 缩量倍数

# ===== 趋势过滤参数 =====
TREND_DOWN_THRESHOLD = -0.03  # 下跌趋势阈值 -3%
SUPPORT_LEVEL_PCT = 0.02      # 支撑位偏离容忍度 2%

# ===== 持仓状态文件 =====
# 统一由 app_runtime 管理，支持通过 MSTU_TRADING_STATE_DIR 环境变量覆写。

# 技术指标参数
RSI_PERIOD = 14
RSI_OVERSOLD = 30          # 超卖
RSI_OVERBOUGHT = 70        # 超买
BB_PERIOD = 20             # 布林带周期
BB_STD = 2.0               # 布林带标准差
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

# ===== 扫描间隔 =====
SCAN_INTERVAL_SEC = 180    # 3分钟扫描一次
NO_TRADE_MINUTES = 30      # 开盘/收盘前30分钟不操作

# ===== 飞书推送配置 =====
NOTIFY_CHANNEL = "feishu"
NOTIFY_TARGET = "chat:oc_af2f3805ae0c8f34718d3eaf3f464f03"

# ===== 数据源 =====
DATA_SOURCE = "yahoo"      # yahoo / alpha_vantage
ALPHA_VANTAGE_KEY = env_str("ALPHA_VANTAGE_KEY", "")
