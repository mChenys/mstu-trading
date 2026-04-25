"""MSTU 日内做T监控 - 主程序"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timezone
import config
from fetcher import get_mstu_quote, format_price_info
from strategy import TradingStrategy, format_trade_signal

def run_single_scan():
    """执行一次扫描"""
    print(f"\n{'='*50}")
    print(f"扫描时间: {datetime.now(timezone.utc).isoformat()}")
    
    # 获取行情
    quote = get_mstu_quote()
    print(format_price_info(quote))
    
    # 策略分析
    strategy = TradingStrategy()
    signal = strategy.analyze(quote)
    print(format_trade_signal(signal))
    return signal

def is_market_open() -> bool:
    """检查美股是否开盘"""
    now = datetime.now(timezone.utc)
    hour = now.hour
    weekday = now.weekday()
    if weekday >= 5:
        return False
    return 14 <= hour <= 21

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="只执行一次扫描")
    args = parser.parse_args()
    
    run_single_scan()