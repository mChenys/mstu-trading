"""MSTU 技术指标增强模块

集成 TA 库的指标，提升做T策略信号质量
"""

import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

# 尝试导入 ta 库
try:
    from ta.trend import SMAIndicator, EMAIndicator, MACD, ADXIndicator
    from ta.volatility import BollingerBands, AverageTrueRange
    from ta.momentum import RSIIndicator, StochasticOscillator
    from ta.volume import VolumeWeightedAveragePrice
    TA_AVAILABLE = True
except ImportError:
    TA_AVAILABLE = False


def calculate_vwap(high: float, low: float, close: float, volume: int, 
                   cumulative_volume: float = None, cumulative_vwap: float = None) -> dict:
    """
    计算 VWAP (Volume Weighted Average Price)
    日内重要参考价，价格在VWAP之上偏多，之下偏空
    
    Args:
        high, low, close: 当前K线价格
        volume: 当前成交量
        cumulative_volume: 累计成交量（可选，用于持续计算）
        cumulative_vwap: 累计VWAP值（可选）
    
    Returns:
        dict: vwap值, 价格相对位置, 信号
    """
    typical_price = (high + low + close) / 3
    
    if cumulative_volume is None or cumulative_vwap is None:
        # 首次计算
        vwap = typical_price
        cum_vol = volume
        cum_vwap = typical_price * volume
    else:
        # 持续累加
        cum_vol = cumulative_volume + volume
        cum_vwap = cumulative_vwap + typical_price * volume
        vwap = cum_vwap / cum_vol if cum_vol > 0 else typical_price
    
    # 价格相对VWAP位置
    position = (close - vwap) / vwap if vwap > 0 else 0
    
    signal = "neutral"
    if close > vwap * 1.005:  # 高于VWAP 0.5%
        signal = "bullish"
    elif close < vwap * 0.995:  # 低于VWAP 0.5%
        signal = "bearish"
    
    return {
        "vwap": round(vwap, 4),
        "position": round(position * 100, 2),  # 百分比
        "signal": signal,
        "cumulative_volume": cum_vol,
        "cumulative_vwap": cum_vwap
    }


def calculate_pivot_points(prev_high: float, prev_low: float, prev_close: float) -> dict:
    """
    计算 Pivot Points (枢轴点)
    日内交易的重要支撑/压力位
    
    经典计算方法：
    - Pivot = (High + Low + Close) / 3
    - R1 = 2*Pivot - Low
    - S1 = 2*Pivot - High
    - R2 = Pivot + (High - Low)
    - S2 = Pivot - (High - Low)
    """
    pivot = (prev_high + prev_low + prev_close) / 3
    
    r1 = 2 * pivot - prev_low
    s1 = 2 * pivot - prev_high
    r2 = pivot + (prev_high - prev_low)
    s2 = pivot - (prev_high - prev_low)
    r3 = prev_high + 2 * (pivot - prev_low)
    s3 = prev_low - 2 * (prev_high - pivot)
    
    return {
        "pivot": round(pivot, 2),
        "r1": round(r1, 2),  # 第一阻力
        "r2": round(r2, 2),  # 第二阻力
        "r3": round(r3, 2),  # 第三阻力
        "s1": round(s1, 2),  # 第一支撑
        "s2": round(s2, 2),  # 第二支撑
        "s3": round(s3, 2),  # 第三支撑
    }


def calculate_rsi(prices: list, period: int = 14) -> dict:
    """
    计算 RSI (Relative Strength Index)
    
    Args:
        prices: 收盘价列表（至少period+1个）
        period: RSI周期，默认14
    
    Returns:
        dict: rsi值, 超买超卖信号
    """
    if len(prices) < period + 1:
        return {"rsi": None, "signal": "insufficient_data"}
    
    if TA_AVAILABLE:
        try:
            df = pd.DataFrame({"close": prices})
            rsi_indicator = RSIIndicator(close=df["close"], window=period)
            rsi = rsi_indicator.rsi().iloc[-1]
        except:
            # 手动计算
            rsi = _manual_rsi(prices, period)
    else:
        rsi = _manual_rsi(prices, period)
    
    signal = "neutral"
    if rsi >= 70:
        signal = "overbought"  # 超买
    elif rsi <= 30:
        signal = "oversold"    # 超卖
    
    return {
        "rsi": round(rsi, 2) if rsi else None,
        "signal": signal
    }


