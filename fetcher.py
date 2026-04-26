"""MSTU 行情数据获取模块 - 优化版

主要用 Nasdaq API（无严格限制）
Alpha Vantage 只每天调用一次（获取交易日历）
"""

import requests
import pandas as pd
import json
from datetime import datetime, timezone, timedelta
import time
import os
import config
from app_runtime import ALPHA_VANTAGE_CACHE_FILE
from indicators import calculate_macd, calculate_rsi

# yfinance 用于获取准确的昨收价
try:
    import yfinance as yf
    YFINANCE_OK = True
except ImportError:
    yf = None
    YFINANCE_OK = False

_last_call_time = 0
_alpha_vantage_cache = None
_alpha_vantage_cache_time = None
_trend_cache = {}
_btc_cache = {}
_daily_tone_cache = {}


def get_btc_trend(interval: str = "15m") -> dict:
    """获取 BTC 大盘趋势数据。
    
    返回 BTC 的趋势信息，用于判断比特币市场基调：
    - EMA 快慢线趋势
    - 价格相对均线位置
    - 涨跌幅
    
    Returns:
        {
            "price": 当前价,
            "change_pct": 涨跌幅百分比,
            "ema_fast": 快线值,
            "ema_slow": 慢线值,
            "ema_bullish": 快线上穿慢线,
            "price_above_ema_fast": 价格在快线上方,
            "trend": "bullish"/"bearish"/"neutral"
        }
    """
    if not YFINANCE_OK:
        return {"error": "yfinance not installed"}
    
    # 缓存 5 分钟
    cache_key = "btc_trend"
    now_ts = time.time()
    cached = _btc_cache.get(cache_key)
    if cached and now_ts - cached["ts"] < 300:
        return cached["data"]
    
    try:
        ticker = yf.Ticker(config.BTC_SYMBOL)
        # 最少需要 EMA_PERIOD + 1 根 K 线
        hist = ticker.history(period="3d", interval=interval)
        
        if hist is None or hist.empty or len(hist) < config.BTC_EMA_SLOW_PERIOD:
            return {"error": "BTC history unavailable"}
        
        close = hist["Close"].astype(float)
        
        # 计算 EMA
        ema_fast = close.ewm(span=config.BTC_EMA_FAST_PERIOD, adjust=False).mean()
        ema_slow = close.ewm(span=config.BTC_EMA_SLOW_PERIOD, adjust=False).mean()
        
        last_price = float(close.iloc[-1])
        prev_close = float(close.iloc[-2]) if len(close) >= 2 else last_price
        last_ema_fast = float(ema_fast.iloc[-1])
        last_ema_slow = float(ema_slow.iloc[-1])
        
        change_pct = (last_price - prev_close) / prev_close if prev_close > 0 else 0.0
        ema_bullish = last_ema_fast > last_ema_slow
        price_above_fast = last_price > last_ema_fast
        
        # 综合判断趋势
        if ema_bullish and price_above_fast and change_pct > 0:
            trend = "bullish"
        elif not ema_bullish and not price_above_fast and change_pct < 0:
            trend = "bearish"
        else:
            trend = "neutral"
        
        result = {
            "price": round(last_price, 2),
            "change_pct": round(change_pct * 100, 2),
            "ema_fast": round(last_ema_fast, 2),
            "ema_slow": round(last_ema_slow, 2),
            "ema_bullish": ema_bullish,
            "price_above_ema_fast": price_above_fast,
            "trend": trend
        }
        
        _btc_cache[cache_key] = {"ts": now_ts, "data": result}
        return result
    except Exception as e:
        return {"error": str(e)}


