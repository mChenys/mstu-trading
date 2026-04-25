"""MSTU 技术指标计算模块"""

import pandas as pd
import numpy as np

def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """计算 RSI"""
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_bollinger_bands(series: pd.Series, period: int = 20, std_dev: float = 2.0) -> dict:
    """计算布林带"""
    middle = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper = middle + std_dev * std
    lower = middle - std_dev * std
    return {
        "upper": upper,
        "middle": middle,
        "lower": lower,
        "bandwidth": (upper - middle) / middle * 100
    }

def calculate_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    """计算 MACD"""
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    histogram = macd - signal_line
    return {
        "macd": macd,
        "signal": signal_line,
        "histogram": histogram
    }

def calculate_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """计算所有技术指标"""
    df = df.copy()
    
    # RSI
    df["rsi"] = calculate_rsi(df["close"])
    
    # 布林带
    bb = calculate_bollinger_bands(df["close"])
    df["bb_upper"] = bb["upper"]
    df["bb_middle"] = bb["middle"]
    df["bb_lower"] = bb["lower"]
    df["bb_width"] = bb["bandwidth"]
    
    # MACD
    macd = calculate_macd(df["close"])
    df["macd"] = macd["macd"]
    df["macd_signal"] = macd["signal"]
    df["macd_hist"] = macd["histogram"]
    
    # 价格位置
    df["price_to_bb_mid"] = (df["close"] - df["bb_middle"]) / df["bb_middle"] * 100
    
    return df

def get_signal_strength(row: pd.Series) -> dict:
    """评估信号强度"""
    signals = []
    
    # RSI 信号
    if pd.notna(row.get("rsi")):
        if row["rsi"] < 25:
            signals.append(("RSI严重超卖", 3))
        elif row["rsi"] < 30:
            signals.append(("RSI超卖", 2))
        elif row["rsi"] > 75:
            signals.append(("RSI严重超买", -3))
        elif row["rsi"] > 70:
            signals.append(("RSI超买", -2))
    
    # 布林带信号
    if pd.notna(row.get("close")) and pd.notna(row.get("bb_lower")):
        bb_position = (row["close"] - row["bb_lower"]) / (row["bb_upper"] - row["bb_lower"])
        if bb_position < 0.1:
            signals.append(("触及布林带下轨", 2))
        elif bb_position > 0.9:
            signals.append(("触及布林带上轨", -2))
    
    # MACD 信号
    if pd.notna(row.get("macd_hist")):
        prev_hist = row.get("prev_macd_hist", 0)
        if row["macd_hist"] > 0 and prev_hist <= 0:
            signals.append(("MACD金叉", 2))
        elif row["macd_hist"] < 0 and prev_hist >= 0:
            signals.append(("MACD死叉", -2))
    
    # 汇总
    buy_score = sum(s for _, s in signals if s > 0)
    sell_score = abs(sum(s for _, s in signals if s < 0))
    
    return {
        "signals": signals,
        "buy_score": buy_score,
        "sell_score": sell_score,
        "action": "BUY" if buy_score >= 3 else ("SELL" if sell_score >= 3 else "HOLD")
    }

if __name__ == "__main__":
    # 测试用
    import numpy as np
    test_data = pd.DataFrame({
        "close": np.random.uniform(7, 8, 100) + np.sin(np.linspace(0, 4*np.pi, 100)) * 0.5
    })
    df = calculate_all_indicators(test_data)
    print(df[["close", "rsi", "bb_upper", "bb_lower"]].tail())
    print(get_signal_strength(df.iloc[-1]))