def _manual_rsi(prices: list, period: int = 14) -> float:
    """手动计算RSI"""
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    
    if avg_loss == 0:
        return 100
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_bollinger_bands(prices: list, period: int = 20, std_dev: float = 2.0) -> dict:
    """
    计算布林带
    
    Args:
        prices: 收盘价列表
        period: 周期，默认20
        std_dev: 标准差倍数，默认2
    
    Returns:
        dict: 上轨、中轨、下轨、带宽、价格位置
    """
    if len(prices) < period:
        return {"error": "insufficient_data"}
    
    if TA_AVAILABLE:
        try:
            df = pd.DataFrame({"close": prices})
            bb = BollingerBands(close=df["close"], window=period, window_dev=std_dev)
            upper = bb.bollinger_hband().iloc[-1]
            middle = bb.bollinger_mavg().iloc[-1]
            lower = bb.bollinger_lband().iloc[-1]
        except:
            upper, middle, lower = _manual_bollinger(prices, period, std_dev)
    else:
        upper, middle, lower = _manual_bollinger(prices, period, std_dev)
    
    current_price = prices[-1]
    bandwidth = (upper - lower) / middle * 100 if middle > 0 else 0
    
    # 价格在布林带中的位置 (0-1)
    if upper != lower:
        position = (current_price - lower) / (upper - lower)
    else:
        position = 0.5
    
    signal = "neutral"
    if current_price >= upper:
        signal = "overbought"  # 突破上轨，可能回调
    elif current_price <= lower:
        signal = "oversold"    # 跌破下轨，可能反弹
    
    return {
        "upper": round(upper, 2),
        "middle": round(middle, 2),
        "lower": round(lower, 2),
        "bandwidth": round(bandwidth, 2),
        "position": round(position, 2),
        "signal": signal
    }


def _manual_bollinger(prices: list, period: int, std_dev: float) -> tuple:
    """手动计算布林带"""
    recent_prices = prices[-period:]
    middle = np.mean(recent_prices)
    std = np.std(recent_prices)
    upper = middle + std_dev * std
    lower = middle - std_dev * std
    return upper, middle, lower


def analyze_price_vs_levels(price: float, levels: dict) -> dict:
    """
    分析价格相对于关键水平的位置
    
    Args:
        price: 当前价格
        levels: 包含pivot, r1, s1等水平的字典
    
    Returns:
        dict: 最近的支撑/压力位，信号
    """
    pivot = levels.get("pivot", 0)
    r1 = levels.get("r1", 0)
    s1 = levels.get("s1", 0)
    r2 = levels.get("r2", 0)
    s2 = levels.get("s2", 0)
    
    signals = []
    
    # 检查是否接近支撑位
    if s1 > 0 and abs(price - s1) / s1 < 0.01:  # 1%以内
        signals.append({"level": "S1", "value": s1, "type": "support", "distance_pct": round((price - s1) / s1 * 100, 2)})
    if s2 > 0 and abs(price - s2) / s2 < 0.01:
        signals.append({"level": "S2", "value": s2, "type": "support", "distance_pct": round((price - s2) / s2 * 100, 2)})
    
    # 检查是否接近阻力位
    if r1 > 0 and abs(price - r1) / r1 < 0.01:
        signals.append({"level": "R1", "value": r1, "type": "resistance", "distance_pct": round((price - r1) / r1 * 100, 2)})
    if r2 > 0 and abs(price - r2) / r2 < 0.01:
        signals.append({"level": "R2", "value": r2, "type": "resistance", "distance_pct": round((price - r2) / r2 * 100, 2)})
    
    # 确定价格区间
    zone = "neutral"
    if price > r1:
        zone = "strong_bullish"
    elif price > pivot:
        zone = "bullish"
    elif price < s1:
        zone = "strong_bearish"
    elif price < pivot:
        zone = "bearish"
    
    return {
        "signals": signals,
        "zone": zone,
        "pivot": pivot,
        "nearest_support": s1 if price > pivot else s2,
        "nearest_resistance": r1 if price < pivot else r2
    }