def calculate_daily_tone(mstr_trend: dict = None, btc_trend: dict = None, ttl_seconds: int = 300) -> dict:
    """综合 MSTR 趋势 + BTC 大盘计算每日做T基调。
    
    基调影响做T策略的阈值调整：
    - bullish/bullish_strong: 正T阈值放宽，反T阈值收紧
    - bearish/bearish_strong: 反T阈值放宽，正T阈值收紧
    - neutral: 维持默认阈值
    
    Args:
        mstr_trend: MSTR 趋势数据（来自 get_mstr_trend）
        btc_trend: BTC 趋势数据（来自 get_btc_trend）
        ttl_seconds: 缓存时长
    
    Returns:
        {
            "tone": "bullish_strong"/"bullish"/"neutral"/"bearish"/"bearish_strong",
            "forward_bias": 正T阈值放宽值（加到 trigger_threshold），
            "reverse_bias": 反T阈值放宽值（加到 trigger_threshold），
            "reason": 基调判断原因,
            "mstr_trend": MSTR 趋势,
            "btc_trend": BTC 趋势
        }
    """
    # 缓存检查
    cache_key = "daily_tone"
    now_ts = time.time()
    cached = _daily_tone_cache.get(cache_key)
    if cached and now_ts - cached["ts"] < ttl_seconds:
        return cached["data"]
    
    # 获取 BTC 趋势（如果没传入）
    if btc_trend is None or "error" in btc_trend:
        btc_trend = get_btc_trend()
    
    # 获取 MSTR 趋势（如果没传入）
    if mstr_trend is None or "error" in mstr_trend:
        try:
            from fetcher import get_mstr_indicators
            mstr_trend = get_mstr_indicators()
        except Exception as e:
            mstr_trend = {"error": str(e)}
    
    # 默认基调
    tone = "neutral"
    forward_bias = 0.0
    reverse_bias = 0.0
    reason_parts = []
    reason_part_structs = []
    
    # BTC 大盘趋势
    btc_trend_val = btc_trend.get("trend", "neutral") if "error" not in btc_trend else "neutral"
    btc_change = btc_trend.get("change_pct", 0) if "error" not in btc_trend else 0
    btc_ema_bullish = btc_trend.get("ema_bullish", True) if "error" not in btc_trend else True
    btc_price_above_fast = btc_trend.get("price_above_ema_fast", True) if "error" not in btc_trend else True
    
    # MSTR 趋势指标（字段名对应 get_mstr_indicators）
    mstr_ema_bullish = mstr_trend.get("mstr_ema_bullish", True) if "error" not in mstr_trend else True
    mstr_macd_bullish = mstr_trend.get("mstr_macd_bullish", True) if "error" not in mstr_trend else True
    mstr_bull_structure_weak = mstr_trend.get("mstr_bull_structure_weak", True) if "error" not in mstr_trend else True
    mstr_bull_structure_strong = mstr_trend.get("mstr_bull_structure_strong", False) if "error" not in mstr_trend else False
    mstr_change_pct = mstr_trend.get("mstr_change_pct", 0) if "error" not in mstr_trend else 0
    mstr_gap_pct = mstr_change_pct  # 用涨跌幅作为缺口近似
    
    # ===== 基调判断逻辑 =====
    
    # BTC 强上涨：EMA 多头 + 价格在快线上方 + 涨幅 > 1%
    if btc_trend_val == "bullish" and btc_change > 1.0:
        tone = "bullish"
        reason_parts.append(f"BTC涨{btc_change:+.1f}%多头结构")
        reason_part_structs.append({"code": "BTC_BULLISH", "params": {"change_pct": round(btc_change, 1)}})
        if btc_change > 2.0:
            tone = "bullish_strong"
            reason_parts.append("(强)")
            reason_part_structs[-1]["params"]["strength"] = "strong"
    
    # BTC 强下跌：EMA 空头 + 价格在快线下方 + 跌幅 > 1%
    elif btc_trend_val == "bearish" and btc_change < -1.0:
        tone = "bearish"
        reason_parts.append(f"BTC跌{btc_change:+.1f}%空头结构")
        reason_part_structs.append({"code": "BTC_BEARISH", "params": {"change_pct": round(btc_change, 1)}})
        if btc_change < -2.0:
            tone = "bearish_strong"
            reason_parts.append("(强)")
            reason_part_structs[-1]["params"]["strength"] = "strong"
    
    # MSTR 基调补充判断
    # 高开 + 多头结构 → 增强 bullish
    if tone in ["neutral", "bullish"] and mstr_gap_pct > 1.5 and mstr_bull_structure_weak:
        if tone == "neutral":
            tone = "bullish"
        elif tone == "bullish":
            tone = "bullish_strong"
        reason_parts.append(f"MSTR高开{mstr_gap_pct:+.1f}%")
        reason_part_structs.append({"code": "MSTR_GAP_UP", "params": {"change_pct": round(mstr_gap_pct, 1)}})
    
    # 低开 + 空头结构 → 增强 bearish
    elif tone in ["neutral", "bearish"] and mstr_gap_pct < -1.5 and not mstr_bull_structure_weak:
        if tone == "neutral":
            tone = "bearish"
        elif tone == "bearish":
            tone = "bearish_strong"
        reason_parts.append(f"MSTR低开{mstr_gap_pct:+.1f}%")
        reason_part_structs.append({"code": "MSTR_GAP_DOWN", "params": {"change_pct": round(mstr_gap_pct, 1)}})
    
    # 盘前/夜盘均线关系判断
    # EMA 多头共振 → bullish
    if tone == "neutral" and mstr_ema_bullish and mstr_macd_bullish and btc_ema_bullish:
        tone = "bullish"
        reason_parts.append("MSTR+BTC均线共振多头")
        reason_part_structs.append({"code": "MSTR_BTC_RESONANCE_BULLISH", "params": {}})
    
    # EMA 空头共振 → bearish
    elif tone == "neutral" and not mstr_ema_bullish and not mstr_macd_bullish and not btc_ema_bullish:
        tone = "bearish"
        reason_parts.append("MSTR+BTC均线共振空头")
        reason_part_structs.append({"code": "MSTR_BTC_RESONANCE_BEARISH", "params": {}})
    
    # ===== 计算阈值调整 =====
    if tone in ["bullish", "bullish_strong"]:
        # 正T放宽，反T收紧
        forward_bias = config.DAILY_TONE_BULLISH_FORWARD_BIAS
        reverse_bias = -0.25  # 反T更严格
        if tone == "bullish_strong":
            forward_bias += 0.25  # 更放宽
    
    elif tone in ["bearish", "bearish_strong"]:
        # 反T放宽，正T收紧
        reverse_bias = config.DAILY_TONE_BEARISH_REVERSE_BIAS
        forward_bias = -0.25  # 正T更严格
        if tone == "bearish_strong":
            reverse_bias += 0.25  # 更放宽
    
    # neutral 维持默认，不调整
    
    reason = " | " .join(reason_parts) if reason_parts else "无明显方向信号"
    if not reason_part_structs:
        reason_part_structs.append({"code": "NO_CLEAR_DIRECTION", "params": {}})
    
    result = {
        "tone": tone,
        "forward_bias": forward_bias,
        "reverse_bias": reverse_bias,
        "reason": reason,
        "reason_parts": reason_part_structs,
        "mstr_trend": mstr_trend if "error" not in mstr_trend else {},
        "btc_trend": btc_trend if "error" not in btc_trend else {},
    }
    
    _daily_tone_cache[cache_key] = {"ts": now_ts, "data": result}
    return result


