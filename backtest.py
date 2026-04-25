#!/usr/bin/env python3
"""MSTU 做T策略回测 - Backtrader 框架

回测层的关键设计和实时策略保持一致：
1. MSTR 作为信号源，用来计算缺口、趋势、RSI/MACD/均线等指标。
2. MSTU 作为执行标的，用来计算实际买价、卖价、仓位和回撤。
3. 因为用户实际持仓是 MSTU，所以回测收益必须以 MSTU 成交结果为准。

给接手的 OpenClaw Agent：
- 如果只改信号阈值，优先看 CombinedStrategy.params。
- 如果改双标逻辑，务必保持 data0=MSTU、data1=MSTR 的约定不变。
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import backtrader as bt
import datetime
import json
import pandas as pd
import numpy as np
import config
from fee_model import BUY, SELL, estimate_fees, max_affordable_shares

# ===== 数据获取 =====
def build_intraday_limit_hint(interval="15m", period="60d") -> str:
    """构建 Yahoo 分钟级历史限制提示。"""
    minute_intervals = {"1m", "2m", "5m", "15m", "30m", "60m", "90m"}
    if interval not in minute_intervals:
        return "如果下载失败，请检查标的代码、网络连接或数据源可用性。"
    return (
        f"Yahoo 的 {interval} 分钟级历史数据通常只能覆盖最近约 60 天。"
        f" 当前请求 period={period} 若超过该窗口，建议改用 60d、提高K线周期，或切换数据源。"
    )


def download_symbol_data(symbol, interval="15m", period="60d"):
    """下载单个标的历史数据。"""
    import yfinance as yf
    
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, interval=interval)
    
    if df.empty:
        print("❌ 无法获取MSTU数据，尝试用缓存...")
        print(f"   {build_intraday_limit_hint(interval=interval, period=period)}")
        return None
    
    # 保存CSV
    csv_path = os.path.join(os.path.dirname(__file__), f"{symbol.lower()}_history.csv")
    df.to_csv(csv_path)
    print(f"✅ {symbol}数据已保存: {csv_path}")
    print(f"   数据范围: {df.index[0].strftime('%Y-%m-%d')} ~ {df.index[-1].strftime('%Y-%m-%d')}")
    print(f"   周期: {interval} | 共 {len(df)} 条K线")
    return csv_path


def download_mstu_data(interval="15m", period="60d"):
    """兼容旧入口：下载 MSTU 数据。"""
    return download_symbol_data("MSTU", interval=interval, period=period)


def download_market_data(interval="15m", period="60d"):
    """下载回测所需的 MSTU/MSTR 双标的数据。

    约定：
    - MSTU: execution feed
    - MSTR: signal feed
    - BTC: daily tone feed
    """
    return {
        "mstu": download_symbol_data("MSTU", interval=interval, period=period),
        "mstr": download_symbol_data("MSTR", interval=interval, period=period),
        "btc": download_symbol_data(config.BTC_SYMBOL, interval=interval, period=period),
    }


def evaluate_daily_tone_snapshot(
    *,
    mstr_change_pct: float,
    mstr_ema_bullish: bool,
    mstr_macd_bullish: bool,
    mstr_bull_structure_weak: bool,
    btc_change_pct: float,
    btc_ema_bullish: bool,
    btc_price_above_fast: bool,
    bullish_forward_bias: float = config.DAILY_TONE_BULLISH_FORWARD_BIAS,
    bearish_reverse_bias: float = config.DAILY_TONE_BEARISH_REVERSE_BIAS,
) -> dict:
    """用回测快照计算 daily tone。

    返回值与实时 fetcher.calculate_daily_tone 的核心字段保持一致，
    但输入全部来自回测中的历史 bar，避免依赖实时接口。
    """
    tone = "neutral"
    forward_bias = 0.0
    reverse_bias = 0.0
    reason_parts = []

    btc_trend = "neutral"
    if btc_ema_bullish and btc_price_above_fast and btc_change_pct > 0:
        btc_trend = "bullish"
    elif (not btc_ema_bullish) and (not btc_price_above_fast) and btc_change_pct < 0:
        btc_trend = "bearish"

    if btc_trend == "bullish" and btc_change_pct > 1.0:
        tone = "bullish"
        reason_parts.append(f"BTC涨{btc_change_pct:+.1f}%多头结构")
        if btc_change_pct > 2.0:
            tone = "bullish_strong"
            reason_parts.append("(强)")
    elif btc_trend == "bearish" and btc_change_pct < -1.0:
        tone = "bearish"
        reason_parts.append(f"BTC跌{btc_change_pct:+.1f}%空头结构")
        if btc_change_pct < -2.0:
            tone = "bearish_strong"
            reason_parts.append("(强)")

    if tone in ["neutral", "bullish"] and mstr_change_pct > 1.5 and mstr_bull_structure_weak:
        tone = "bullish_strong" if tone == "bullish" else "bullish"
        reason_parts.append(f"MSTR高开{mstr_change_pct:+.1f}%")
    elif tone in ["neutral", "bearish"] and mstr_change_pct < -1.5 and not mstr_bull_structure_weak:
        tone = "bearish_strong" if tone == "bearish" else "bearish"
        reason_parts.append(f"MSTR低开{mstr_change_pct:+.1f}%")

    if tone == "neutral" and mstr_ema_bullish and mstr_macd_bullish and btc_ema_bullish:
        tone = "bullish"
        reason_parts.append("MSTR+BTC均线共振多头")
    elif tone == "neutral" and (not mstr_ema_bullish) and (not mstr_macd_bullish) and (not btc_ema_bullish):
        tone = "bearish"
        reason_parts.append("MSTR+BTC均线共振空头")

    if tone in ["bullish", "bullish_strong"]:
        forward_bias = bullish_forward_bias
        reverse_bias = -0.25
        if tone == "bullish_strong":
            forward_bias += 0.25
    elif tone in ["bearish", "bearish_strong"]:
        reverse_bias = bearish_reverse_bias
        forward_bias = -0.25
        if tone == "bearish_strong":
            reverse_bias += 0.25

    return {
        "tone": tone,
        "forward_bias": round(forward_bias, 2),
        "reverse_bias": round(reverse_bias, 2),
        "reason": " | ".join(reason_parts) if reason_parts else "无明显方向信号",
    }


class IntradayGapStrategy(bt.Strategy):
    """为开盘缺口型策略提供按交易日切分的日内状态。"""

    params = (
        ('entry_bars', 4),
    )

    def init_session_state(self):
        self.signal_data = getattr(self, "signal_data", self.datas[0])
        self.session_date = None
        self.prev_day_close = None
        self.day_open = None
        self.session_high = None
        self.session_low = None
        self.bars_today = 0
        self.last_bar_close = None
        self.trade_opened_today = False

    def update_session_state(self):
        current_dt = self.signal_data.datetime.datetime(0)
        current_date = current_dt.date()

        if self.session_date != current_date:
            self.prev_day_close = self.last_bar_close
            self.session_date = current_date
            self.day_open = float(self.signal_data.open[0])
            self.session_high = float(self.signal_data.high[0])
            self.session_low = float(self.signal_data.low[0])
            self.bars_today = 0
            self.trade_opened_today = False
        else:
            self.session_high = max(self.session_high, float(self.signal_data.high[0]))
            self.session_low = min(self.session_low, float(self.signal_data.low[0]))

        self.bars_today += 1
        self.last_bar_close = float(self.signal_data.close[0])

    def can_enter_today(self):
        return (
            self.prev_day_close is not None
            and self.bars_today <= self.params.entry_bars
            and not self.trade_opened_today
        )

    def current_gap_pct(self):
        if not self.prev_day_close:
            return None
        return (self.day_open - self.prev_day_close) / self.prev_day_close


class SessionVWAP(bt.Indicator):
    """按交易日重置的日内 VWAP。"""

    lines = ("vwap",)

    def __init__(self):
        self._session_date = None
        self._cum_value = 0.0
        self._cum_volume = 0.0

    def next(self):
        current_dt = self.data.datetime.datetime(0)
        current_date = current_dt.date()
        if self._session_date != current_date:
            self._session_date = current_date
            self._cum_value = 0.0
            self._cum_volume = 0.0

        typical_price = (self.data.high[0] + self.data.low[0] + self.data.close[0]) / 3
        bar_volume = max(float(self.data.volume[0]), 0.0)
        self._cum_value += typical_price * bar_volume
        self._cum_volume += bar_volume
        self.lines.vwap[0] = (
            self._cum_value / self._cum_volume if self._cum_volume > 0 else self.data.close[0]
        )


class CandlePatternFlags(bt.Indicator):
    """将 moomoo 的关键三根 K 线形态翻译成回测里的布尔标记。"""

    lines = ("morning_star", "evening_star", "inside_bar_breakout_up", "inside_bar_breakout_down")

    def next(self):
        if len(self.data) < 6:
            self.lines.morning_star[0] = 0
            self.lines.evening_star[0] = 0
            self.lines.inside_bar_breakout_up[0] = 0
            self.lines.inside_bar_breakout_down[0] = 0
            return

        first_open = float(self.data.open[-2])
        first_close = float(self.data.close[-2])
        second_open = float(self.data.open[-1])
        second_close = float(self.data.close[-1])
        third_open = float(self.data.open[0])
        third_close = float(self.data.close[0])

        ma_now = sum(float(self.data.close[-i]) for i in range(5)) / 5
        ma_prev = sum(float(self.data.close[-i - 1]) for i in range(5)) / 5
        trend_up = ma_now > ma_prev
        trend_down = ma_now < ma_prev
        second_body_ratio = abs(second_open - second_close) / second_close if second_close else 0.0

        morning_star = (
            first_close / first_open < 0.95
            and second_open < first_close
            and second_body_ratio < 0.03
            and third_close / third_open > 1.05
            and third_close > first_close
            and trend_down
        )
        evening_star = (
            first_close / first_open > 1.03
            and second_open > first_close
            and second_body_ratio < 0.02
            and third_close / third_open < 0.97
            and third_close < first_close
            and trend_up
        )

        mother_high = float(self.data.high[-3])
        mother_low = float(self.data.low[-3])
        mother_open = float(self.data.open[-3])
        mother_close = float(self.data.close[-3])
        mother_range = mother_high - mother_low
        mother_body = abs(mother_close - mother_open)
        strong_mother = mother_range > 0 and (mother_body / mother_range > 0.7)
        child_inside = float(self.data.high[-2]) < mother_high and float(self.data.low[-2]) > mother_low
        uptrend_before = float(self.data.close[-3]) > float(self.data.close[-4])
        downtrend_before = float(self.data.close[-3]) < float(self.data.close[-4])
        breakout_up = float(self.data.close[-1]) > mother_high
        breakout_down = float(self.data.close[-1]) < mother_low

        self.lines.morning_star[0] = 1 if morning_star else 0
        self.lines.evening_star[0] = 1 if evening_star else 0
        self.lines.inside_bar_breakout_up[0] = 1 if (child_inside and strong_mother and downtrend_before and breakout_up) else 0
        self.lines.inside_bar_breakout_down[0] = 1 if (child_inside and strong_mother and uptrend_before and breakout_down) else 0


# ===== 策略1: 低吸做T =====
class DipBuyStrategy(IntradayGapStrategy):
    """低吸做T策略 - 低开买入，冲高卖出"""
    
    params = (
        ('gap_down_pct', -0.04),      # 低开4%才考虑低吸
        ('take_profit_pct', 0.02),    # 止盈2.0%
        ('stop_loss_pct', 0.018),     # 止损1.8%
        ('trade_amount', 400),        # 单次买入金额
        ('printlog', True),
    )
    
    def __init__(self):
        self.signal_data = self.datas[0]
        self.init_session_state()
        self.order = None
        self.buy_price = None
        self.target_price = None
        self.stop_price = None
        self.holding_shares = 0
        self.trade_count = 0
        self.win_count = 0
        self.loss_count = 0
        self.total_pnl = 0
        
        # RSI
        self.rsi = bt.ind.RSI(period=14)
        # 布林带
        self.boll = bt.ind.BollingerBands(period=20, devfactor=2.0)
        # MACD
        self.macd = bt.ind.MACD()
    
    def log(self, txt, dt=None):
        if self.params.printlog:
            dt = dt or self.datas[0].datetime.date(0)
            print(f'[{dt.isoformat()}] {txt}')
    
    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        
        if order.status in [order.Completed]:
            if order.isbuy():
                self.buy_price = order.executed.price
                self.holding_shares = int(order.executed.size)
                self.target_price = self.buy_price * (1 + self.params.take_profit_pct)
                self.stop_price = self.buy_price * (1 - self.params.stop_loss_pct)
                self.log(f'买入执行: {self.holding_shares}股 @ ${self.buy_price:.2f}, 目标${self.target_price:.2f}, 止损${self.stop_price:.2f}')
            elif order.issell():
                sell_price = order.executed.price
                pnl = (sell_price - self.buy_price) * self.holding_shares if self.buy_price else 0
                self.total_pnl += pnl
                self.trade_count += 1
                if pnl > 0:
                    self.win_count += 1
                else:
                    self.loss_count += 1
                self.log(f'卖出执行: {self.holding_shares}股 @ ${sell_price:.2f}, 盈亏${pnl:+.2f}')
                self.holding_shares = 0
                self.buy_price = None
                self.target_price = None
                self.stop_price = None
        
        self.order = None
    
    def next(self):
        # 有未完成订单则跳过
        if self.order:
            return

        self.update_session_state()
        
        current_price = self.data.close[0]
        
        # 如果有持仓，检查卖出条件
        if self.holding_shares > 0:
            # 止盈
            if current_price >= self.target_price:
                self.log(f'🎯 止盈: 当前${current_price:.2f} >= 目标${self.target_price:.2f}')
                self.order = self.sell(size=self.holding_shares)
                return
            # 止损
            if current_price <= self.stop_price:
                self.log(f'⛔ 止损: 当前${current_price:.2f} <= 止损${self.stop_price:.2f}')
                self.order = self.sell(size=self.holding_shares)
                return
            # 收盘前卖出（日内做T）
            # 简化：如果盈利>0.5%也考虑卖出
            if current_price > self.buy_price * 1.005:
                self.log(f'📊 浮盈卖出: 当前${current_price:.2f}, 买入${self.buy_price:.2f} (+{(current_price/self.buy_price-1)*100:.1f}%)')
                self.order = self.sell(size=self.holding_shares)
                return
            return
        
        # 无持仓，检查买入条件
        if self.can_enter_today():
            gap_pct = self.current_gap_pct()
            
            # 低开买入
            if gap_pct is not None and gap_pct <= self.params.gap_down_pct:
                # 收紧低吸：必须是更强的超卖，而不是单纯低开接飞刀
                rsi_oversold = self.rsi[0] < 30 if not np.isnan(self.rsi[0]) else False
                bb_lower = current_price <= self.boll.lines.bot[0] if not np.isnan(self.boll.lines.bot[0]) else False
                deep_gap = gap_pct <= self.params.gap_down_pct * 1.25
                
                if (rsi_oversold and bb_lower) or deep_gap:
                    buy_shares = int(self.params.trade_amount / current_price)
                    if buy_shares > 0:
                        self.trade_opened_today = True
                        self.log(f'🟢 低吸买入: 低开{gap_pct*100:+.1f}%, RSI超卖={rsi_oversold}, 触及布林下轨={bb_lower}')
                        self.order = self.buy(size=buy_shares)
    
    def stop(self):
        win_rate = self.win_count / self.trade_count * 100 if self.trade_count > 0 else 0
        print(f'\n{"="*50}')
        print(f'📊 低吸做T策略回测结果')
        print(f'{"="*50}')
        print(f'总交易次数: {self.trade_count}')
        print(f'盈利次数: {self.win_count}')
        print(f'亏损次数: {self.loss_count}')
        print(f'胜率: {win_rate:.1f}%')
        print(f'总盈亏: ${self.total_pnl:+.2f}')
        if self.trade_count > 0:
            print(f'平均每笔: ${self.total_pnl/self.trade_count:+.2f}')
        print(f'{"="*50}')


# ===== 策略2: 追涨做T =====
class MomentumStrategy(IntradayGapStrategy):
    """追涨做T策略 - 高开追涨，快止盈"""
    
    params = (
        ('gap_up_pct', 0.012),         # 高开1.2%追涨
        ('take_profit_pct', 0.018),    # 止盈1.8%
        ('stop_loss_pct', 0.01),       # 止损1.0%
        ('max_chase_pct', 0.035),      # 涨幅超3.5%不追
        ('trade_amount', 600),         # 单次买入金额
        ('printlog', True),
    )
    
    def __init__(self):
        self.signal_data = self.datas[0]
        self.init_session_state()
        self.order = None
        self.buy_price = None
        self.target_price = None
        self.stop_price = None
        self.holding_shares = 0
        self.trade_count = 0
        self.win_count = 0
        self.loss_count = 0
        self.total_pnl = 0
        
        self.rsi = bt.ind.RSI(period=14)
        self.macd = bt.ind.MACD()
        self.ema9 = bt.ind.EMA(period=9)
        self.ema21 = bt.ind.EMA(period=21)
    
    def log(self, txt, dt=None):
        if self.params.printlog:
            dt = dt or self.datas[0].datetime.date(0)
            print(f'[{dt.isoformat()}] {txt}')
    
    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        
        if order.status in [order.Completed]:
            if order.isbuy():
                self.buy_price = order.executed.price
                self.holding_shares = int(order.executed.size)
                self.target_price = self.buy_price * (1 + self.params.take_profit_pct)
                self.stop_price = self.buy_price * (1 - self.params.stop_loss_pct)
                self.log(f'买入执行: {self.holding_shares}股 @ ${self.buy_price:.2f}')
            elif order.issell():
                sell_price = order.executed.price
                pnl = (sell_price - self.buy_price) * self.holding_shares if self.buy_price else 0
                self.total_pnl += pnl
                self.trade_count += 1
                if pnl > 0:
                    self.win_count += 1
                else:
                    self.loss_count += 1
                self.log(f'卖出执行: @ ${sell_price:.2f}, 盈亏${pnl:+.2f}')
                self.holding_shares = 0
                self.buy_price = None
        
        self.order = None
    
    def next(self):
        if self.order:
            return

        self.update_session_state()
        
        current_price = self.data.close[0]
        
        # 有持仓，卖出检查
        if self.holding_shares > 0:
            if current_price >= self.target_price:
                self.order = self.sell(size=self.holding_shares)
                return
            if current_price <= self.stop_price:
                self.order = self.sell(size=self.holding_shares)
                return
            # 追涨快出：盈利>0.8%就出
            if current_price > self.buy_price * 1.008:
                self.order = self.sell(size=self.holding_shares)
                return
            return
        
        # 买入检查
        if self.can_enter_today():
            gap_pct = self.current_gap_pct()
            
            # 高开追涨
            if gap_pct is not None and self.params.gap_up_pct <= gap_pct <= self.params.max_chase_pct:
                # 收紧追涨：EMA 与 MACD 同时确认
                ema_bullish = self.ema9[0] > self.ema21[0] if not np.isnan(self.ema21[0]) else True
                macd_bullish = self.macd.lines.macd[0] > self.macd.lines.signal[0] if not np.isnan(self.macd.lines.signal[0]) else True
                
                if ema_bullish and macd_bullish:
                    buy_shares = int(self.params.trade_amount / current_price)
                    if buy_shares > 0:
                        self.trade_opened_today = True
                        self.log(f'📈 追涨买入: 高开{gap_pct*100:+.1f}%, EMA多头={ema_bullish}, MACD多头={macd_bullish}')
                        self.order = self.buy(size=buy_shares)
    
    def stop(self):
        win_rate = self.win_count / self.trade_count * 100 if self.trade_count > 0 else 0
        print(f'\n{"="*50}')
        print(f'📊 追涨做T策略回测结果')
        print(f'{"="*50}')
        print(f'总交易次数: {self.trade_count}')
        print(f'盈利次数: {self.win_count}')
        print(f'亏损次数: {self.loss_count}')
        print(f'胜率: {win_rate:.1f}%')
        print(f'总盈亏: ${self.total_pnl:+.2f}')
        if self.trade_count > 0:
            print(f'平均每笔: ${self.total_pnl/self.trade_count:+.2f}')
        print(f'{"="*50}')


# ===== 策略3: 组合策略（低吸+追涨）=====
class CombinedStrategy(IntradayGapStrategy):
    """组合策略 - 底仓 + T仓 + 正向/反向做T。

    数据约定：
    - self.data / data0: MSTU，真实执行价格
    - self.signal_data / data1: MSTR，技术指标和方向判断

    设计目标：
    - base_position: 用户长期底仓，不在回测里当作普通策略仓位频繁清空
    - t_long_shares: 额外买入的正向T仓，低买高卖
    - reverse_t_shares: 从已有底仓里先卖后买回的反向T仓，不代表做空，只代表高抛后回补
    """
    
    params = (
        ('gap_down_pct', -0.04),
        ('gap_up_pct', 0.012),
        ('max_chase_pct', 0.04),
        ('dip_profit_pct', 0.02),
        ('dip_stop_pct', 0.018),
        ('mom_profit_pct', 0.018),
        ('mom_stop_pct', 0.01),
        ('trade_amount', 250),
        ('mom_trade_amount', 750),
        # 追涨腿保留“高开顺势”入口，同时新增“盘中放量启动”入口，
        # 避免整个 momentum 只剩开盘缺口一种场景。
        ('momentum_runup_min', 0.012),
        ('momentum_intraday_position_min', 0.55),
        ('momentum_pullback_max', 0.012),
        # 高命中信号阈值：优先调这些，而不是继续堆低频形态。
        ('downtrend_adx_threshold', 25),
        ('vwap_volume_ratio_min', 1.2),
        ('rsi_rebound_prev_max', 22),
        ('rsi_rebound_now_min', 20),
        ('kdj_turn_level', 30),
        ('bull_structure_confirm_bars', 3),
        ('base_position', 3000),
        # 反向T默认更轻仓，避免“高抛动作太多”把整套做T拖成过度交易。
        ('reverse_trade_amount', 200),
        ('reverse_profit_pct', 0.015),
        ('reverse_stop_pct', 0.012),
        # 反向T必须先出现 VWAP 下破，再叠加顶部转弱信号，避免只因位置偏高就过早卖出。
        # 这里默认用“轻量反向T”参数：先有明显拉升，再从高位有一定回落，才允许减底仓。
        ('reverse_trigger_threshold', 2.25),
        ('reverse_runup_min', 0.04),
        ('reverse_pullback_min', 0.012),
        ('enable_macd_enhanced', True),
        ('enable_btc_tone', True),
        ('print_summary', True),
        ('printlog', False),
    )
    
    def __init__(self):
        # 双标回测时，第二路数据固定视为信号源 MSTR；
        # 如果只传一路数据，则退化为单标模式，方便兼容旧脚本。
        self.signal_data = self.datas[1] if len(self.datas) > 1 else self.datas[0]
        self.btc_data = self.datas[2] if len(self.datas) > 2 else None
        self.init_session_state()
        self.order = None
        self.buy_price = None
        self.target_price = None
        self.stop_price = None
        self.holding_shares = 0
        self.position_type = ""  # dip / momentum
        self.initial_t_cash = None
        self.t_cash = None
        self.t_long_shares = 0
        self.t_long_entry_price = 0.0
        self.t_long_cost_basis = 0.0
        self.t_long_entry_date = None
        self.t_long_type = ""
        self.reverse_t_shares = 0
        self.reverse_sell_price = 0.0
        self.reverse_sale_net_proceeds = 0.0
        self.reverse_entry_date = None
        self.trade_count = 0
        self.win_count = 0
        self.loss_count = 0
        self.total_pnl = 0
        self.dip_trades = 0
        self.dip_wins = 0
        self.mom_trades = 0
        self.mom_wins = 0
        self.forward_t_count = 0
        self.reverse_t_count = 0
        self.cross_session_t_count = 0
        self.forward_t_wins = 0
        self.reverse_t_wins = 0
        self.current_value = 0.0
        self.peak_value = 0.0
        self.max_drawdown_pct = 0.0
        self.daily_tone = "neutral"
        self.tone_forward_bias = 0.0
        self.tone_reverse_bias = 0.0
        self.tone_reason = ""
        self._tone_session_date = None
        self.tone_hits = {
            "bullish_strong": 0,
            "bullish": 0,
            "neutral": 0,
            "bearish": 0,
            "bearish_strong": 0,
        }
        self.signal_hits = {
            "morning_star": 0,
            "evening_star": 0,
            "inside_bar_breakout_up": 0,
            "inside_bar_breakout_down": 0,
            "rsi_rebound": 0,
            "kdj_turn_bull": 0,
            "vwap_cross_up": 0,
            "bull_structure_weak": 0,
            "bull_structure_strong": 0,
            # MACD 增强信号
            "macd_bottom_divergence": 0,
            "macd_top_divergence": 0,
            "macd_green_shrinking": 0,
            "macd_red_shrinking": 0,
            "macd_red_to_green": 0,
            "macd_green_to_red": 0,
            "macd_above_zero_golden": 0,
            "macd_below_zero_golden": 0,
            "macd_above_zero_dead": 0,
            "macd_below_zero_dead": 0,
        }
        # MACD 历史数据缓存（用于计算背离和趋势）
        self._macd_hist_history = []
        self._macd_history = []
        self._signal_history = []
        self._close_history = []
        
        # 技术指标全部建在 signal_data 上，避免直接用杠杆 ETF(MSTU) 做主信号。
        self.rsi = bt.ind.RSI(self.signal_data.close, period=14)
        self.boll = bt.ind.BollingerBands(self.signal_data.close, period=20, devfactor=2.0)
        self.macd = bt.ind.MACD(self.signal_data.close)
        self.ema9 = bt.ind.EMA(self.signal_data.close, period=9)
        self.ema21 = bt.ind.EMA(self.signal_data.close, period=21)
        # MACD 柱状图 = (DIF - DEA) * 2
        self.macd_hist = self.macd.macd - self.macd.signal
        self.sma50 = bt.ind.SMA(self.signal_data.close, period=50)
        self.short_bull_top = bt.ind.EMA(self.signal_data.high, period=24)
        self.short_bull_bottom = bt.ind.EMA(self.signal_data.low, period=23)
        self.long_bull_top = bt.ind.EMA(self.signal_data.high, period=89)
        self.long_bull_bottom = bt.ind.EMA(self.signal_data.low, period=90)
        self.vwap = SessionVWAP(self.signal_data)
        self.patterns = CandlePatternFlags(self.signal_data)
        self.volume_sma = bt.ind.SMA(self.signal_data.volume, period=5)
        self.atr = bt.ind.ATR(self.signal_data, period=14)
        # ADX - 趋势强度
        self.adx = bt.ind.ADX(self.signal_data, period=14)
        self.k = bt.ind.Stochastic(self.signal_data).percK
        self.d = bt.ind.Stochastic(self.signal_data).percD
        if self.btc_data is not None:
            self.btc_ema_fast = bt.ind.EMA(self.btc_data.close, period=config.BTC_EMA_FAST_PERIOD)
            self.btc_ema_slow = bt.ind.EMA(self.btc_data.close, period=config.BTC_EMA_SLOW_PERIOD)
        else:
            self.btc_ema_fast = None
            self.btc_ema_slow = None

    def start(self):
        # 只把可动用现金作为 T 仓回测本金，底仓收益不计入策略收益。
        self.initial_t_cash = float(self.broker.getcash())
        self.t_cash = float(self.initial_t_cash)
        self.current_value = self.initial_t_cash
        self.peak_value = self.initial_t_cash

    def _calculate_macd_enhanced(self, current_price: float) -> tuple:
        """计算三个 MACD 增强信号。
        
        返回:
            (macd_divergence, macd_hist_trend, macd_cross_position)
            - macd_divergence: "none" / "bottom" / "top"
            - macd_hist_trend: "neutral" / "green_shrinking" / "red_shrinking" / "red_to_green" / "green_to_red"
            - macd_cross_position: "none" / "above_zero_golden" / "below_zero_golden" / "above_zero_dead" / "below_zero_dead"
        """
        # 获取当前 MACD 值
        curr_hist = float(self.macd_hist[0]) if not np.isnan(self.macd_hist[0]) else 0.0
        curr_macd = float(self.macd.macd[0]) if not np.isnan(self.macd.macd[0]) else 0.0
        curr_signal = float(self.macd.signal[0]) if not np.isnan(self.macd.signal[0]) else 0.0
        
        # 更新历史缓存（保留最近20根）
        self._macd_hist_history.append(curr_hist)
        self._macd_history.append(curr_macd)
        self._signal_history.append(curr_signal)
        self._close_history.append(current_price)
        
        max_history = 20
        if len(self._macd_hist_history) > max_history:
            self._macd_hist_history = self._macd_hist_history[-max_history:]
            self._macd_history = self._macd_history[-max_history:]
            self._signal_history = self._signal_history[-max_history:]
            self._close_history = self._close_history[-max_history:]
        
        # 初始化返回值
        macd_divergence = "none"
        macd_hist_trend = "neutral"
        macd_cross_position = "none"
        
        # ===== 功能1: 顶背离/底背离检测 =====
        if len(self._close_history) >= 10 and len(self._macd_hist_history) >= 10:
            recent_close = self._close_history[-10:]
            recent_hist = self._macd_hist_history[-10:]
            
            # 底背离：价格创新低但MACD柱未创新低
            price_min_idx = recent_close.index(min(recent_close))
            if price_min_idx >= 3:  # 需要前半段有足够数据
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
            if macd_divergence == "none":  # 顶背离和底背离互斥
                price_max_idx = recent_close.index(max(recent_close))
                if price_max_idx >= 3:
                    first_half_close_hi = recent_close[:price_max_idx]
                    first_half_hist_hi = recent_hist[:price_max_idx]
                    if len(first_half_close_hi) >= 3:
                        prev_price_high = max(first_half_close_hi)
                        prev_hist_at_high = first_half_hist_hi[first_half_close_hi.index(prev_price_high)]
                        curr_price_high = max(recent_close)
                        curr_hist_at_high = recent_hist[price_max_idx]
                        # 价格新高 + MACD柱未新高 + 当前柱在正值区
                        if (curr_price_high > prev_price_high
                            and curr_hist_at_high < prev_hist_at_high
                            and curr_hist_at_high > 0):
                            macd_divergence = "top"
        
        # ===== 功能2: 柱状图变化趋势 =====
        if len(self._macd_hist_history) >= 4:
            last3 = self._macd_hist_history[-3:]
            curr = self._macd_hist_history[-1]
            prev1 = self._macd_hist_history[-2]
            
            # 绿柱（负值）连续3根缩短 → 空头衰竭
            if all(h < 0 for h in last3) and last3[0] < last3[1] < last3[2]:
                macd_hist_trend = "green_shrinking"
            # 红柱（正值）连续3根缩短 → 多头衰竭
            elif all(h > 0 for h in last3) and last3[0] > last3[1] > last3[2]:
                macd_hist_trend = "red_shrinking"
            # 绿转红（金叉）
            elif prev1 <= 0 and curr > 0:
                macd_hist_trend = "red_to_green"
            # 红转绿（死叉）
            elif prev1 >= 0 and curr < 0:
                macd_hist_trend = "green_to_red"
        
        # ===== 功能3: 金叉/死叉位置判断 =====
        macd_cross_position = "none"
        if len(self._macd_history) >= 2 and len(self._signal_history) >= 2:
            prev_macd = self._macd_history[-2]
            curr_macd = self._macd_history[-1]
            prev_signal = self._signal_history[-2]
            curr_signal = self._signal_history[-1]
            
            # 金叉：DIF从下方穿越DEA
            if prev_macd <= prev_signal and curr_macd > curr_signal:
                if curr_macd > 0:
                    macd_cross_position = "above_zero_golden"  # 零轴上方金叉
                else:
                    macd_cross_position = "below_zero_golden"  # 零轴下方金叉
            # 死叉：DIF从上方穿越DEA
            elif prev_macd >= prev_signal and curr_macd < curr_signal:
                if curr_macd > 0:
                    macd_cross_position = "above_zero_dead"  # 零轴上方死叉
                else:
                    macd_cross_position = "below_zero_dead"  # 零轴下方死叉
        
        return macd_divergence, macd_hist_trend, macd_cross_position

    def _calculate_backtest_daily_tone(self, gap_pct: float, bull_structure_weak: bool) -> dict:
        """基于当前 MSTR/BTC bar 计算回测内 daily tone。"""
        if not self.params.enable_btc_tone or self.btc_data is None:
            return {
                "tone": "neutral",
                "forward_bias": 0.0,
                "reverse_bias": 0.0,
                "reason": "BTC tone disabled",
            }

        btc_close = float(self.btc_data.close[0]) if not np.isnan(self.btc_data.close[0]) else 0.0
        btc_prev_close = float(self.btc_data.close[-1]) if len(self.btc_data) > 1 and not np.isnan(self.btc_data.close[-1]) else btc_close
        btc_change_pct = ((btc_close - btc_prev_close) / btc_prev_close * 100) if btc_prev_close > 0 else 0.0

        btc_fast = float(self.btc_ema_fast[0]) if self.btc_ema_fast is not None and not np.isnan(self.btc_ema_fast[0]) else btc_close
        btc_slow = float(self.btc_ema_slow[0]) if self.btc_ema_slow is not None and not np.isnan(self.btc_ema_slow[0]) else btc_close

        mstr_ema_bullish = self.ema9[0] > self.ema21[0] if not np.isnan(self.ema21[0]) else True
        mstr_macd_bullish = self.macd.lines.macd[0] > self.macd.lines.signal[0] if not np.isnan(self.macd.lines.signal[0]) else True

        return evaluate_daily_tone_snapshot(
            mstr_change_pct=gap_pct * 100,
            mstr_ema_bullish=bool(mstr_ema_bullish),
            mstr_macd_bullish=bool(mstr_macd_bullish),
            mstr_bull_structure_weak=bool(bull_structure_weak),
            btc_change_pct=btc_change_pct,
            btc_ema_bullish=btc_fast > btc_slow,
            btc_price_above_fast=btc_close > btc_fast,
        )
    
    def _mark_to_market(self, current_price: float):
        """T 仓净值：现金 + 正向T市值 - 反向T回补负债。"""
        long_exit_value = estimate_fees(SELL, price=current_price, shares=self.t_long_shares).net_amount
        reverse_buyback_cost = 0.0
        if self.reverse_t_shares > 0:
            buyback_fee = estimate_fees(BUY, price=current_price, shares=self.reverse_t_shares)
            reverse_buyback_cost = buyback_fee.gross_amount + buyback_fee.total_fees
        self.current_value = self.t_cash + long_exit_value - reverse_buyback_cost
        self.peak_value = max(self.peak_value, self.current_value)
        if self.peak_value > 0:
            drawdown = (self.peak_value - self.current_value) / self.peak_value * 100
            self.max_drawdown_pct = max(self.max_drawdown_pct, drawdown)

    def _record_close(self, pnl: float, direction: str, entry_date, exit_date):
        self.total_pnl += pnl
        self.trade_count += 1
        if pnl > 0:
            self.win_count += 1
            if direction == "forward":
                self.forward_t_wins += 1
            else:
                self.reverse_t_wins += 1
        else:
            self.loss_count += 1
        if direction == "forward":
            self.forward_t_count += 1
        else:
            self.reverse_t_count += 1
        if entry_date and exit_date and entry_date != exit_date:
            self.cross_session_t_count += 1

    def _open_forward_t(self, current_price: float, trade_amount: float, trade_type: str, current_date):
        shares = max_affordable_shares(trade_amount, current_price)
        entry_fee = estimate_fees(BUY, price=current_price, shares=shares)
        total_debit = entry_fee.gross_amount + entry_fee.total_fees
        if shares <= 0 or self.t_cash < total_debit:
            return False
        self.t_cash -= total_debit
        self.t_long_shares = shares
        self.t_long_entry_price = current_price
        self.t_long_cost_basis = total_debit
        self.t_long_entry_date = current_date
        self.t_long_type = trade_type
        self.holding_shares = shares
        self.buy_price = current_price
        if trade_type == "dip":
            self.target_price = current_price * (1 + self.params.dip_profit_pct)
            self.stop_price = current_price * (1 - self.params.dip_stop_pct)
            self.dip_trades += 1
        else:
            self.target_price = current_price * (1 + self.params.mom_profit_pct)
            self.stop_price = current_price * (1 - self.params.mom_stop_pct)
            self.mom_trades += 1
        self.position_type = trade_type
        return True

    def _close_forward_t(self, current_price: float, current_date):
        if self.t_long_shares <= 0:
            return
        exit_fee = estimate_fees(SELL, price=current_price, shares=self.t_long_shares)
        proceeds = exit_fee.net_amount
        pnl = proceeds - self.t_long_cost_basis
        self.t_cash += proceeds
        self._record_close(pnl, "forward", self.t_long_entry_date, current_date)
        if pnl > 0:
            if self.t_long_type == "dip":
                self.dip_wins += 1
            elif self.t_long_type == "momentum":
                self.mom_wins += 1
        self.t_long_shares = 0
        self.t_long_entry_price = 0.0
        self.t_long_cost_basis = 0.0
        self.t_long_entry_date = None
        self.t_long_type = ""
        self.holding_shares = 0
        self.buy_price = None
        self.position_type = ""

    def _open_reverse_t(self, current_price: float, current_date):
        shares = int(self.params.reverse_trade_amount / current_price)
        available_base = self.params.base_position - self.reverse_t_shares
        shares = min(shares, available_base)
        if shares <= 0:
            return False
        # 反向T：先从已有底仓里卖出一部分，现金回到账户，等待更低位买回。
        sell_fee = estimate_fees(SELL, price=current_price, shares=shares)
        self.t_cash += sell_fee.net_amount
        self.reverse_t_shares = shares
        self.reverse_sell_price = current_price
        self.reverse_sale_net_proceeds = sell_fee.net_amount
        self.reverse_entry_date = current_date
        return True

    def _close_reverse_t(self, current_price: float, current_date):
        if self.reverse_t_shares <= 0:
            return
        buy_fee = estimate_fees(BUY, price=current_price, shares=self.reverse_t_shares)
        cost = buy_fee.gross_amount + buy_fee.total_fees
        pnl = self.reverse_sale_net_proceeds - cost
        self.t_cash -= cost
        self._record_close(pnl, "reverse", self.reverse_entry_date, current_date)
        self.reverse_t_shares = 0
        self.reverse_sell_price = 0.0
        self.reverse_sale_net_proceeds = 0.0
        self.reverse_entry_date = None
    
    def log(self, txt, dt=None):
        if self.params.printlog:
            dt = dt or self.datas[0].datetime.date(0)
            print(f'[{dt.isoformat()}] {txt}')
    
    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status in [order.Completed]:
            if order.isbuy():
                self.buy_price = order.executed.price
                self.holding_shares = int(order.executed.size)
                if self.position_type == "dip":
                    self.target_price = self.buy_price * (1 + self.params.dip_profit_pct)
                    self.stop_price = self.buy_price * (1 - self.params.dip_stop_pct)
                else:
                    self.target_price = self.buy_price * (1 + self.params.mom_profit_pct)
                    self.stop_price = self.buy_price * (1 - self.params.mom_stop_pct)
                self.log(f'买入: {self.holding_shares}股 @ ${self.buy_price:.2f} [{self.position_type}]')
            elif order.issell():
                sell_price = order.executed.price
                pnl = (sell_price - self.buy_price) * self.holding_shares if self.buy_price else 0
                self.total_pnl += pnl
                self.trade_count += 1
                if pnl > 0:
                    self.win_count += 1
                    if self.position_type == "dip":
                        self.dip_wins += 1
                    else:
                        self.mom_wins += 1
                else:
                    self.loss_count += 1
                self.log(f'卖出: @ ${sell_price:.2f}, PnL ${pnl:+.2f} [{self.position_type}]')
                self.holding_shares = 0
                self.buy_price = None
                self.position_type = ""
        self.order = None
    
    def next(self):
        self.update_session_state()
        current_price = self.data.close[0]  # MSTU execution price
        signal_price = self.signal_data.close[0]  # MSTR signal price
        current_date = self.signal_data.datetime.datetime(0).date()
        self._mark_to_market(current_price)

        # 不再限制“每天只开一次仓”，否则不符合日内做T的节奏。
        if self.prev_day_close is None:
            return
        
        gap_pct = self.current_gap_pct()
        if gap_pct is None:
            return
        
        # ADX趋势判断
        adx_val = self.adx[0] if not np.isnan(self.adx[0]) else 25
        price_below_sma50 = signal_price < self.sma50[0] if not np.isnan(self.sma50[0]) else False
        strong_downtrend = price_below_sma50 and adx_val > self.params.downtrend_adx_threshold
        short_above_long = self.short_bull_bottom[0] > self.long_bull_bottom[0] if not np.isnan(self.long_bull_bottom[0]) else True
        price_above_long_top = signal_price > self.long_bull_top[0] if not np.isnan(self.long_bull_top[0]) else True
        short_bottom_rising = self.short_bull_bottom[0] > self.short_bull_bottom[-1] if not np.isnan(self.short_bull_bottom[-1]) else True
        long_bottom_rising = self.long_bull_bottom[0] > self.long_bull_bottom[-1] if not np.isnan(self.long_bull_bottom[-1]) else True
        persistent_structure = all(
            self.short_bull_bottom[-offset] > self.long_bull_bottom[-offset]
            for offset in range(self.params.bull_structure_confirm_bars)
        )
        bull_structure_weak = short_above_long and price_above_long_top
        bull_structure_strong = (
            bull_structure_weak and persistent_structure and short_bottom_rising and long_bottom_rising
        )
        tone_data = self._calculate_backtest_daily_tone(gap_pct, bull_structure_weak)
        self.daily_tone = tone_data["tone"]
        self.tone_forward_bias = tone_data["forward_bias"]
        self.tone_reverse_bias = tone_data["reverse_bias"]
        self.tone_reason = tone_data["reason"]
        if current_date != self._tone_session_date:
            self.tone_hits[self.daily_tone] += 1
            self._tone_session_date = current_date
        volume_ratio = self.signal_data.volume[0] / self.volume_sma[0] if self.volume_sma[0] else 1.0
        vwap_cross_up = self.signal_data.close[-1] <= self.vwap[-1] and signal_price > self.vwap[0]
        gap_too_big = gap_pct > 0.05
        effective_gap_down_pct = self.params.gap_down_pct + (self.tone_forward_bias * 0.01)
        effective_gap_up_pct = max(0.0, self.params.gap_up_pct - (self.tone_forward_bias * 0.01))
        effective_reverse_trigger_threshold = self.params.reverse_trigger_threshold - self.tone_reverse_bias
        
        # ===== 计算 MACD 增强信号 =====
        if self.params.enable_macd_enhanced:
            macd_divergence, macd_hist_trend, macd_cross_position = self._calculate_macd_enhanced(signal_price)
        else:
            macd_divergence, macd_hist_trend, macd_cross_position = ("none", "neutral", "none")
        macd_buy_score = 0.0
        macd_sell_score = 0.0
        
        # 功能1: 顶背离/底背离
        if macd_divergence == "bottom":
            macd_buy_score += 1.5
            self.signal_hits["macd_bottom_divergence"] += 1
        elif macd_divergence == "top":
            macd_sell_score += 1.5
            self.signal_hits["macd_top_divergence"] += 1
        
        # 功能2: 柱状图变化趋势
        if macd_hist_trend == "green_shrinking":
            macd_buy_score += 1.0
            self.signal_hits["macd_green_shrinking"] += 1
        elif macd_hist_trend == "red_shrinking":
            macd_sell_score += 1.0
            self.signal_hits["macd_red_shrinking"] += 1
        elif macd_hist_trend == "red_to_green":
            macd_buy_score += 0.75
            self.signal_hits["macd_red_to_green"] += 1
        elif macd_hist_trend == "green_to_red":
            macd_sell_score += 0.75
            self.signal_hits["macd_green_to_red"] += 1
        
        # 功能3: 金叉/死叉位置
        if macd_cross_position == "above_zero_golden":
            macd_buy_score += 1.5
            self.signal_hits["macd_above_zero_golden"] += 1
        elif macd_cross_position == "below_zero_golden":
            macd_buy_score += 0.75
            self.signal_hits["macd_below_zero_golden"] += 1
        elif macd_cross_position == "above_zero_dead":
            macd_sell_score += 0.75
            self.signal_hits["macd_above_zero_dead"] += 1
        elif macd_cross_position == "below_zero_dead":
            macd_sell_score += 1.5
            self.signal_hits["macd_below_zero_dead"] += 1
        rsi_rebound = (
            not np.isnan(self.rsi[-1])
            and not np.isnan(self.rsi[0])
            and self.rsi[-1] <= self.params.rsi_rebound_prev_max
            and self.rsi[0] > self.params.rsi_rebound_now_min
        )
        j_val = 3 * self.k[0] - 2 * self.d[0] if not np.isnan(self.k[0]) and not np.isnan(self.d[0]) else 50
        prev_j_val = 3 * self.k[-1] - 2 * self.d[-1] if not np.isnan(self.k[-1]) and not np.isnan(self.d[-1]) else 50
        kdj_turn_bull = prev_j_val <= self.params.kdj_turn_level and j_val > self.params.kdj_turn_level
        morning_star = bool(self.patterns.morning_star[0])
        evening_star = bool(self.patterns.evening_star[0])
        inside_bar_breakout_up = bool(self.patterns.inside_bar_breakout_up[0])
        inside_bar_breakout_down = bool(self.patterns.inside_bar_breakout_down[0])

        # 记录信号命中次数，方便判断“规则没触发”还是“触发了但没改变交易”。
        if morning_star:
            self.signal_hits["morning_star"] += 1
        if evening_star:
            self.signal_hits["evening_star"] += 1
        if inside_bar_breakout_up:
            self.signal_hits["inside_bar_breakout_up"] += 1
        if inside_bar_breakout_down:
            self.signal_hits["inside_bar_breakout_down"] += 1
        if rsi_rebound:
            self.signal_hits["rsi_rebound"] += 1
        if kdj_turn_bull:
            self.signal_hits["kdj_turn_bull"] += 1
        if vwap_cross_up:
            self.signal_hits["vwap_cross_up"] += 1
        if bull_structure_weak:
            self.signal_hits["bull_structure_weak"] += 1
        if bull_structure_strong:
            self.signal_hits["bull_structure_strong"] += 1

        vwap_cross_down = self.signal_data.close[-1] >= self.vwap[-1] and signal_price < self.vwap[0]
        rsi_top_fade = (
            not np.isnan(self.rsi[-1])
            and not np.isnan(self.rsi[0])
            and self.rsi[-1] >= 78
            and self.rsi[0] < self.rsi[-1]
        )
        kdj_turn_bear = prev_j_val >= 70 and j_val < 70
        intraday_position = 0.5
        run_up_from_open = 0.0
        pullback_from_high = 0.0
        # 用“盘中先冲起来过，再从高位回落”来表达反向T环境，比单看当前位置更接近真实高抛语义。
        if self.session_high is not None and self.session_low is not None and self.session_high > self.session_low:
            intraday_position = (signal_price - self.session_low) / (self.session_high - self.session_low)
        if self.day_open:
            run_up_from_open = (self.session_high - self.day_open) / self.day_open
        if self.session_high:
            pullback_from_high = (self.session_high - signal_price) / self.session_high

        # ===== 先处理已持有的 T 仓 =====
        if self.t_long_shares > 0:
            if current_price >= self.target_price or current_price <= self.stop_price:
                self._close_forward_t(current_price, current_date)
            elif self.t_long_type == "dip" and current_price > self.t_long_entry_price * 1.008:
                self._close_forward_t(current_price, current_date)
            elif self.t_long_type == "momentum" and (current_price > self.t_long_entry_price * 1.006 or vwap_cross_down):
                self._close_forward_t(current_price, current_date)

        if self.reverse_t_shares > 0:
            buyback_target = self.reverse_sell_price * (1 - self.params.reverse_profit_pct)
            buyback_stop = self.reverse_sell_price * (1 + self.params.reverse_stop_pct)
            if current_price <= buyback_target or current_price >= buyback_stop:
                self._close_reverse_t(current_price, current_date)
            elif rsi_rebound or kdj_turn_bull:
                self._close_reverse_t(current_price, current_date)

        # ===== 低吸模式 =====
        if self.t_long_shares == 0 and gap_pct <= effective_gap_down_pct:
            # 强下跌趋势中减少买入（除非超跌反弹信号很强）
            rsi_val = self.rsi[0] if not np.isnan(self.rsi[0]) else 50
            bb_lower = signal_price <= self.boll.lines.bot[0] if not np.isnan(self.boll.lines.bot[0]) else False
            
            # MACD 底背离作为额外加分项
            macd_dip_boost = macd_buy_score if macd_divergence == "bottom" else 0
            
            if strong_downtrend:
                # 强下跌环境只做极端超跌反弹
                # 形态信号保留统计，但不再替代核心拐点条件。
                # MACD底背离可以增强超跌反弹信心
                if (
                    rsi_val < 22 and bb_lower and gap_pct <= -0.07
                    and (rsi_rebound or kdj_turn_bull or macd_divergence == "bottom")
                ):
                    if self._open_forward_t(current_price, self.params.trade_amount * 0.6, "dip", current_date):
                        return
            else:
                # 非下跌趋势也只做更强的低吸，避免普通回落反复止损
                # MACD信号纳入综合判断
                dip_signals = sum([bull_structure_weak, rsi_rebound, kdj_turn_bull,
                                   macd_divergence == "bottom", macd_hist_trend == "green_shrinking"])
                dip_signal_score = dip_signals + self.tone_forward_bias
                if ((rsi_val < 30 and bb_lower and dip_signal_score >= 1)
                        or gap_pct <= effective_gap_down_pct * 1.25):
                    if self._open_forward_t(current_price, self.params.trade_amount, "dip", current_date):
                        return
        
        # ===== 追涨模式 =====
        # 日内追涨不再只盯“高开缺口”，而是拆成两条入口：
        # 1. 开盘就很强：gap-up 顺势；
        # 2. 盘中才启动：放量站稳 VWAP，且已经从开盘拉出一段幅度但没有明显冲顶回落。
        if self.t_long_shares == 0:
            ema_bullish = self.ema9[0] > self.ema21[0] if not np.isnan(self.ema21[0]) else True
            macd_bullish = self.macd.lines.macd[0] > self.macd.lines.signal[0] if not np.isnan(self.macd.lines.signal[0]) else True
            momentum_bias = 0.0
            if bull_structure_strong:
                momentum_bias += 0.5
            elif bull_structure_weak:
                momentum_bias += 0.25
            if kdj_turn_bull:
                momentum_bias += 0.5
            if rsi_rebound:
                momentum_bias += 0.25
            momentum_bias += self.tone_forward_bias
            
            # MACD 增强信号纳入追涨评分
            if macd_cross_position in ["above_zero_golden", "below_zero_golden"]:
                momentum_bias += 0.5
            if macd_hist_trend == "red_to_green":
                momentum_bias += 0.25

            gap_momentum_ok = effective_gap_up_pct <= gap_pct <= self.params.max_chase_pct
            intraday_breakout_ok = (
                run_up_from_open >= self.params.momentum_runup_min
                and intraday_position >= self.params.momentum_intraday_position_min
                and pullback_from_high <= self.params.momentum_pullback_max
                and signal_price > self.vwap[0]
            )
            # 追涨不再只认“上穿当根”，也允许上穿后的延续启动。
            vwap_momentum_ready = (
                vwap_cross_up
                or (
                    intraday_breakout_ok
                    and self.signal_data.close[-1] > self.vwap[-1]
                )
            )

            if (
                (gap_momentum_ok or intraday_breakout_ok)
                and
                ema_bullish and macd_bullish
                and vwap_momentum_ready
                and volume_ratio >= self.params.vwap_volume_ratio_min
                and not gap_too_big
                and momentum_bias >= 0.25
            ):
                if self._open_forward_t(current_price, self.params.mom_trade_amount, "momentum", current_date):
                    return

        # ===== 反向T：高抛已有底仓，再低位买回 =====
        # 反向T是当前系统里最容易“做太多”的部分，所以这里故意比正向T更严格：
        # 1. VWAP 下破必须成立，先确认分时节奏已转弱；
        # 2. 再叠加 RSI/KDJ 顶部转弱或位置过高，才允许减底仓做反向T；
        # 3. 牛熊线只做背景偏置，不再单独触发反向T。
        if self.reverse_t_shares == 0:
            reverse_bias = 0.0
            reverse_gate = (
                vwap_cross_down
                and run_up_from_open >= self.params.reverse_runup_min
                and pullback_from_high >= self.params.reverse_pullback_min
            )
            if run_up_from_open >= self.params.reverse_runup_min:
                reverse_bias += 0.5
            if pullback_from_high >= self.params.reverse_pullback_min:
                reverse_bias += 0.25
            if vwap_cross_down:
                reverse_bias += 1.0
            if rsi_top_fade:
                reverse_bias += 0.75
            if kdj_turn_bear:
                reverse_bias += 0.75
            if not bull_structure_weak:
                reverse_bias += 0.25
            
            # MACD 增强信号纳入反向T评分
            if macd_divergence == "top":
                reverse_bias += 1.0
            if macd_hist_trend == "red_shrinking":
                reverse_bias += 0.5
            if macd_cross_position in ["above_zero_dead", "below_zero_dead"]:
                reverse_bias += 0.75

            # 顶部拐头需要至少一个“动能衰减”确认，避免单靠价格位置去猜顶部。
            # MACD 顶背离和死叉也作为动能衰减信号
            reverse_confirmation = rsi_top_fade or kdj_turn_bear or macd_divergence == "top" or macd_cross_position in ["above_zero_dead", "below_zero_dead"]
            if reverse_gate and reverse_confirmation and reverse_bias >= effective_reverse_trigger_threshold:
                self._open_reverse_t(current_price, current_date)
    
    def stop(self):
        if not self.params.print_summary:
            return
        win_rate = self.win_count / self.trade_count * 100 if self.trade_count > 0 else 0
        dip_win_rate = self.dip_wins / self.dip_trades * 100 if self.dip_trades > 0 else 0
        mom_win_rate = self.mom_wins / self.mom_trades * 100 if self.mom_trades > 0 else 0
        
        print(f'\n{"="*60}')
        print(f'📊 组合策略回测结果（底仓 + T仓）')
        print(f'{"="*60}')
        print(f'总交易: {self.trade_count}次 | 胜率: {win_rate:.1f}% | 总盈亏: ${self.total_pnl:+.2f}')
        if self.trade_count > 0:
            print(f'平均每笔: ${self.total_pnl/self.trade_count:+.2f}')
        print(f'--- T仓结构 ---')
        print(f'  正向T: {self.forward_t_count}次 | 反向T: {self.reverse_t_count}次 | 跨天T: {self.cross_session_t_count}次')
        print(f'--- 低吸模式 ---')
        print(f'  交易: {self.dip_trades}次 | 胜率: {dip_win_rate:.1f}%')
        print(f'--- 追涨模式 ---')
        print(f'  交易: {self.mom_trades}次 | 胜率: {mom_win_rate:.1f}%')
        print(f'--- Daily Tone ---')
        print(f'  bullish_strong: {self.tone_hits["bullish_strong"]}')
        print(f'  bullish: {self.tone_hits["bullish"]}')
        print(f'  neutral: {self.tone_hits["neutral"]}')
        print(f'  bearish: {self.tone_hits["bearish"]}')
        print(f'  bearish_strong: {self.tone_hits["bearish_strong"]}')
        print(f'--- 原始信号命中 ---')
        for name in ["morning_star", "evening_star", "inside_bar_breakout_up", "inside_bar_breakout_down", "rsi_rebound", "kdj_turn_bull", "vwap_cross_up", "bull_structure_weak", "bull_structure_strong"]:
            print(f'  {name}: {self.signal_hits[name]}')
        print(f'--- MACD增强信号命中 ---')
        macd_hits = {
            "macd_bottom_divergence": self.signal_hits["macd_bottom_divergence"],
            "macd_top_divergence": self.signal_hits["macd_top_divergence"],
            "macd_green_shrinking": self.signal_hits["macd_green_shrinking"],
            "macd_red_shrinking": self.signal_hits["macd_red_shrinking"],
            "macd_red_to_green": self.signal_hits["macd_red_to_green"],
            "macd_green_to_red": self.signal_hits["macd_green_to_red"],
            "macd_above_zero_golden": self.signal_hits["macd_above_zero_golden"],
            "macd_below_zero_golden": self.signal_hits["macd_below_zero_golden"],
            "macd_above_zero_dead": self.signal_hits["macd_above_zero_dead"],
            "macd_below_zero_dead": self.signal_hits["macd_below_zero_dead"],
        }
        for name, hits in macd_hits.items():
            print(f'  {name}: {hits}')
        print(f'{"="*60}')

def run_backtest(strategy_class, csv_path=None, cash=1400, commission=0.001,
                 strategy_params=None, verbose=True):
    """运行回测。

    csv_path 可以是：
    - 单个 CSV 路径：兼容旧版单标回测
    - {"mstu": "...", "mstr": "...", "btc": "..."}：推荐的三标回测模式
    """
    cerebro = bt.Cerebro()

    # 加载数据
    if isinstance(csv_path, dict):
        mstu_path = csv_path.get("mstu")
        mstr_path = csv_path.get("mstr")
        btc_path = csv_path.get("btc")
        if not (mstu_path and os.path.exists(mstu_path) and mstr_path and os.path.exists(mstr_path)):
            print("❌ 双标的数据文件不完整")
            return
        def read_feed(path, name):
            df = pd.read_csv(path, index_col=0)
            df.index = pd.to_datetime(df.index, utc=True).tz_convert(None)
            df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
            df.columns = ['open', 'high', 'low', 'close', 'volume']
            return bt.feeds.PandasData(dataname=df, name=name)
        # adddata 顺序不能改：data0=MSTU 执行，data1=MSTR 信号
        cerebro.adddata(read_feed(mstu_path, "MSTU"))
        cerebro.adddata(read_feed(mstr_path, "MSTR"))
        if btc_path and os.path.exists(btc_path):
            cerebro.adddata(read_feed(btc_path, "BTC"))
    elif csv_path and os.path.exists(csv_path):
        df = pd.read_csv(csv_path, index_col=0)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(None)
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
        df.columns = ['open', 'high', 'low', 'close', 'volume']
        data = bt.feeds.PandasData(dataname=df, name="MSTU")
        cerebro.adddata(data)
    else:
        print("❌ 无数据文件")
        return
    
    # 设置
    strategy_params = strategy_params or {}
    cerebro.addstrategy(strategy_class, **strategy_params)
    cerebro.broker.setcash(cash)
    cerebro.broker.setcommission(commission=commission)
    
    # 分析器
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
    
    # 运行
    if verbose:
        print(f'\n{"="*60}')
        print(f'💰 初始资金: ${cash:.2f}')
        print(f'📊 手续费: {commission*100:.1f}%')
        print(f'📈 策略: {strategy_class.__name__}')
        if strategy_params:
            print(f'🧪 参数: {strategy_params}')
        print(f'{"="*60}\n')
    
    results = cerebro.run()
    strat = results[0]
    
    # 最终资金
    final_value = getattr(strat, "current_value", cerebro.broker.getvalue())
    total_return_pct = (final_value / cash - 1) * 100
    max_drawdown = None
    sharpe_ratio = None
    trade_analysis = {}

    # 分析结果
    try:
        sharpe = strat.analyzers.sharpe.get_analysis()
        dd = strat.analyzers.drawdown.get_analysis()
        sharpe_ratio = sharpe.get("sharperatio")
        max_drawdown = dd.get("max", {}).get("drawdown")
    except:
        pass
    if hasattr(strat, "max_drawdown_pct"):
        max_drawdown = strat.max_drawdown_pct

    try:
        trade_analysis = strat.analyzers.trades.get_analysis()
    except:
        trade_analysis = {}

    if verbose:
        print(f'\n💰 最终资金: ${final_value:.2f}')
        print(f'📈 总收益率: {total_return_pct:+.2f}%')
        print(f'📊 夏普比率: {sharpe_ratio}')
        if max_drawdown is not None:
            print(f'📉 最大回撤: {max_drawdown:.2f}%')

    return results


def collect_backtest_metrics(strategy_class, csv_path=None, cash=1400, commission=0.001,
                             strategy_params=None) -> dict:
    """运行回测并返回核心指标，供参数搜索使用。"""
    results = run_backtest(
        strategy_class,
        csv_path=csv_path,
        cash=cash,
        commission=commission,
        strategy_params=strategy_params,
        verbose=False,
    )
    strat = results[0]
    final_value = getattr(strat, "current_value", strat.broker.getvalue())

    try:
        drawdown = strat.analyzers.drawdown.get_analysis()
        max_drawdown = drawdown.get("max", {}).get("drawdown")
    except:
        max_drawdown = None
    if hasattr(strat, "max_drawdown_pct"):
        max_drawdown = strat.max_drawdown_pct

    try:
        sharpe = strat.analyzers.sharpe.get_analysis()
        sharpe_ratio = sharpe.get("sharperatio")
    except:
        sharpe_ratio = None

    try:
        trades = strat.analyzers.trades.get_analysis()
        total_closed = trades.get("total", {}).get("closed", 0)
        won = trades.get("won", {}).get("total", 0)
        lost = trades.get("lost", {}).get("total", 0)
    except:
        total_closed = 0
        won = 0
        lost = 0
    if hasattr(strat, "trade_count"):
        total_closed = strat.trade_count
        won = strat.win_count
        lost = strat.loss_count

    metrics = {
        "final_value": round(final_value, 2),
        "return_pct": round((final_value / cash - 1) * 100, 2),
        "max_drawdown": round(max_drawdown, 2) if max_drawdown is not None else None,
        "sharpe_ratio": sharpe_ratio,
        "total_closed": total_closed,
        "won": won,
        "lost": lost,
        "win_rate": round((won / total_closed) * 100, 2) if total_closed else 0.0,
    }
    if hasattr(strat, "forward_t_count"):
        metrics["forward_t_count"] = strat.forward_t_count
        metrics["reverse_t_count"] = strat.reverse_t_count
        metrics["cross_session_t_count"] = strat.cross_session_t_count
    if hasattr(strat, "signal_hits"):
        metrics["signal_hits"] = dict(strat.signal_hits)
    if hasattr(strat, "tone_hits"):
        metrics["tone_hits"] = dict(strat.tone_hits)
        metrics["daily_tone"] = getattr(strat, "daily_tone", "neutral")
    return metrics


def run_quadrant_experiment(csv_path, cash=1400, commission=0.001) -> dict:
    """运行四象限实验：baseline / macd_only / btc_only / macd_plus_btc。"""
    variants = {
        "baseline": {"enable_macd_enhanced": False, "enable_btc_tone": False, "print_summary": False},
        "macd_only": {"enable_macd_enhanced": True, "enable_btc_tone": False, "print_summary": False},
        "btc_only": {"enable_macd_enhanced": False, "enable_btc_tone": True, "print_summary": False},
        "macd_plus_btc": {"enable_macd_enhanced": True, "enable_btc_tone": True, "print_summary": False},
    }

    result = {
        "experiment": "quadrant",
        "csv": csv_path,
        "variants": {},
    }

    for name, params in variants.items():
        metrics = collect_backtest_metrics(
            CombinedStrategy,
            csv_path=csv_path,
            cash=cash,
            commission=commission,
            strategy_params=params,
        )
        result["variants"][name] = {
            "params": params,
            **metrics,
        }

    return result


def save_experiment_result(result: dict, output_dir: str = None, filename: str = None) -> str:
    """保存实验结果到磁盘，返回输出路径。"""
    output_dir = output_dir or os.path.join(os.path.dirname(__file__), "reports")
    os.makedirs(output_dir, exist_ok=True)
    if filename is None:
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"{result.get('experiment', 'experiment')}-{stamp}.json"
    output_path = os.path.join(output_dir, filename)
    with open(output_path, "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return output_path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", choices=["dip", "momentum", "combined", "all"], default="all")
    parser.add_argument("--experiment", choices=["quadrant"], default=None)
    parser.add_argument("--download", action="store_true", help="重新下载数据")
    parser.add_argument("--interval", default="15m", help="下载数据周期，默认15m")
    parser.add_argument("--period", default="60d", help="下载历史范围，默认60d")
    args = parser.parse_args()
    
    csv_path = os.path.join(os.path.dirname(__file__), "mstu_history.csv")
    dual_csv = {
        "mstu": os.path.join(os.path.dirname(__file__), "mstu_history.csv"),
        "mstr": os.path.join(os.path.dirname(__file__), "mstr_history.csv"),
    }
    
    # 下载数据
    if args.strategy in ["combined", "all"]:
        if args.download or not (os.path.exists(dual_csv["mstu"]) and os.path.exists(dual_csv["mstr"])):
            result = download_market_data(interval=args.interval, period=args.period)
            if result:
                dual_csv = result
            else:
                print("无法获取双标回测数据，退出")
                sys.exit(1)
    else:
        if args.download or not os.path.exists(csv_path):
            result = download_mstu_data(interval=args.interval, period=args.period)
            if result:
                csv_path = result
            else:
                print("无法获取数据，退出")
                sys.exit(1)
    
    if args.experiment == "quadrant":
        print("\n" + "🧪" * 30)
        experiment_result = run_quadrant_experiment(dual_csv)
        output_path = save_experiment_result(experiment_result)
        print("Quadrant experiment summary:")
        for name, payload in experiment_result["variants"].items():
            print(
                f"  {name}: return={payload['return_pct']:+.2f}% "
                f"win_rate={payload['win_rate']:.2f}% "
                f"drawdown={payload['max_drawdown']}"
            )
        print(f"Saved full result to: {output_path}")
        sys.exit(0)

    # 运行回测
    if args.strategy in ["dip", "all"]:
        print("\n" + "🔶" * 30)
        run_backtest(DipBuyStrategy, csv_path)
    
    if args.strategy in ["momentum", "all"]:
        print("\n" + "🔶" * 30)
        run_backtest(MomentumStrategy, csv_path)
    
    if args.strategy in ["combined", "all"]:
        print("\n" + "🔶" * 30)
        run_backtest(CombinedStrategy, dual_csv)