def generate_enhanced_signals(quote: dict, history: list = None) -> dict:
    """
    生成增强的技术分析信号
    
    Args:
        quote: 当前行情 (包含 price, high, low, prev_close, volume 等)
        history: 历史价格列表 (可选，用于计算RSI/布林带)
    
    Returns:
        dict: 综合技术信号
    """
    price = quote.get("price", 0)
    high = quote.get("high", price)
    low = quote.get("low", price)
    prev_close = quote.get("prev_close", 0)
    volume = quote.get("volume", 0)
    
    signals = []
    score = {"buy": 0, "sell": 0}
    
    # 1. Pivot Points 分析
    if prev_close > 0 and high > 0 and low > 0:
        # 用昨日的high/low/close计算今日pivot
        pivots = calculate_pivot_points(high, low, prev_close)
        pivot_analysis = analyze_price_vs_levels(price, pivots)
        
        if pivot_analysis["signals"]:
            for sig in pivot_analysis["signals"]:
                if sig["type"] == "support":
                    signals.append(f"🎯 接近{sig['level']}支撑(${sig['value']:.2f})")
                    score["buy"] += 1
                else:
                    signals.append(f"🎯 接近{sig['level']}阻力(${sig['value']:.2f})")
                    score["sell"] += 1
        
        # 价格区间信号
        zone = pivot_analysis["zone"]
        if zone == "strong_bullish":
            signals.append("📈 突破R1，强势看多")
            score["buy"] += 1
        elif zone == "strong_bearish":
            signals.append("📉 跌破S1，强势看空")
            score["sell"] += 1
    
    # 2. RSI 分析
    if history and len(history) >= 15:
        rsi_result = calculate_rsi(history, period=14)
        rsi = rsi_result.get("rsi")
        
        if rsi:
            if rsi_result["signal"] == "oversold":
                signals.append(f"💚 RSI超卖({rsi:.0f})，可能反弹")
                score["buy"] += 2
            elif rsi_result["signal"] == "overbought":
                signals.append(f"💗 RSI超买({rsi:.0f})，注意回调")
                score["sell"] += 2
            elif rsi < 40:
                score["buy"] += 0.5
            elif rsi > 60:
                score["sell"] += 0.5
    
    # 3. 布林带分析
    if history and len(history) >= 20:
        bb_result = calculate_bollinger_bands(history, period=20)
        
        if "error" not in bb_result:
            bb_signal = bb_result.get("signal", "")
            position = bb_result.get("position", 0.5)
            
            if bb_signal == "oversold":
                signals.append(f"📊 触及布林下轨，可能反弹")
                score["buy"] += 1.5
            elif bb_signal == "overbought":
                signals.append(f"📊 突破布林上轨，注意回调")
                score["sell"] += 1.5
            elif position < 0.2:
                signals.append(f"📊 布林带低位区")
                score["buy"] += 0.5
            elif position > 0.8:
                signals.append(f"📊 布林带高位区")
                score["sell"] += 0.5
    
    # 4. VWAP 分析（需要盘中累计数据，这里简化处理）
    if volume > 0:
        vwap_result = calculate_vwap(high, low, price, volume)
        vwap_signal = vwap_result.get("signal", "neutral")
        vwap_position = vwap_result.get("position", 0)
        
        if vwap_signal == "bullish":
            signals.append(f"📊 价格高于VWAP，偏多")
            score["buy"] += 0.5
        elif vwap_signal == "bearish":
            signals.append(f"📊 价格低于VWAP，偏空")
            score["sell"] += 0.5
    
    return {
        "signals": signals,
        "buy_score": round(score["buy"], 1),
        "sell_score": round(score["sell"], 1),
        "pivot_levels": pivots if prev_close > 0 else None,
        "rsi": rsi_result if history and len(history) >= 15 else None,
        "bollinger": bb_result if history and len(history) >= 20 else None
    }


if __name__ == "__main__":
    # 测试
    test_prices = [7.20, 7.25, 7.18, 7.30, 7.35, 7.28, 7.40, 7.45, 7.38, 7.50,
                   7.55, 7.48, 7.60, 7.52, 7.58, 7.65, 7.70, 7.62, 7.55, 7.48]
    
    print("=== RSI ===")
    rsi = calculate_rsi(test_prices)
    print(f"RSI: {rsi['rsi']}, Signal: {rsi['signal']}")
    
    print("\n=== Bollinger Bands ===")
    bb = calculate_bollinger_bands(test_prices)
    print(f"Upper: {bb['upper']}, Middle: {bb['middle']}, Lower: {bb['lower']}")
    print(f"Position: {bb['position']}, Signal: {bb['signal']}")
    
    print("\n=== Pivot Points ===")
    pivots = calculate_pivot_points(7.70, 7.18, 7.48)
    print(f"Pivot: {pivots['pivot']}, R1: {pivots['r1']}, S1: {pivots['s1']}")
    
    print("\n=== 综合信号 ===")
    quote = {"price": 7.55, "high": 7.70, "low": 7.48, "prev_close": 7.48, "volume": 50000000}
    result = generate_enhanced_signals(quote, test_prices)
    print(f"Signals: {result['signals']}")
    print(f"Buy Score: {result['buy_score']}, Sell Score: {result['sell_score']}")