def calculate_kdj(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> dict:
    """计算 KDJ，供实时快照和策略加分使用。"""
    lowest_low = low.rolling(window=period, min_periods=period).min()
    highest_high = high.rolling(window=period, min_periods=period).max()
    spread = (highest_high - lowest_low).replace(0, pd.NA)
    rsv = ((close - lowest_low) / spread * 100).fillna(50)
    k = rsv.ewm(alpha=1 / 3, adjust=False).mean()
    d = k.ewm(alpha=1 / 3, adjust=False).mean()
    j = 3 * k - 2 * d
    return {"k": k, "d": d, "j": j}


def calculate_intraday_vwap(df: pd.DataFrame) -> pd.Series:
    """按交易日重置的日内 VWAP。"""
    typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
    traded_value = typical_price * df["Volume"]
    session_key = df.index.strftime("%Y-%m-%d")
    cum_value = traded_value.groupby(session_key).cumsum()
    cum_volume = df["Volume"].groupby(session_key).cumsum().replace(0, pd.NA)
    return (cum_value / cum_volume).fillna(df["Close"])


def detect_candlestick_patterns(df: pd.DataFrame) -> dict:
    """将 moomoo 中的关键 K 线形态翻译成 Python 条件。

    这里只保留对当前策略最有帮助的三类：
    - 早晨之星
    - 黄昏之星
    - 孕线突破
    """
    if len(df) < 4:
        return {
            "morning_star": False,
            "evening_star": False,
            "inside_bar_breakout_up": False,
            "inside_bar_breakout_down": False,
        }

    o = df["Open"].astype(float)
    h = df["High"].astype(float)
    l = df["Low"].astype(float)
    c = df["Close"].astype(float)
    ma10 = c.rolling(window=10, min_periods=10).mean()

    # 最近三根 K 线，对应 moomoo 里 REF(...,2/1/0)
    first_open, first_close = o.iloc[-3], c.iloc[-3]
    second_open, second_close = o.iloc[-2], c.iloc[-2]
    third_open, third_close = o.iloc[-1], c.iloc[-1]

    trend_up = bool(pd.notna(ma10.iloc[-1]) and pd.notna(ma10.iloc[-2]) and ma10.iloc[-1] > ma10.iloc[-2])
    trend_down = bool(pd.notna(ma10.iloc[-1]) and pd.notna(ma10.iloc[-2]) and ma10.iloc[-1] < ma10.iloc[-2])

    second_body_ratio = abs(second_open - second_close) / second_close if second_close else 0.0

    morning_star = (
        first_close / first_open < config.MSTR_MORNING_STAR_FIRST_BAR_MAX
        and second_open < first_close
        and second_body_ratio < config.MSTR_DOJI_BODY_MAX
        and third_close / third_open > config.MSTR_MORNING_STAR_THIRD_BAR_MIN
        and third_close > first_close
        and trend_down
    )

    evening_star = (
        first_close / first_open > config.MSTR_EVENING_STAR_FIRST_BAR_MIN
        and second_open > first_close
        and second_body_ratio < 0.02
        and third_close / third_open < config.MSTR_EVENING_STAR_THIRD_BAR_MAX
        and third_close < first_close
        and trend_up
    )

    mother_high = h.iloc[-4]
    mother_low = l.iloc[-4]
    mother_open = o.iloc[-4]
    mother_close = c.iloc[-4]
    mother_range = mother_high - mother_low
    mother_body = abs(mother_close - mother_open)
    strong_mother = (
        mother_range > 0
        and mother_body / mother_range > config.MSTR_INSIDE_BAR_MOTHER_BODY_MIN
    )
    child_inside = h.iloc[-3] < mother_high and l.iloc[-3] > mother_low
    uptrend_before = bool(pd.notna(ma10.iloc[-4]) and pd.notna(ma10.iloc[-5]) and ma10.iloc[-4] > ma10.iloc[-5] and c.iloc[-4] > c.iloc[-5])
    downtrend_before = bool(pd.notna(ma10.iloc[-4]) and pd.notna(ma10.iloc[-5]) and ma10.iloc[-4] < ma10.iloc[-5] and c.iloc[-4] < c.iloc[-5])
    breakout_up = c.iloc[-2] > mother_high
    breakout_down = c.iloc[-2] < mother_low

    inside_bar_breakout_up = child_inside and strong_mother and downtrend_before and breakout_up
    inside_bar_breakout_down = child_inside and strong_mother and uptrend_before and breakout_down

    return {
        "morning_star": bool(morning_star),
        "evening_star": bool(evening_star),
        "inside_bar_breakout_up": bool(inside_bar_breakout_up),
        "inside_bar_breakout_down": bool(inside_bar_breakout_down),
    }

def _rate_limit():
    """Nasdaq API 无严格限制"""
    pass

def get_nasdaq_realtime(symbol: str) -> dict:
    """获取 Nasdaq 实时行情（含盘前/盘后）"""
    url = f"https://api.nasdaq.com/api/quote/{symbol}/info?assetclass=etf"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }
    
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        data = resp.json()
        
        if not data.get("data"):
            return {"error": "Nasdaq API 无数据"}
        
        d = data["data"]
        primary = d.get("primaryData") or {}
        secondary = d.get("secondaryData") or {}  # 可能为 null
        
        def parse_price(s):
            try:
                return float(s.replace("$", "").replace(",", ""))
            except:
                return 0.0
        
        realtime_price = parse_price(primary.get("lastSalePrice", "$0"))
        # secondaryData 可能为 null，需要从 Alpha Vantage 获取 prev_close
        prev_close_price = parse_price(secondary.get("lastSalePrice", "$0")) if secondary else 0.0
        is_realtime = primary.get("isRealTime", False)
        last_trade_time = primary.get("lastTradeTimestamp", "")
        
        change_str = primary.get("netChange", "0").replace("+", "")
        change_pct_str = primary.get("percentageChange", "0%").replace("%", "").replace("+", "")
        
        try:
            change_val = float(change_str)
        except:
            change_val = 0.0
        try:
            change_pct_val = float(change_pct_str)
        except:
            change_pct_val = 0.0
        
        volume_str = primary.get("volume", "0").replace(",", "")
        try:
            volume_val = int(volume_str)
        except:
            volume_val = 0
        
        bid = parse_price(primary.get("bidPrice", "$0"))
        ask = parse_price(primary.get("askPrice", "$0"))
        
        return {
            "symbol": symbol,
            "price": realtime_price,
            "prev_close": prev_close_price,
            "change": change_val,
            "change_pct": change_pct_val,
            "is_realtime": is_realtime,
            "last_trade_time": last_trade_time,
            "volume": volume_val,
            "bid": bid,
            "ask": ask,
            "company_name": d.get("companyName", ""),
            "source": "nasdaq-realtime" if is_realtime else "nasdaq-delayed",
            "last_update": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        return {"error": str(e)}

def get_global_quote(symbol: str) -> dict:
    """获取 Alpha Vantage 数据（每天缓存一次）"""
    global _alpha_vantage_cache, _alpha_vantage_cache_time
    
    # 缓存有效期：12小时
    cache_file = ALPHA_VANTAGE_CACHE_FILE
    
    # 尝试从缓存读取
    if _alpha_vantage_cache and _alpha_vantage_cache_time:
        if time.time() - _alpha_vantage_cache_time < 12 * 3600:
            return _alpha_vantage_cache
    
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r') as f:
                cache = json.load(f)
                cache_time = cache.get('cache_time', 0)
                if time.time() - cache_time < 12 * 3600:
                    _alpha_vantage_cache = cache.get('data', {})
                    _alpha_vantage_cache_time = cache_time
                    return _alpha_vantage_cache
        except:
            pass
    
    # 调用 Alpha Vantage API
    url = "https://www.alphavantage.co/query"
    params = {
        "function": "GLOBAL_QUOTE",
        "symbol": symbol,
        "apikey": config.ALPHA_VANTAGE_KEY
    }
    
    try:
        resp = requests.get(url, params=params, timeout=30)
        data = resp.json()
        
        if "Information" in data:
            return {"error": f"API: {data['Information'][:80]}"}
        if "Error Message" in data:
            return {"error": data["Error Message"]}
        if "Note" in data:
            return {"error": "API 限频"}
        
        quote = data.get("Global Quote", {})
        if not quote:
            return {"error": "无报价数据"}
        
        result = {
            "symbol": quote.get("01. symbol"),
            "price": float(quote.get("05. price", 0)),
            "open": float(quote.get("02. open", 0)),
            "high": float(quote.get("03. high", 0)),
            "low": float(quote.get("04. low", 0)),
            "volume": int(quote.get("06. volume", 0)),
            "prev_close": float(quote.get("08. previous close", 0)),
            "latest_trading_day": quote.get("07. latest trading day", ""),
            "change": float(quote.get("09. change", 0)),
            "change_pct": float(quote.get("10. change percent", "0%").replace("%", ""))
        }
        
        # 缓存结果
        _alpha_vantage_cache = result
        _alpha_vantage_cache_time = time.time()
        try:
            with open(cache_file, 'w') as f:
                json.dump({'data': result, 'cache_time': _alpha_vantage_cache_time}, f)
        except:
            pass
        
        return result
        
    except Exception as e:
        return {"error": str(e)}

def get_session_type() -> str:
    """判断当前交易时段（北京时间）"""
    now_bj = datetime.now(timezone.utc) + timedelta(hours=8)
    weekday = now_bj.weekday()
    hour = now_bj.hour
    minute = now_bj.minute
    time_val = hour * 100 + minute
    
    if weekday == 5:
        return "closed"
    if weekday == 6 and time_val < 800:
        return "closed"
    
    if 0 <= hour < 8:
        return "sleep"
    
    if 8 <= hour < 16:
        if weekday <= 4 or weekday == 6:
            return "overnight"
    
    if 16 <= hour < 21 or (hour == 21 and minute < 30):
        return "premarket"
    
    if hour == 21 and minute >= 30:
        return "regular"
    if 22 <= hour <= 23:
        return "regular"
    
    return "closed"

def get_yahoo_quote(symbol: str) -> dict:
    """从 Yahoo Finance 获取准确的行情数据，支持盘前/盘后实时价格"""
    if not YFINANCE_OK:
        return {"error": "yfinance not installed"}
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        session = get_session_type()
        
        # 判断是否有盘前/盘后数据
        premarket_price = info.get("preMarketPrice")
        postmarket_price = info.get("postMarketPrice")
        regular_price = info.get("regularMarketPrice", 0)
        prev_close = info.get("regularMarketPreviousClose") or info.get("previousClose", 0)

        # 获取历史数据用于 high/low/volume，同时为盘前/夜盘修正昨收基准价。
        hist = ticker.history(period="5d")
        if len(hist) >= 1:
            latest = hist.iloc[-1]
            high = float(latest["High"])
            low = float(latest["Low"])
            volume = int(latest["Volume"])
            open_price = float(latest["Open"])
            latest_day = latest.name.strftime("%Y-%m-%d") if hasattr(latest.name, 'strftime') else str(latest.name)[:10]
            if session in ["premarket", "overnight"]:
                hist_prev_close = float(latest["Close"])
                if hist_prev_close > 0:
                    prev_close = hist_prev_close
        else:
            high = info.get("regularMarketDayHigh", 0)
            low = info.get("regularMarketDayLow", 0)
            volume = info.get("regularMarketVolume", 0)
            open_price = info.get("regularMarketOpen", 0)
            latest_day = ""

        # 选择正确的当前价格
        if session == "premarket" and premarket_price and premarket_price > 0:
            # 盘前：使用盘前价格
            current_price = premarket_price
            premarket_change = info.get("preMarketChange", 0)
            premarket_change_pct = info.get("preMarketChangePercent", 0)
            is_realtime = True
            price_source = "yahoo-premarket"
        elif session == "overnight" and postmarket_price and postmarket_price > 0:
            # 盘后：使用盘后价格
            current_price = postmarket_price
            is_realtime = True
            price_source = "yahoo-postmarket"
        else:
            # 盘中：使用常规价格
            current_price = regular_price
            is_realtime = True
            price_source = "yahoo-realtime"
        
        # 计算涨跌幅
        change_pct = (current_price - prev_close) / prev_close * 100 if prev_close > 0 else 0
        
        result = {
            "price": round(current_price, 4),
            "prev_close": round(prev_close, 4),
            "high": round(high, 2),
            "low": round(low, 2),
            "open": round(open_price, 2),
            "volume": volume,
            "source": price_source,
            "symbol": symbol,
            "latest_day": latest_day,
            "is_realtime": is_realtime,
            "change_pct": round(change_pct, 2),
        }
        
        # 盘前额外信息
        if session == "premarket" and premarket_price:
            result["premarket_price"] = premarket_price
            result["premarket_change_pct"] = round(premarket_change_pct, 2) if premarket_change_pct else round(change_pct, 2)
        
        return result
            
    except Exception as e:
        print(f"Yahoo error: {e}")
    return {"error": "Yahoo Finance fetch failed"}


def get_yahoo_trend_snapshot(symbol: str,
                             period: str = None,
                             interval: str = None,
                             ttl_seconds: int = 240) -> dict:
    """获取标的的短周期趋势快照。

    这里主要给实时策略补上和回测更一致的趋势快照：
    - EMA / MACD 趋势确认
    - moomoo 精简版牛熊线
    - VWAP 突破 + 量比 + 假突破过滤
    - RSI / KDJ 变盘加分
    为了避免每次扫描都重复拉历史数据，这里做一个短 TTL 缓存。
    """
    if not YFINANCE_OK:
        return {"error": "yfinance not installed"}

    period = period or config.MSTR_TREND_LOOKBACK_PERIOD
    interval = interval or config.MSTR_TREND_LOOKBACK_INTERVAL
    cache_key = f"{symbol}:{period}:{interval}"
    now_ts = time.time()
    cached = _trend_cache.get(cache_key)
    if cached and now_ts - cached["ts"] < ttl_seconds:
        return cached["data"]

    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period, interval=interval)
        if hist is None or hist.empty or len(hist) < config.MSTR_SLOW_EMA_PERIOD:
            return {"error": f"{symbol} trend history unavailable"}

        close = hist["Close"].astype(float)
        high = hist["High"].astype(float)
        low = hist["Low"].astype(float)
        volume = hist["Volume"].astype(float).fillna(0)
        ema_fast = close.ewm(span=config.MSTR_FAST_EMA_PERIOD, adjust=False).mean()
        ema_slow = close.ewm(span=config.MSTR_SLOW_EMA_PERIOD, adjust=False).mean()
        macd = calculate_macd(close)
        rsi = calculate_rsi(close, period=9)
        kdj = calculate_kdj(high, low, close)
        vwap = calculate_intraday_vwap(hist)
        patterns = detect_candlestick_patterns(hist)
        short_top = high.ewm(span=config.MSTR_SHORT_BULL_HIGH_EMA, adjust=False).mean()
        short_bottom = low.ewm(span=config.MSTR_SHORT_BULL_LOW_EMA, adjust=False).mean()
        long_top = high.ewm(span=config.MSTR_LONG_BULL_HIGH_EMA, adjust=False).mean()
        long_bottom = low.ewm(span=config.MSTR_LONG_BULL_LOW_EMA, adjust=False).mean()

        last_close = float(close.iloc[-1])
        prev_close = float(close.iloc[-2])
        last_open = float(hist["Open"].iloc[-1])
        last_vwap = float(vwap.iloc[-1])
        prev_vwap = float(vwap.iloc[-2])
        prev_rsi = float(rsi.iloc[-2]) if pd.notna(rsi.iloc[-2]) else 50.0
        last_rsi = float(rsi.iloc[-1]) if pd.notna(rsi.iloc[-1]) else 50.0
        prev_j = float(kdj["j"].iloc[-2]) if pd.notna(kdj["j"].iloc[-2]) else 50.0
        last_j = float(kdj["j"].iloc[-1]) if pd.notna(kdj["j"].iloc[-1]) else 50.0
        volume_window = volume.iloc[-(config.MSTR_VWAP_VOLUME_RATIO_PERIOD + 1):-1]
        volume_ratio = float(volume.iloc[-1] / volume_window.mean()) if len(volume_window) > 0 and volume_window.mean() > 0 else 1.0
        gap_pct = ((last_open - prev_close) / prev_close) if prev_close > 0 else 0.0
        vwap_cross_up = prev_close <= prev_vwap and last_close > last_vwap
        vwap_cross_down = prev_close >= prev_vwap and last_close < last_vwap
        session_open = float(hist["Open"].iloc[0])
        session_high = float(high.max())
        session_low = float(low.min())
        run_up_from_open = ((session_high - session_open) / session_open) if session_open > 0 else 0.0
        pullback_from_high = ((session_high - last_close) / session_high) if session_high > 0 else 0.0
        intraday_position = (
            (last_close - session_low) / (session_high - session_low)
            if session_high > session_low else 0.5
        )
        vwap_hold_above = bool(last_close > last_vwap and prev_close > prev_vwap)
        vwap_momentum_ready = bool(
            vwap_cross_up or (
                vwap_hold_above
                and run_up_from_open >= config.MSTR_MOMENTUM_RUNUP_MIN
                and intraday_position >= config.MSTR_MOMENTUM_INTRADAY_POSITION_MIN
                and pullback_from_high <= config.MSTR_MOMENTUM_PULLBACK_MAX
            )
        )
        gap_too_big = gap_pct > config.MSTR_GAP_BREAKOUT_LIMIT
        rsi_bottom_rebound = prev_rsi <= config.MSTR_RSI_REBOUND_THRESHOLD and last_rsi > config.MSTR_RSI_RECOVERY_LEVEL
        kdj_turn_bull = prev_j <= config.MSTR_KDJ_TURN_BULL_LEVEL and last_j > config.MSTR_KDJ_TURN_BULL_LEVEL
        short_above_long = bool(short_bottom.iloc[-1] > long_bottom.iloc[-1])
        price_above_long_top = bool(last_close > long_top.iloc[-1])
        short_bottom_rising = bool(short_bottom.iloc[-1] > short_bottom.iloc[-2])
        long_bottom_rising = bool(long_bottom.iloc[-1] > long_bottom.iloc[-2])
        confirm_bars = min(config.MSTR_BULL_STRUCTURE_CONFIRM_BARS, len(short_bottom))
        persistent_structure = bool(
            all(
                short_bottom.iloc[-idx] > long_bottom.iloc[-idx]
                for idx in range(1, confirm_bars + 1)
            )
        )
        bull_structure_weak = short_above_long and price_above_long_top
        bull_structure_strong = (
            bull_structure_weak and persistent_structure and short_bottom_rising and long_bottom_rising
        )

        # ===== MACD 历史序列（最近20根K线）=====
        lookback = min(20, len(macd["histogram"]))
        hist_series = macd["histogram"].iloc[-lookback:].tolist()
        macd_series = macd["macd"].iloc[-lookback:].tolist()
        close_series = close.iloc[-lookback:].tolist()
        signal_series = macd["signal"].iloc[-lookback:].tolist()

        # ===== 功能1: 顶背离/底背离检测 =====
        macd_divergence = "none"  # none / bottom / top
        if len(hist_series) >= 10 and len(close_series) >= 10:
            # 底背离：价格创新低但MACD柱未创新低
            # 找最近两个价格低点
            recent_close = close_series[-10:]
            recent_hist = hist_series[-10:]
            price_min_idx = recent_close.index(min(recent_close))
            # 前半段的价格低点
            first_half_close = recent_close[:price_min_idx]
            first_half_hist = recent_hist[:price_min_idx]
            if len(first_half_close) >= 3:
                prev_price_low = min(first_half_close)
                prev_hist_at_low = first_half_hist[first_half_close.index(prev_price_low)]
                curr_price_low = min(recent_close)
                curr_hist_at_low = recent_hist[price_min_idx]
                # 价格新低 + MACD柱未新低 + 当前柱在负值区
                if (curr_price_low < prev_price_low
                    and curr_hist_at_low > prev_hist_at_low
                    and curr_hist_at_low < 0):
                    macd_divergence = "bottom"

            # 顶背离：价格创新高但MACD柱未创新高
            recent_close_hi = close_series[-10:]
            recent_hist_hi = hist_series[-10:]
            price_max_idx = recent_close_hi.index(max(recent_close_hi))
            first_half_close_hi = recent_close_hi[:price_max_idx]
            first_half_hist_hi = recent_hist_hi[:price_max_idx]
            if len(first_half_close_hi) >= 3:
                prev_price_high = max(first_half_close_hi)
                prev_hist_at_high = first_half_hist_hi[first_half_close_hi.index(prev_price_high)]
                curr_price_high = max(recent_close_hi)
                curr_hist_at_high = recent_hist_hi[price_max_idx]
                # 价格新高 + MACD柱未新高 + 当前柱在正值区
                if (curr_price_high > prev_price_high
                    and curr_hist_at_high < prev_hist_at_high
                    and curr_hist_at_high > 0):
                    macd_divergence = "top"

        # ===== 功能2: 柱状图变化趋势 =====
        hist_trend = "neutral"  # neutral / green_shrinking / red_shrinking / green_to_red / red_to_green
        if len(hist_series) >= 4:
            last3 = hist_series[-3:]
            prev1 = hist_series[-2]
            prev2 = hist_series[-3]
            curr = hist_series[-1]
            # 绿柱（负值）连续3根缩短 → 空头衰竭
            if all(h < 0 for h in last3) and last3[0] < last3[1] < last3[2]:
                hist_trend = "green_shrinking"
            # 红柱（正值）连续3根缩短 → 多头衰竭
            elif all(h > 0 for h in last3) and last3[0] > last3[1] > last3[2]:
                hist_trend = "red_shrinking"
            # 绿转红（金叉）
            elif prev1 <= 0 and curr > 0:
                hist_trend = "red_to_green"
            # 红转绿（死叉）
            elif prev1 >= 0 and curr < 0:
                hist_trend = "green_to_red"

        # ===== 功能3: 金叉/死叉位置判断 =====
        cross_position = "none"  # none / above_zero_golden / below_zero_golden / above_zero_dead / below_zero_dead
        curr_macd_val = macd_series[-1]
        prev_macd_val = macd_series[-2] if len(macd_series) >= 2 else 0
        curr_signal_val = signal_series[-1]
        prev_signal_val = signal_series[-2] if len(signal_series) >= 2 else 0

        # 金叉：DIF从下方穿越DEA
        if prev_macd_val <= prev_signal_val and curr_macd_val > curr_signal_val:
            if curr_macd_val > 0:
                cross_position = "above_zero_golden"  # 零轴上方金叉
            else:
                cross_position = "below_zero_golden"  # 零轴下方金叉
        # 死叉：DIF从上方穿越DEA
        elif prev_macd_val >= prev_signal_val and curr_macd_val < curr_signal_val:
            if curr_macd_val > 0:
                cross_position = "above_zero_dead"  # 零轴上方死叉
            else:
                cross_position = "below_zero_dead"  # 零轴下方死叉

        trend = {
            "ema_fast": round(float(ema_fast.iloc[-1]), 4),
            "ema_slow": round(float(ema_slow.iloc[-1]), 4),
            "macd": round(float(macd["macd"].iloc[-1]), 4),
            "macd_signal": round(float(macd["signal"].iloc[-1]), 4),
            "macd_hist": round(float(macd["histogram"].iloc[-1]), 4),
            "ema_bullish": bool(ema_fast.iloc[-1] > ema_slow.iloc[-1]),
            "macd_bullish": bool(macd["macd"].iloc[-1] > macd["signal"].iloc[-1]),
            "macd_divergence": macd_divergence,
            "macd_hist_trend": hist_trend,
            "macd_cross_position": cross_position,
            "rsi": round(last_rsi, 2),
            "rsi_bottom_rebound": bool(rsi_bottom_rebound),
            "kdj_j": round(last_j, 2),
            "kdj_turn_bull": bool(kdj_turn_bull),
            "vwap": round(last_vwap, 4),
            "vwap_cross_up": bool(vwap_cross_up),
            "vwap_cross_down": bool(vwap_cross_down),
            "vwap_hold_above": bool(vwap_hold_above),
            "vwap_momentum_ready": bool(vwap_momentum_ready),
            "volume_ratio": round(volume_ratio, 2),
            "volume_expanding": bool(volume_ratio >= config.MSTR_VWAP_MIN_VOLUME_RATIO),
            "run_up_from_open": round(run_up_from_open, 4),
            "pullback_from_high": round(pullback_from_high, 4),
            "intraday_position": round(float(intraday_position), 4),
            "gap_too_big": bool(gap_too_big),
            "short_bull_top": round(float(short_top.iloc[-1]), 4),
            "short_bull_bottom": round(float(short_bottom.iloc[-1]), 4),
            "long_bull_top": round(float(long_top.iloc[-1]), 4),
            "long_bull_bottom": round(float(long_bottom.iloc[-1]), 4),
            "short_above_long": bool(short_above_long),
            "price_above_long_top": bool(price_above_long_top),
            "short_bottom_rising": bool(short_bottom_rising),
            "long_bottom_rising": bool(long_bottom_rising),
            "bull_structure_persistent": bool(persistent_structure),
            "bull_structure_weak": bool(bull_structure_weak),
            "bull_structure_strong": bool(bull_structure_strong),
            "morning_star": patterns["morning_star"],
            "evening_star": patterns["evening_star"],
            "inside_bar_breakout_up": patterns["inside_bar_breakout_up"],
            "inside_bar_breakout_down": patterns["inside_bar_breakout_down"],
            "bars": int(len(hist)),
            "interval": interval,
            "period": period,
        }
        _trend_cache[cache_key] = {"ts": now_ts, "data": trend}
        return trend
    except Exception as e:
        return {"error": str(e)}

def get_mstr_indicators() -> dict:
    """获取MSTR指标（底层正股）用于预判MSTU走势"""
    quote = get_yahoo_quote("MSTR")
    if "error" in quote:
        return {"error": "MSTR fetch failed"}
    
    # 计算MSTR的技术指标
    price = quote["price"]
    prev_close = quote["prev_close"]
    change_pct = (price - prev_close) / prev_close * 100 if prev_close > 0 else 0
    
    # MSTR涨跌2% → MSTU涨跌4%（2倍杠杆）
    mstu_expected_change = change_pct * 2
    trend_snapshot = get_yahoo_trend_snapshot("MSTR")

    result = {
        "mstr_price": price,
        "mstr_prev_close": prev_close,
        "mstr_open": quote.get("open", 0),
        "mstr_change_pct": round(change_pct, 2),
        "mstu_expected_change": round(mstu_expected_change, 2),
        "mstr_high": quote["high"],
        "mstr_low": quote["low"],
        "mstr_volume": quote["volume"],
        "signal": "bullish" if change_pct > 1 else ("bearish" if change_pct < -1 else "neutral")
    }
    if "error" not in trend_snapshot:
        result.update({
            "mstr_ema_fast": trend_snapshot["ema_fast"],
            "mstr_ema_slow": trend_snapshot["ema_slow"],
            "mstr_macd": trend_snapshot["macd"],
            "mstr_macd_signal": trend_snapshot["macd_signal"],
            "mstr_macd_hist": trend_snapshot["macd_hist"],
            "mstr_ema_bullish": trend_snapshot["ema_bullish"],
            "mstr_macd_bullish": trend_snapshot["macd_bullish"],
            "mstr_rsi": trend_snapshot["rsi"],
            "mstr_rsi_bottom_rebound": trend_snapshot["rsi_bottom_rebound"],
            "mstr_kdj_j": trend_snapshot["kdj_j"],
            "mstr_kdj_turn_bull": trend_snapshot["kdj_turn_bull"],
            "mstr_vwap": trend_snapshot["vwap"],
            "mstr_vwap_cross_up": trend_snapshot["vwap_cross_up"],
            "mstr_vwap_cross_down": trend_snapshot["vwap_cross_down"],
            "mstr_vwap_hold_above": trend_snapshot["vwap_hold_above"],
            "mstr_vwap_momentum_ready": trend_snapshot["vwap_momentum_ready"],
            "mstr_volume_ratio": trend_snapshot["volume_ratio"],
            "mstr_volume_expanding": trend_snapshot["volume_expanding"],
            "mstr_run_up_from_open": trend_snapshot["run_up_from_open"],
            "mstr_pullback_from_high": trend_snapshot["pullback_from_high"],
            "mstr_intraday_position": trend_snapshot["intraday_position"],
            "mstr_gap_too_big": trend_snapshot["gap_too_big"],
            "mstr_short_bull_top": trend_snapshot["short_bull_top"],
            "mstr_short_bull_bottom": trend_snapshot["short_bull_bottom"],
            "mstr_long_bull_top": trend_snapshot["long_bull_top"],
            "mstr_long_bull_bottom": trend_snapshot["long_bull_bottom"],
            "mstr_short_above_long": trend_snapshot["short_above_long"],
            "mstr_price_above_long_top": trend_snapshot["price_above_long_top"],
            "mstr_short_bottom_rising": trend_snapshot["short_bottom_rising"],
            "mstr_long_bottom_rising": trend_snapshot["long_bottom_rising"],
            "mstr_bull_structure_persistent": trend_snapshot["bull_structure_persistent"],
            "mstr_bull_structure_weak": trend_snapshot["bull_structure_weak"],
            "mstr_bull_structure_strong": trend_snapshot["bull_structure_strong"],
            "mstr_morning_star": trend_snapshot["morning_star"],
            "mstr_evening_star": trend_snapshot["evening_star"],
            "mstr_inside_bar_breakout_up": trend_snapshot["inside_bar_breakout_up"],
            "mstr_inside_bar_breakout_down": trend_snapshot["inside_bar_breakout_down"],
            "mstr_trend_interval": trend_snapshot["interval"],
            "mstr_macd_divergence": trend_snapshot.get("macd_divergence", "none"),
            "mstr_macd_hist_trend": trend_snapshot.get("macd_hist_trend", "neutral"),
            "mstr_macd_cross_position": trend_snapshot.get("macd_cross_position", "none"),
        })
    return result

def get_mstu_quote() -> dict:
    """获取 MSTU 实时行情 + MSTR 底层指标"""
    # 获取MSTU数据
    yahoo_quote = get_yahoo_quote(config.SYMBOL)
    
    if "error" not in yahoo_quote:
        yahoo_quote["session"] = get_session_type()
    else:
        # Yahoo 失败，fallback 到 Nasdaq
        quote = get_nasdaq_realtime(config.SYMBOL)
        if "error" in quote:
            return quote
        yahoo_quote = quote
        yahoo_quote["session"] = get_session_type()
    
    # 获取MSTR底层指标
    mstr_indicators = get_mstr_indicators()
    if "error" not in mstr_indicators:
        yahoo_quote["mstr"] = mstr_indicators
    
    return yahoo_quote

def format_price_info(quote: dict) -> str:
    """格式化行情信息"""
    if "error" in quote:
        return f"❌ 获取行情失败: {quote['error']}"
    
    session = quote.get("session", "unknown")
    session_label = {
        "premarket": "🌅 盘前",
        "regular": "📊 盘中",
        "overnight": "🌙 夜盘",
        "sleep": "😴 休息中",
        "closed": "🚫 休市"
    }.get(session, "❓")
    
    trading_day = quote.get("latest_trading_day", "")
    
    return f"""{session_label} **MSTU 行情**

💰 当前价格: ${quote['price']:.2f}
📊 交易日: {trading_day}
📈 日内: ${quote.get('low', 0):.2f} - ${quote.get('high', 0):.2f}
📉 昨收: ${quote['prev_close']:.2f} ({quote['change_pct']:+.2f}%)
📊 成交量: {quote.get('volume', 0):,}

🕐 {datetime.now(timezone.utc).strftime('%H:%M')} UTC"""

if __name__ == "__main__":
    print(f"当前时段: {get_session_type()}")
    quote = get_mstu_quote()
    print(format_price_info(quote))
