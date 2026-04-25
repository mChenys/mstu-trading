"""MSTU 日内做T策略模块 - 跨时段版

当前版本的核心约束：
1. MSTR 负责生成方向/强弱信号，因为它是底层正股，技术指标更稳定。
2. MSTU 负责实际执行买卖，因为用户被套和做T的真实标的是 MSTU。
3. 跨时段仓位（盘前/夜盘）进入盘中后，仍然按 MSTU 的盈亏和目标价管理。

给接手的 OpenClaw Agent：
- 如果后续继续调策略，优先修改 MSTR 信号阈值，而不是回到用 MSTU 自身指标发主信号。
- 如果调整回测逻辑，请同时保持实时策略与回测的“信号源/执行标的”分工一致。
"""

import pandas as pd
import json
import os
from datetime import datetime, timezone, timedelta
import config
from fetcher import get_session_type, calculate_daily_tone
from fee_model import BUY, SELL, estimate_fees, estimate_round_trip, max_affordable_shares
try:
    from indicators_enhanced import generate_enhanced_signals, calculate_pivot_points, analyze_price_vs_levels
    ENHANCED_INDICATORS = True
except ImportError:
    ENHANCED_INDICATORS = False

class TradingStrategy:
    def __init__(self):
        self.daily_ops_count = 0
        self.daily_pnl = 0.0
        self.available_cash = config.AVAILABLE_CASH
        self.holding_shares = 0
        self.buy_price = 0.0  # 买入价
        self.holding_cost_basis = 0.0  # 持仓总成本（含手续费）
        self.target_price = 0.0  # 目标卖出价
        self.stop_price = 0.0  # 止损价
        self.position_source = ""  # 仓位来源: premarket / overnight / regular
        self.cross_session_positions = []  # 跨时段持仓列表
        self.daily_fees = 0.0
        self.cumulative_fees = 0.0
        self.last_reset_date = ""
        # 每日基调
        self.daily_tone = "neutral"  # bullish/bullish_strong/neutral/bearish/bearish_strong
        self.tone_forward_bias = 0.0  # 正T阈值放宽
        self.tone_reverse_bias = 0.0  # 反T阈值放宽
        self.tone_reason = ""
        self.tone_updated_at = ""
        self.load_position()

    @staticmethod
    def _is_cross_session_source(source: str) -> bool:
        """判断是否为跨时段仓位来源。"""
        return source.startswith("premarket") or source.startswith("overnight")

    @staticmethod
    def _source_display_label(source: str) -> str:
        """统一仓位来源文案。"""
        return {
            "premarket": "盘前仓",
            "premarket-dip": "盘前仓",
            "premarket-momentum": "盘前仓",
            "overnight": "夜盘仓",
            "overnight-dip": "夜盘仓",
            "overnight-momentum": "夜盘仓",
            "regular": "盘中仓",
        }.get(source, "仓位")

    @staticmethod
    def _get_reference_quote(quote: dict) -> dict:
        """优先使用 MSTR 作为信号参考；没有时退回 MSTU 自身。

        这里是实时策略里最关键的切换点：
        - reference quote: 用来算缺口、趋势、量价、强弱
        - quote 自身 price: 用来算 MSTU 的实际买卖价、仓位和盈亏
        """
        mstr = quote.get("mstr")
        if not mstr:
            return {
                "price": quote.get("price", 0),
                "prev_close": quote.get("prev_close", 0),
                "high": quote.get("high", 0),
                "low": quote.get("low", 0),
                "volume": quote.get("volume", 0),
                "symbol": quote.get("symbol", config.SYMBOL),
                "source": "mstu",
            }

        return {
            "price": mstr.get("mstr_price", 0),
            "prev_close": mstr.get("mstr_prev_close", 0),
            "high": mstr.get("mstr_high", 0),
            "low": mstr.get("mstr_low", 0),
            "volume": mstr.get("mstr_volume", 0),
            "open": mstr.get("mstr_open", 0),
            "change_pct": mstr.get("mstr_change_pct", 0),
            "symbol": "MSTR",
            "source": "mstr",
        }
        
    def load_position(self):
        """加载持仓状态"""
        if os.path.exists(config.POSITION_STATE_FILE):
            try:
                with open(config.POSITION_STATE_FILE, 'r') as f:
                    data = json.load(f)
                    self.holding_shares = data.get('holding_shares', 0)
                    self.buy_price = data.get('buy_price', 0.0)
                    self.holding_cost_basis = data.get('holding_cost_basis', self.buy_price * self.holding_shares)
                    self.target_price = data.get('target_price', 0.0)
                    self.stop_price = data.get('stop_price', 0.0)
                    self.position_source = data.get('position_source', '')
                    self.daily_ops_count = data.get('daily_ops_count', 0)
                    self.daily_pnl = data.get('daily_pnl', 0.0)
                    self.daily_fees = data.get('daily_fees', 0.0)
                    self.cumulative_fees = data.get('cumulative_fees', 0.0)
                    self.available_cash = data.get('available_cash', config.AVAILABLE_CASH)
                    self.cross_session_positions = data.get('cross_session_positions', [])
                    self.last_reset_date = data.get('last_reset_date', '')
                    # 基调状态
                    self.daily_tone = data.get('daily_tone', 'neutral')
                    self.tone_forward_bias = data.get('tone_forward_bias', 0.0)
                    self.tone_reverse_bias = data.get('tone_reverse_bias', 0.0)
                    self.tone_reason = data.get('tone_reason', '')
                    self.tone_updated_at = data.get('tone_updated_at', '')
            except:
                pass
    
    def save_position(self):
        """保存持仓状态"""
        data = {
            'holding_shares': self.holding_shares,
            'buy_price': self.buy_price,
            'holding_cost_basis': self.holding_cost_basis,
            'target_price': self.target_price,
            'stop_price': self.stop_price,
            'position_source': self.position_source,
            'daily_ops_count': self.daily_ops_count,
            'daily_pnl': self.daily_pnl,
            'daily_fees': self.daily_fees,
            'cumulative_fees': self.cumulative_fees,
            'available_cash': self.available_cash,
            'cross_session_positions': self.cross_session_positions,
            'last_reset_date': self.last_reset_date,
            # 基调状态
            'daily_tone': self.daily_tone,
            'tone_forward_bias': self.tone_forward_bias,
            'tone_reverse_bias': self.tone_reverse_bias,
            'tone_reason': self.tone_reason,
            'tone_updated_at': self.tone_updated_at,
            'updated_at': datetime.now(timezone.utc).isoformat()
        }
        try:
            with open(config.POSITION_STATE_FILE, 'w') as f:
                json.dump(data, f, indent=2)
        except:
            pass
    
    def reset_daily(self):
        """重置日内统计"""
        self.daily_ops_count = 0
        self.daily_pnl = 0.0
        self.daily_fees = 0.0
        self.last_reset_date = self._beijing_date_str()
        self.save_position()

    @staticmethod
    def _beijing_now() -> datetime:
        """北京时间。"""
        return datetime.now(timezone.utc) + timedelta(hours=8)

    def _beijing_date_str(self) -> str:
        """北京时间日期字符串。"""
        return self._beijing_now().strftime("%Y-%m-%d")

    def _ensure_daily_reset(self):
        """跨天自动重置日内统计，但保留持仓状态。"""
        today = self._beijing_date_str()
        if self.last_reset_date != today:
            self.reset_daily()

    def _pct_with_forward_tone(self, base_pct: float) -> float:
        """把 daily tone 的正向偏置折算到百分比阈值上。"""
        return base_pct - (self.tone_forward_bias / 100.0)

    def _score_threshold_with_forward_tone(self, base_threshold: float) -> float:
        """上涨基调时，允许更低一点的正向开仓分数门槛。"""
        return max(0.0, base_threshold - self.tone_forward_bias)

    def _score_threshold_with_reverse_tone(self, base_threshold: float) -> float:
        """下跌基调时，允许更低一点的卖出/反向动作门槛。"""
        return max(0.0, base_threshold - self.tone_reverse_bias)

    def _is_regular_trade_window_open(self) -> bool:
        """盘中是否允许开新仓。开盘/收盘前后禁做T。"""
        now_bj = self._beijing_now()
        minutes_now = now_bj.hour * 60 + now_bj.minute
        regular_start = 21 * 60 + 30
        regular_end = 24 * 60

        minutes_since_open = minutes_now - regular_start
        minutes_to_close = regular_end - minutes_now
        return (
            minutes_since_open >= config.NO_TRADE_MINUTES and
            minutes_to_close > config.NO_TRADE_MINUTES
        )
    
    def analyze(self, quote: dict, volume_history: list = None) -> dict:
        """分析行情，返回交易建议"""
        self._ensure_daily_reset()

        if "error" in quote:
            return {"action": "ERROR", "reason": quote["error"]}
        
        price = quote.get("price")
        session = quote.get("session", "unknown")
        volume = quote.get("volume", 0)
        prev_close = quote.get("prev_close", 0)
        
        if not price:
            return {"action": "NO_DATA", "reason": "无价格数据"}
        
        # 睡觉/休市不监控
        if session in ["sleep", "closed"]:
            return {"action": "OFF", "reason": "非监控时段", "price": price}
        
        # ===== 计算每日基调 =====
        if config.DAILY_TONE_ENABLED:
            mstr_trend = quote.get("mstr_trend", {})
            tone_data = calculate_daily_tone(mstr_trend=mstr_trend)
            self.daily_tone = tone_data.get("tone", "neutral")
            self.tone_forward_bias = tone_data.get("forward_bias", 0.0)
            self.tone_reverse_bias = tone_data.get("reverse_bias", 0.0)
            self.tone_reason = tone_data.get("reason", "")
            self.tone_updated_at = datetime.now(timezone.utc).isoformat()
        
        # 盘前：低吸买入
        if session == "premarket":
            return self._premarket_analysis(quote)
        
        # 盘中：优先卖出跨时段仓位，再做T
        if session == "regular":
            # 优先检查跨时段仓位的卖出信号
            if self.holding_shares > 0 and self._is_cross_session_source(self.position_source):
                sell_signal = self._check_sell_target(quote)
                if sell_signal.get("action") == "SELL":
                    sell_signal["cross_session"] = True
                    sell_signal["source"] = self.position_source
                    return sell_signal
            
            # 检查盘中做T仓位
            if self.holding_shares > 0 and self.position_source == "regular":
                sell_signal = self._check_sell_target(quote)
                if sell_signal.get("action") == "SELL":
                    return sell_signal
            
            # 买入分析
            return self._regular_analysis(quote, volume_history)
        
        # 夜盘：低位买入
        if session == "overnight":
            result = self._overnight_analysis(quote)
            result["daily_tone"] = self.daily_tone
            result["tone_reason"] = self.tone_reason
            return result
        
        # 默认返回时也带上基调
        return {"action": "HOLD", "reason": "未知时段", "price": price,
                "daily_tone": self.daily_tone, "tone_reason": self.tone_reason}
    
    def _check_sell_target(self, quote: dict) -> dict:
        """检查是否到达卖出目标"""
        price = quote.get("price", 0)
        source_label = self._source_display_label(self.position_source)
        
        # 到达止盈价
        if self.target_price > 0 and price >= self.target_price:
            return {
                "action": "SELL",
                "price": round(price, 2),
                "shares": self.holding_shares,
                "buy_price": round(self.buy_price, 2),
                "target_price": round(self.target_price, 2),
                "profit_pct": round((price - self.buy_price) / self.buy_price * 100, 2),
                "reason": f"🎯 {source_label}到达目标价 ${self.target_price:.2f}，建议卖出",
                "signal_type": "TARGET_HIT"
            }
        
        # 到达止损价
        if self.stop_price > 0 and price <= self.stop_price:
            return {
                "action": "SELL",
                "price": round(price, 2),
                "shares": self.holding_shares,
                "buy_price": round(self.buy_price, 2),
                "stop_price": round(self.stop_price, 2),
                "loss_pct": round((price - self.buy_price) / self.buy_price * 100, 2),
                "reason": f"⛔ {source_label}触发止损 ${self.stop_price:.2f}，立即卖出",
                "signal_type": "STOP_LOSS"
            }
        
        # 跨时段仓位：盘中冲高也考虑卖出（宽松条件）
        if self._is_cross_session_source(self.position_source):
            change_from_buy = (price - self.buy_price) / self.buy_price
            # 盘中任何时间涨幅超过1%就提醒可以考虑卖出
            if change_from_buy >= 0.01:
                return {
                    "action": "SELL",
                    "price": round(price, 2),
                    "shares": self.holding_shares,
                    "buy_price": round(self.buy_price, 2),
                    "profit_pct": round(change_from_buy * 100, 2),
                    "reason": f"📊 {source_label}盘中浮盈{change_from_buy*100:+.1f}%，建议择机卖出",
                    "signal_type": "CROSS_SESSION_PROFIT"
                }
        
        return {"action": "HOLD", "reason": "继续持有"}
    
    def _premarket_analysis(self, quote: dict) -> dict:
        """盘前分析 - 低吸 + 追涨双策略。

        盘前是否值得在 MSTU 上下单，先看 MSTR 是否出现足够强的
        低开低吸 / 高开顺势 条件，再映射到 MSTU 的执行价格。
        """
        price = quote.get("price", 0)
        reference = self._get_reference_quote(quote)
        ref_price = reference.get("price", 0)
        ref_prev_close = reference.get("prev_close", 0)
        ref_symbol = reference.get("symbol", "MSTR")
        
        # 已有持仓则不重复买入
        if self.holding_shares > 0:
            return {
                "action": "PREMARKET",
                "price": round(price, 2),
                "reason": f"已有持仓{self.holding_shares}股，盘前不重复买入"
            }
        
        # 检查资金
        if self.available_cash < price * 50:
            return {
                "action": "PREMARKET",
                "price": round(price, 2),
                "reason": "可用资金不足"
            }
        
        gap_pct = (ref_price - ref_prev_close) / ref_prev_close if ref_prev_close else 0
        effective_dip_threshold = self._pct_with_forward_tone(config.PREMARKET_BUY_GAP_DOWN)
        effective_momentum_threshold = self._pct_with_forward_tone(config.PREMARKET_MOMENTUM_GAP_UP)
        signals = []
        mstr = quote.get("mstr", {})
        bull_structure_weak = mstr.get("mstr_bull_structure_weak", True)
        bull_structure_strong = mstr.get("mstr_bull_structure_strong", bull_structure_weak)
        long_trend_ok = bull_structure_weak
        momentum_ok = (
            mstr.get("mstr_ema_bullish", True)
            and mstr.get("mstr_macd_bullish", True)
            and mstr.get("mstr_vwap_momentum_ready", mstr.get("mstr_vwap_cross_up", True))
            and mstr.get("mstr_volume_expanding", True)
            and not mstr.get("mstr_gap_too_big", False)
            and bull_structure_weak
        )
        
        # ========== Pivot Points 分析（盘前）==========
        pivot_zone = "neutral"
        if ENHANCED_INDICATORS and ref_prev_close > 0:
            try:
                high_val = reference.get('high', ref_price)
                low_val = reference.get('low', ref_price)
                if high_val > 0 and low_val > 0:
                    pivots = calculate_pivot_points(high_val, low_val, ref_prev_close)
                    pivot_analysis = analyze_price_vs_levels(ref_price, pivots)
                    pivot_zone = pivot_analysis.get('zone', 'neutral')
                    # 接近支撑位增强低吸信心
                    for sig in pivot_analysis.get('signals', []):
                        if sig['type'] == 'support':
                            signals.append(f"🎯 接近{sig['level']}支撑(${sig['value']:.2f})")
                        elif sig['type'] == 'resistance':
                            signals.append(f"🎯 接近{sig['level']}阻力(${sig['value']:.2f})")
            except:
                pass
        
        # ========== 低吸模式 (Dip Buy) ==========
        if config.PREMARKET_BUY_ENABLED and gap_pct <= effective_dip_threshold:
            if not long_trend_ok and not mstr.get("mstr_rsi_bottom_rebound", False):
                signals.append("🧱 MSTR 牛熊线弱结构未建立，盘前低吸继续观察")
                return {
                    "action": "PREMARKET",
                    "price": round(price, 2),
                    "gap_pct": round(gap_pct * 100, 2),
                    "signals": signals,
                    "reason": f"盘前参考{ref_symbol}{gap_pct*100:+.1f}%，结构未转强"
                }
            buy_shares = max_affordable_shares(min(config.PREMARKET_MAX_BUY_AMT, self.available_cash), price, min_shares=50)
            if buy_shares >= 50:
                target = round(price * (1 + config.CROSS_SESSION_PROFIT_PCT), 2)
                stop = round(price * (1 - config.CROSS_SESSION_STOP_PCT), 2)
                signals.append(f"🟢 低吸: {ref_symbol}盘前低开{gap_pct*100:+.1f}%")
                
                # 急跌加仓
                strength = "强买入" if gap_pct <= effective_dip_threshold * 1.5 else "买入"
                
                return {
                    "action": "BUY",
                    "price": round(price, 2),
                    "shares": buy_shares,
                    "target_price": target,
                    "stop_price": stop,
                    "position_source": "premarket-dip",
                    "gap_pct": round(gap_pct * 100, 2),
                    "daily_tone": self.daily_tone,
                    "tone_reason": self.tone_reason,
                    "effective_dip_threshold_pct": round(effective_dip_threshold * 100, 2),
                    "signals": signals,
                    "reason": f"🟢 {strength}: {ref_symbol}盘前低开{gap_pct*100:+.1f}%，在MSTU买入{buy_shares}股，目标${target:.2f}"
                }
        
        # ========== 追涨模式 (Momentum) ==========
        if config.PREMARKET_MOMENTUM_ENABLED and gap_pct >= config.PREMARKET_MOMENTUM_MIN_GAP:
            # 涨幅过大不追
            if gap_pct <= config.MOMENTUM_MAX_CHASE_PCT:
                if not momentum_ok:
                    signals.append("🧱 MSTR 未满足 VWAP/量比/基础结构共振，盘前不追")
                    return {
                        "action": "PREMARKET",
                        "price": round(price, 2),
                        "gap_pct": round(gap_pct * 100, 2),
                        "signals": signals,
                        "reason": f"盘前参考{ref_symbol}{gap_pct*100:+.1f}%，但顺势条件不足"
                    }
                buy_shares = max_affordable_shares(min(config.MOMENTUM_MAX_BUY_AMT, self.available_cash), price, min_shares=50)
                if buy_shares >= 50:
                    # 涨幅达标触发
                    if gap_pct >= effective_momentum_threshold:
                        target = round(price * (1 + config.MOMENTUM_PROFIT_PCT), 2)
                        stop = round(price * (1 - config.MOMENTUM_STOP_PCT), 2)
                        signals.append(f"📈 追涨: {ref_symbol}盘前高开{gap_pct*100:+.1f}%，趋势延续")
                        
                        return {
                            "action": "BUY",
                            "price": round(price, 2),
                            "shares": buy_shares,
                            "target_price": target,
                            "stop_price": stop,
                            "position_source": "premarket-momentum",
                            "gap_pct": round(gap_pct * 100, 2),
                            "daily_tone": self.daily_tone,
                            "tone_reason": self.tone_reason,
                            "effective_momentum_threshold_pct": round(effective_momentum_threshold * 100, 2),
                            "signals": signals,
                            "reason": f"📈 追涨: {ref_symbol}盘前高开{gap_pct*100:+.1f}%，顺势在MSTU买入{buy_shares}股，快止盈${target:.2f}"
                        }
                    else:
                        # 涨幅不够强，观察
                        signals.append(f"📈 {ref_symbol}高开{gap_pct*100:+.1f}%，未达追涨阈值({effective_momentum_threshold*100:+.2f}%)")
            else:
                signals.append(f"⚠️ {ref_symbol}高开{gap_pct*100:+.1f}%，涨幅过大不追")
        
        # ========== 不满足任何买入条件 ==========
        return {
            "action": "PREMARKET",
            "price": round(price, 2),
            "gap_pct": round(gap_pct * 100, 2),
            "daily_tone": self.daily_tone,
            "tone_reason": self.tone_reason,
            "effective_dip_threshold_pct": round(effective_dip_threshold * 100, 2),
            "effective_momentum_threshold_pct": round(effective_momentum_threshold * 100, 2),
            "signals": signals,
            "reason": f"盘前参考{ref_symbol}{gap_pct*100:+.1f}%，无明确信号"
        }
    
    def _overnight_analysis(self, quote: dict) -> dict:
        """夜盘分析 - 低吸 + 追涨双策略。

        夜盘同样坚持“信号看 MSTR，执行落在 MSTU”。
        这样可以避免被杠杆 ETF 的放大噪音误导。
        """
        price = quote.get("price", 0)
        reference = self._get_reference_quote(quote)
        ref_price = reference.get("price", 0)
        ref_prev_close = reference.get("prev_close", 0)
        ref_symbol = reference.get("symbol", "MSTR")
        
        # 已有持仓则不重复买入
        if self.holding_shares > 0:
            return {
                "action": "OVERNIGHT",
                "price": round(price, 2),
                "reason": f"已有持仓{self.holding_shares}股，夜盘不重复买入"
            }
        
        # 检查资金
        if self.available_cash < price * 50:
            return {
                "action": "OVERNIGHT",
                "price": round(price, 2),
                "reason": "可用资金不足"
            }
        
        
        change_pct = (ref_price - ref_prev_close) / ref_prev_close if ref_prev_close else 0
        effective_dip_threshold = self._pct_with_forward_tone(config.OVERNIGHT_BUY_DROP)
        effective_momentum_threshold = self._pct_with_forward_tone(config.OVERNIGHT_MOMENTUM_RISE)
        signals = []
        mstr = quote.get("mstr", {})
        bull_structure_weak = mstr.get("mstr_bull_structure_weak", True)
        bull_structure_strong = mstr.get("mstr_bull_structure_strong", bull_structure_weak)
        long_trend_ok = bull_structure_weak
        momentum_ok = (
            mstr.get("mstr_ema_bullish", True)
            and mstr.get("mstr_macd_bullish", True)
            and mstr.get("mstr_vwap_momentum_ready", mstr.get("mstr_vwap_cross_up", True))
            and mstr.get("mstr_volume_expanding", True)
            and not mstr.get("mstr_gap_too_big", False)
            and bull_structure_weak
        )
        
        # ========== 低吸模式 (Dip Buy) ==========
        if config.OVERNIGHT_BUY_ENABLED and change_pct <= effective_dip_threshold:
            if not long_trend_ok and not mstr.get("mstr_rsi_bottom_rebound", False):
                signals.append("🧱 MSTR 牛熊线弱结构未建立，夜盘低吸继续等待")
                return {
                    "action": "OVERNIGHT",
                    "price": round(price, 2),
                    "change_pct": round(change_pct * 100, 2),
                    "signals": signals,
                    "reason": f"夜盘参考{ref_symbol}{change_pct*100:+.1f}%，结构未转强"
                }
            buy_shares = max_affordable_shares(min(config.OVERNIGHT_MAX_BUY_AMT, self.available_cash), price, min_shares=50)
            if buy_shares >= 50:
                target = round(price * (1 + config.CROSS_SESSION_PROFIT_PCT), 2)
                stop = round(price * (1 - config.CROSS_SESSION_STOP_PCT), 2)
                signals.append(f"🟢 低吸: {ref_symbol}夜盘跌{change_pct*100:+.1f}%")
                
                return {
                    "action": "BUY",
                    "price": round(price, 2),
                    "shares": buy_shares,
                    "target_price": target,
                    "stop_price": stop,
                    "position_source": "overnight-dip",
                    "change_pct": round(change_pct * 100, 2),
                    "daily_tone": self.daily_tone,
                    "tone_reason": self.tone_reason,
                    "effective_dip_threshold_pct": round(effective_dip_threshold * 100, 2),
                    "signals": signals,
                    "reason": f"🟢 低吸: {ref_symbol}夜盘跌{change_pct*100:+.1f}%，在MSTU买入{buy_shares}股，目标${target:.2f}"
                }
        
        
        # ========== 追涨模式 (Momentum) ==========
        if config.OVERNIGHT_MOMENTUM_ENABLED and change_pct >= config.OVERNIGHT_MOMENTUM_MIN_RISE:
            # 涨幅过大不追
            if change_pct <= config.MOMENTUM_MAX_CHASE_PCT:
                if not momentum_ok:
                    signals.append("🧱 MSTR 未满足 VWAP/量比/基础结构共振，夜盘不追")
                    return {
                        "action": "OVERNIGHT",
                        "price": round(price, 2),
                        "change_pct": round(change_pct * 100, 2),
                        "signals": signals,
                        "reason": f"夜盘参考{ref_symbol}{change_pct*100:+.1f}%，但顺势条件不足"
                    }
                buy_shares = max_affordable_shares(min(config.MOMENTUM_MAX_BUY_AMT, self.available_cash), price, min_shares=50)
                if buy_shares >= 50:
                    # 涨幅达标触发
                    if change_pct >= effective_momentum_threshold:
                        target = round(price * (1 + config.MOMENTUM_PROFIT_PCT), 2)
                        stop = round(price * (1 - config.MOMENTUM_STOP_PCT), 2)
                        signals.append(f"📈 追涨: {ref_symbol}夜盘涨{change_pct*100:+.1f}%，趋势延续")
                        
                        return {
                            "action": "BUY",
                            "price": round(price, 2),
                            "shares": buy_shares,
                            "target_price": target,
                            "stop_price": stop,
                            "position_source": "overnight-momentum",
                            "change_pct": round(change_pct * 100, 2),
                            "daily_tone": self.daily_tone,
                            "tone_reason": self.tone_reason,
                            "effective_momentum_threshold_pct": round(effective_momentum_threshold * 100, 2),
                            "signals": signals,
                            "reason": f"📈 追涨: {ref_symbol}夜盘涨{change_pct*100:+.1f}%，顺势在MSTU买入{buy_shares}股，快止盈${target:.2f}"
                        }
                    else:
                        # 涨幅不够强，观察
                        signals.append(f"📈 {ref_symbol}涨{change_pct*100:+.1f}%，未达追涨阈值({effective_momentum_threshold*100:+.2f}%)")
            else:
                signals.append(f"⚠️ {ref_symbol}涨{change_pct*100:+.1f}%，涨幅过大不追")
        
        
        # ========== 不满足任何买入条件 ==========
        if abs(change_pct) > 0.03:
            signals.append(f"波动{change_pct*100:+.1f}%")
        
        return {
            "action": "OVERNIGHT",
            "price": round(price, 2),
            "change_pct": round(change_pct * 100, 2),
            "daily_tone": self.daily_tone,
            "tone_reason": self.tone_reason,
            "effective_dip_threshold_pct": round(effective_dip_threshold * 100, 2),
            "effective_momentum_threshold_pct": round(effective_momentum_threshold * 100, 2),
            "signals": signals,
            "reason": f"夜盘参考{ref_symbol}{change_pct*100:+.1f}%，无明确信号"
        }
    
    def _regular_analysis(self, quote: dict, volume_history: list = None) -> dict:
        """盘中分析：做T核心时段。

        注意：
        - ref_* 变量来自 MSTR（若可用），用于判断是否值得开新仓/继续顺势。
        - price 变量来自 MSTU，用于给用户真实的成交参考和止盈止损。
        - 这里不要轻易改回“全部基于 MSTU 算指标”，否则会破坏当前策略假设。
        """
        price = quote.get("price", 0)
        reference = self._get_reference_quote(quote)
        prev_close = reference.get("prev_close", 0)
        high = reference.get("high", 0)
        low = reference.get("low", 0)
        volume = reference.get("volume", 0)
        ref_price = reference.get("price", price)
        ref_symbol = reference.get("symbol", "MSTR")
        
        # 检查限制
        if self.daily_ops_count >= config.MAX_LOTS_PER_DAY:
            return {"action": "HOLD", "reason": f"已达当日操作上限({config.MAX_LOTS_PER_DAY}次)", "price": price}
        
        if self.daily_pnl <= -config.DAILY_MAX_LOSS:
            return {"action": "HOLD", "reason": f"已达亏损上限(${config.DAILY_MAX_LOSS})", "price": price}
        
        # ========== 趋势过滤 ==========
        trend_signal, trend_score = self._analyze_trend(ref_price, prev_close)
        
        # ========== MSTR 底层信号 ==========
        mstr_signal = ""
        mstr_extra_signals = []
        mstr_score = {"buy": 0, "sell": 0}
        mstr_breakdown = {"buy": 0.0, "sell": 0.0, "macd_enhanced": {"buy": 0.0, "sell": 0.0}}
        mstr_trend_ok = True
        mstr_trend_note = ""
        
        # MACD/EMA/VWAP 详细状态（始终输出）
        macd_detail = ""
        ema_detail = ""
        vwap_detail = ""
        vol_detail = ""
        rsi_detail = ""
        kdj_detail = ""
        
        if "mstr" in quote:
            mstr = quote["mstr"]
            mstr_change = mstr.get("mstr_change_pct", 0)
            
            # MACD 详细状态
            macd_bullish = mstr.get("mstr_macd_bullish")
            macd_val = mstr.get("mstr_macd", 0)
            macd_signal_val = mstr.get("mstr_macd_signal", 0)
            macd_hist = mstr.get("mstr_macd_hist", 0)
            macd_status = "🟢MACD多头" if macd_bullish else ("🔴MACD空头" if macd_bullish is False else "⚪MACD")
            macd_detail = f"{macd_status}(DIF={macd_val:.2f}, DEA={macd_signal_val:.2f}, MACD={macd_hist*2:.2f})"
            
            # 均线(EMA) 详细状态
            ema_bullish = mstr.get("mstr_ema_bullish")
            ema_fast = mstr.get("mstr_ema_fast", 0)
            ema_slow = mstr.get("mstr_ema_slow", 0)
            ema_status = "🟢EMA多头" if ema_bullish else ("🔴EMA空头" if ema_bullish is False else "⚪EMA")
            ema_detail = f"{ema_status}(EMA{config.MSTR_FAST_EMA_PERIOD}={ema_fast:.2f}, EMA{config.MSTR_SLOW_EMA_PERIOD}={ema_slow:.2f})"
            
            # VWAP 均线详细状态
            vwap_val = mstr.get("mstr_vwap", 0)
            vwap_cross_up = mstr.get("mstr_vwap_cross_up", False)
            vwap_cross_down = mstr.get("mstr_vwap_cross_down", False)
            vwap_hold_above = mstr.get("mstr_vwap_hold_above", False)
            if vwap_val > 0:
                vwap_status = "🟢VWAP上方" if vwap_hold_above else ("🟢VWAP上穿" if vwap_cross_up else ("🔴VWAP下破" if vwap_cross_down else "🔴VWAP下方"))
                vwap_detail = f"{vwap_status}(${vwap_val:.2f})"
            
            # 量比详细状态
            vol_ratio = mstr.get("mstr_volume_ratio", 0)
            vol_expanding = mstr.get("mstr_volume_expanding", False)
            vol_detail = f"{'🟢放量' if vol_expanding else '⚪缩量'}(量比={vol_ratio:.1f})"
            
            # RSI 详细状态
            rsi_val = mstr.get("mstr_rsi", 0)
            rsi_detail = f"RSI={rsi_val:.0f}" if rsi_val > 0 else ""
            
            # KDJ 详细状态
            kdj_j = mstr.get("mstr_kdj_j", 0)
            kdj_turn = mstr.get("mstr_kdj_turn_bull", False)
            kdj_detail = f"{'🟢KDJ转多' if kdj_turn else '⚪KDJ'}(J={kdj_j:.0f})"
            
            # MSTR涨>2% → MSTU看多
            if mstr_change > 2:
                mstr_signal = f"📈 MSTR涨{mstr_change:+.1f}%，MSTU看多"
                mstr_score["buy"] += 2
                mstr_breakdown["buy"] += 2
            elif mstr_change > 1:
                mstr_signal = f"📊 MSTR涨{mstr_change:+.1f}%，偏多"
                mstr_score["buy"] += 1
                mstr_breakdown["buy"] += 1
            # MSTR跌>2% → MSTU看空
            elif mstr_change < -2:
                mstr_signal = f"📉 MSTR跌{mstr_change:.1f}%，MSTU看空"
                mstr_score["sell"] += 2
                mstr_breakdown["sell"] += 2
            elif mstr_change < -1:
                mstr_signal = f"📊 MSTR跌{mstr_change:.1f}%，偏空"
                mstr_score["sell"] += 1
                mstr_breakdown["sell"] += 1

            # 实时策略补齐回测里的趋势确认：
            # EMA / MACD 现在不再作为“硬门槛”，而是作为分时动能确认的一部分。
            # 日内做T更关注节奏是否启动，而不是中短趋势线必须全部完美对齐。
            if config.MSTR_TREND_FILTER_ENABLED:
                ema_bullish = mstr.get("mstr_ema_bullish")
                macd_bullish = mstr.get("mstr_macd_bullish")
                if ema_bullish is not None and macd_bullish is not None:
                    if ema_bullish and macd_bullish:
                        mstr_trend_ok = True
                        mstr_score["buy"] += 1.25
                        mstr_breakdown["buy"] += 1.25
                        mstr_trend_note = (
                            f"📐 MSTR趋势确认: EMA{config.MSTR_FAST_EMA_PERIOD}>{config.MSTR_SLOW_EMA_PERIOD}"
                            " 且 MACD 多头"
                        )
                    else:
                        mstr_trend_ok = False
                        mstr_score["sell"] += 0.5
                        mstr_breakdown["sell"] += 0.5
                        weak_parts = []
                        if not ema_bullish:
                            weak_parts.append(
                                f"EMA{config.MSTR_FAST_EMA_PERIOD}<={config.MSTR_SLOW_EMA_PERIOD}"
                            )
                        if not macd_bullish:
                            weak_parts.append("MACD 未转多")
                        mstr_trend_note = "📐 MSTR趋势未确认: " + " / ".join(weak_parts)

            # moomoo 精简指标接入：
            # 1. 牛熊线只提供趋势偏置
            # 2. VWAP + 量比 + MACD/KDJ/RSI 负责日内主触发
            # 3. K线形态只做辅助提示
            if mstr.get("mstr_bull_structure_strong"):
                mstr_score["buy"] += 0.75
                mstr_breakdown["buy"] += 0.75
                signals_hint = "🟨 MSTR强结构: 牛熊线持续走强且双线抬升"
            elif mstr.get("mstr_bull_structure_weak"):
                mstr_score["buy"] += 0.35
                mstr_breakdown["buy"] += 0.35
                signals_hint = "🟨 MSTR弱结构: 短线底轨站上长线底轨，价格站上长期牛线"
            else:
                mstr_score["sell"] += 0.5
                mstr_breakdown["sell"] += 0.5
                signals_hint = "🟦 MSTR结构偏弱: 牛熊线未完成有效上移"
            if mstr.get("mstr_vwap_momentum_ready") and mstr.get("mstr_volume_expanding") and not mstr.get("mstr_gap_too_big"):
                mstr_score["buy"] += 2.0
                mstr_breakdown["buy"] += 2.0
                if mstr.get("mstr_vwap_cross_up"):
                    signals_hint += f" | VWAP上穿 + 量比{mstr.get('mstr_volume_ratio', 0):.1f}"
                else:
                    signals_hint += (
                        f" | VWAP上方延续启动 + 量比{mstr.get('mstr_volume_ratio', 0):.1f}"
                    )
            elif mstr.get("mstr_vwap_cross_down"):
                mstr_score["sell"] += 1.5
                mstr_breakdown["sell"] += 1.5
                signals_hint += " | 跌回VWAP下方"
            if mstr.get("mstr_rsi_bottom_rebound"):
                mstr_score["buy"] += 0.75
                mstr_breakdown["buy"] += 0.75
                signals_hint += " | RSI底部反弹"
            if mstr.get("mstr_kdj_turn_bull"):
                mstr_score["buy"] += 1.0
                mstr_breakdown["buy"] += 1.0
                signals_hint += " | KDJ变盘转多"
            mstr_extra_signals.append(signals_hint)

            if config.MSTR_PATTERN_FILTER_ENABLED:
                pattern_signals = []
                if mstr.get("mstr_morning_star"):
                    # 形态只做辅助提示，不再主导评分。
                    mstr_score["buy"] += 0.25
                    mstr_breakdown["buy"] += 0.25
                    pattern_signals.append("🌅 早晨之星")
                if mstr.get("mstr_inside_bar_breakout_up"):
                    mstr_score["buy"] += 0.25
                    mstr_breakdown["buy"] += 0.25
                    pattern_signals.append("📈 孕线向上突破")
                if mstr.get("mstr_evening_star"):
                    mstr_score["sell"] += 0.25
                    mstr_breakdown["sell"] += 0.25
                    pattern_signals.append("🌇 黄昏之星")
                if mstr.get("mstr_inside_bar_breakout_down"):
                    mstr_score["sell"] += 0.25
                    mstr_breakdown["sell"] += 0.25
                    pattern_signals.append("📉 孕线向下突破")
                if pattern_signals:
                    mstr_extra_signals.append("🕯 MSTR形态辅助: " + " | ".join(pattern_signals))

            # ===== MACD增强信号（功能1/2/3）=====
            macd_div = mstr.get("mstr_macd_divergence", "none")
            macd_trend = mstr.get("mstr_macd_hist_trend", "neutral")
            macd_cross = mstr.get("mstr_macd_cross_position", "none")
            
            macd_detail_extra = []
            
            # 功能1: 顶背离/底背离
            if macd_div == "bottom":
                mstr_score["buy"] += 1.5
                mstr_breakdown["buy"] += 1.5
                mstr_breakdown["macd_enhanced"]["buy"] += 1.5
                macd_detail_extra.append("🎯 MACD底背离：价格新低但MACD未新低，反弹信号")
            elif macd_div == "top":
                mstr_score["sell"] += 1.5
                mstr_breakdown["sell"] += 1.5
                mstr_breakdown["macd_enhanced"]["sell"] += 1.5
                macd_detail_extra.append("⚠️ MACD顶背离：价格新高但MACD未新高，调整信号")
            
            # 功能2: 柱状图变化趋势
            if macd_trend == "green_shrinking":
                mstr_score["buy"] += 1.0
                mstr_breakdown["buy"] += 1.0
                mstr_breakdown["macd_enhanced"]["buy"] += 1.0
                macd_detail_extra.append("📊 MACD绿柱连续缩短：空头衰竭")
            elif macd_trend == "red_shrinking":
                mstr_score["sell"] += 1.0
                mstr_breakdown["sell"] += 1.0
                mstr_breakdown["macd_enhanced"]["sell"] += 1.0
                macd_detail_extra.append("📊 MACD红柱连续缩短：多头衰竭")
            elif macd_trend == "red_to_green":
                mstr_score["buy"] += 0.75
                mstr_breakdown["buy"] += 0.75
                mstr_breakdown["macd_enhanced"]["buy"] += 0.75
                macd_detail_extra.append("📊 MACD绿转红：金叉信号")
            elif macd_trend == "green_to_red":
                mstr_score["sell"] += 0.75
                mstr_breakdown["sell"] += 0.75
                mstr_breakdown["macd_enhanced"]["sell"] += 0.75
                macd_detail_extra.append("📊 MACD红转绿：死叉信号")
            
            # 功能3: 金叉/死叉位置判断
            if macd_cross == "above_zero_golden":
                mstr_score["buy"] += 1.5
                mstr_breakdown["buy"] += 1.5
                mstr_breakdown["macd_enhanced"]["buy"] += 1.5
                macd_detail_extra.append("📈 MACD零轴上方金叉：强买入信号")
            elif macd_cross == "below_zero_golden":
                mstr_score["buy"] += 0.75
                mstr_breakdown["buy"] += 0.75
                mstr_breakdown["macd_enhanced"]["buy"] += 0.75
                macd_detail_extra.append("📈 MACD零轴下方金叉：弱买入信号")
            elif macd_cross == "above_zero_dead":
                mstr_score["sell"] += 0.75
                mstr_breakdown["sell"] += 0.75
                mstr_breakdown["macd_enhanced"]["sell"] += 0.75
                macd_detail_extra.append("📉 MACD零轴上方死叉：弱卖出信号")
            elif macd_cross == "below_zero_dead":
                mstr_score["sell"] += 1.5
                mstr_breakdown["sell"] += 1.5
                mstr_breakdown["macd_enhanced"]["sell"] += 1.5
                macd_detail_extra.append("📉 MACD零轴下方死叉：强卖出信号")
            
            if macd_detail_extra:
                mstr_extra_signals.append("📐 MACD增强: " + " | ".join(macd_detail_extra))

        # ========== 量价分析 ==========
        volume_signal, volume_score = self._analyze_volume(ref_price, prev_close, volume, volume_history)
        
        # ========== 日内位置分析 ==========
        position_signal, position_score = self._analyze_price_position(ref_price, high, low)
        
        # ========== 增强技术指标 ==========
        enhanced_score = {'buy': 0, 'sell': 0}
        enhanced_signals = []
        if ENHANCED_INDICATORS:
            try:
                reference_quote = {
                    "price": ref_price,
                    "high": high,
                    "low": low,
                    "prev_close": prev_close,
                    "volume": volume,
                }
                enhanced = generate_enhanced_signals(reference_quote, volume_history)
                enhanced_signals = enhanced.get('signals', [])
                enhanced_score['buy'] = enhanced.get('buy_score', 0)
                enhanced_score['sell'] = enhanced.get('sell_score', 0)
            except:
                pass
        
        # ========== 综合判断 ==========
        signals = []
        signals.extend(trend_signal)
        signals.extend(volume_signal)
        signals.extend(position_signal)
        signals.extend(enhanced_signals)
        signals.extend(mstr_extra_signals)
        if mstr_signal:
            signals.append(mstr_signal)
        if mstr_trend_note:
            signals.append(mstr_trend_note)
        # MACD/EMA/VWAP/量比/RSI/KDJ 详细指标
        for detail in [ema_detail, macd_detail, vwap_detail, vol_detail, rsi_detail, kdj_detail]:
            if detail:
                signals.append(f"📐 {detail}")
        
        # MACD增强信号明细
        macd_div = mstr.get("mstr_macd_divergence", "none") if "mstr" in quote else "none"
        macd_trend = mstr.get("mstr_macd_hist_trend", "neutral") if "mstr" in quote else "neutral"
        macd_cross = mstr.get("mstr_macd_cross_position", "none") if "mstr" in quote else "none"
        
        if macd_div == "bottom":
            signals.append("📐 🎯MACD底背离")
        elif macd_div == "top":
            signals.append("📐 ⚠️MACD顶背离")
        
        if macd_trend == "green_shrinking":
            signals.append("📐 📊绿柱缩短(空头衰竭)")
        elif macd_trend == "red_shrinking":
            signals.append("📐 📊红柱缩短(多头衰竭)")
        elif macd_trend == "red_to_green":
            signals.append("📐 📊MACD绿转红(金叉)")
        elif macd_trend == "green_to_red":
            signals.append("📐 📊MACD红转绿(死叉)")
        
        if macd_cross == "above_zero_golden":
            signals.append("📐 📈零轴上方金叉")
        elif macd_cross == "below_zero_golden":
            signals.append("📐 📈零轴下方金叉")
        elif macd_cross == "above_zero_dead":
            signals.append("📐 📉零轴上方死叉")
        elif macd_cross == "below_zero_dead":
            signals.append("📐 📉零轴下方死叉")
        
        signals.append(f"🧭 信号参考{ref_symbol}，执行标的MSTU")
        
        buy_score = position_score.get('buy', 0) + volume_score.get('buy', 0) + enhanced_score.get('buy', 0) + mstr_score.get('buy', 0)
        sell_score = position_score.get('sell', 0) + volume_score.get('sell', 0) + enhanced_score.get('sell', 0) + mstr_score.get('sell', 0)
        buy_trigger_threshold = self._score_threshold_with_forward_tone(2.0)
        strong_buy_threshold = self._score_threshold_with_forward_tone(3.0)
        sell_trigger_threshold = self._score_threshold_with_reverse_tone(2.0)
        
        # 趋势过滤：下跌趋势降低买入信心
        if trend_score == 'down':
            buy_score = max(0, buy_score - 1)
            signals.append("📉 下跌趋势，谨慎买入")
        elif trend_score == 'up':
            buy_score += 0.5
            signals.append("📈 上升趋势")

        if config.MSTR_TREND_FILTER_ENABLED and not mstr_trend_ok:
            buy_score = max(0, buy_score - 0.5)
            signals.append("🧱 MSTR趋势未完全确认，但不直接阻断分时做T")
        
        # 判断行动
        action = "HOLD"
        result_update = {}
        
        # ========== 隔夜持仓处理 ==========
        if self.holding_shares > 0 and self.position_source in ["regular", ""]:
            # 昨天盘中买入今天还没卖 → 隔夜做T
            # 优先卖出条件放宽，尽快平仓释放资金
            profit_pct = (price - self.buy_price) / self.buy_price if self.buy_price > 0 else 0
            
            if price >= self.target_price:
                action = "SELL"
                result_update = {
                    "signal_type": "TARGET_HIT",
                    "buy_price": round(self.buy_price, 2),
                    "target_price": round(self.target_price, 2),
                    "stop_price": round(self.stop_price, 2),
                    "profit_pct": round(profit_pct * 100, 1),
                    "shares": self.holding_shares,
                    "cross_session": True
                }
            elif price <= self.stop_price:
                action = "SELL"
                result_update = {
                    "signal_type": "STOP_LOSS",
                    "buy_price": round(self.buy_price, 2),
                    "target_price": round(self.target_price, 2),
                    "stop_price": round(self.stop_price, 2),
                    "loss_pct": round(profit_pct * 100, 1),
                    "shares": self.holding_shares,
                    "cross_session": True
                }
            elif profit_pct >= 0.01:  # 浮盈1%以上，可以择机卖出
                sell_score += 1.5  # 隔夜仓加卖分，优先出
                signals.append(f"📋 隔夜持仓浮盈{profit_pct*100:+.1f}%，优先平仓")
            else:
                signals.append(f"📋 隔夜持仓浮盈{profit_pct*100:+.1f}%，等反弹出")
        
        # 买入条件：综合得分>=2，有资金，下跌趋势中需要更强信号
        if action != "SELL" and buy_score >= buy_trigger_threshold and self.available_cash >= price * 50:
            if self.holding_shares == 0:  # 盘中只有空仓才买入
                if not self._is_regular_trade_window_open():
                    action = "TIME_WINDOW_BLOCKED"
                    result_update = {
                        "signal_type": "NO_TRADE_WINDOW",
                        "blocked_reason": f"收盘前{config.NO_TRADE_MINUTES}分钟禁止新开仓"
                    }
                    signals.append(f"⏱ {result_update['blocked_reason']}")
                elif trend_score != 'down' or buy_score >= strong_buy_threshold:
                    action = "BUY"
        
        # 卖出条件：有持仓且到达目标
        if action != "SELL" and self.holding_shares > 0 and sell_score >= sell_trigger_threshold:
            action = "SELL"
        
        result = {
            "action": action,
            "price": round(price, 2),
            "signals": signals,
            "buy_score": round(buy_score, 1),
            "sell_score": round(sell_score, 1),
            "trend": trend_score,
            "mstr_signal": mstr_signal,
            "mstr_trend_note": mstr_trend_note,
            "mstr_trend_ok": mstr_trend_ok,
            "daily_tone": self.daily_tone,
            "tone_reason": self.tone_reason,
            "tone_forward_bias": self.tone_forward_bias,
            "tone_reverse_bias": self.tone_reverse_bias,
            "buy_trigger_threshold": round(buy_trigger_threshold, 2),
            "sell_trigger_threshold": round(sell_trigger_threshold, 2),
            "score_breakdown": {
                "position": position_score,
                "volume": volume_score,
                "enhanced": enhanced_score,
                "mstr": mstr_breakdown,
            },
            "decision_trace": [
                f"buy_score={round(buy_score, 2)} vs threshold={round(buy_trigger_threshold, 2)}",
                f"sell_score={round(sell_score, 2)} vs threshold={round(sell_trigger_threshold, 2)}",
                f"trend={trend_score}",
                f"daily_tone={self.daily_tone} forward_bias={self.tone_forward_bias} reverse_bias={self.tone_reverse_bias}",
                f"mstr_macd_buy={round(mstr_breakdown['macd_enhanced']['buy'], 2)} mstr_macd_sell={round(mstr_breakdown['macd_enhanced']['sell'], 2)}",
            ],
            "reason": " | ".join(signals) if signals else "正常波动"
        }
        
        # 合并隔夜持仓卖出信号
        if action in ["SELL", "TIME_WINDOW_BLOCKED", "HOLD"] and result_update:
            result.update(result_update)
        
        if action == "BUY":
            buy_shares = max_affordable_shares(min(config.MAX_TRADE_AMOUNT, self.available_cash), price, min_shares=50)
            result.update({
                "shares": buy_shares,
                "target_price": round(price * (1 + config.TAKE_PROFIT_PCT), 2),
                "stop_price": round(price * (1 - config.STOP_LOSS_PCT), 2),
                "position_source": "regular",
                "volume_signal": volume_signal[0] if volume_signal else ""
            })
        
        return result
    
    def _analyze_trend(self, price: float, prev_close: float) -> tuple:
        """趋势分析"""
        signals = []
        trend = 'neutral'
        
        if prev_close > 0:
            change_pct = (price - prev_close) / prev_close
            
            if change_pct < config.TREND_DOWN_THRESHOLD:
                trend = 'down'
                signals.append(f"📉 下跌趋势({change_pct*100:+.1f}%)")
            elif change_pct > 0.02:
                trend = 'up'
                signals.append(f"📈 上涨趋势({change_pct*100:+.1f}%)")
        
        return signals, trend
    
    def _analyze_volume(self, price: float, prev_close: float, 
                        volume: int, volume_history: list = None) -> tuple:
        """量价分析"""
        signals = []
        score = {'buy': 0, 'sell': 0}
        
        if volume <= 0:
            return signals, score
        
        high_volume_threshold = 50_000_000
        
        if prev_close > 0:
            price_change = (price - prev_close) / prev_close
            
            if volume > high_volume_threshold and price_change > 0:
                signals.append("📊 放量上涨，强势信号")
                score['buy'] += 1
            elif volume > high_volume_threshold and price_change < 0:
                signals.append("📊 放量下跌，注意风险")
                score['sell'] += 1
            elif volume < 20_000_000:
                if price_change < 0:
                    signals.append("📉 缩量下跌，可能见底")
                    score['buy'] += 1
                elif price_change > 0:
                    signals.append("📈 缩量上涨，动能不足")
                    score['sell'] += 0.5
        
        return signals, score
    
    def _analyze_price_position(self, price: float, high: float, low: float) -> tuple:
        """日内价格位置分析"""
        signals = []
        score = {'buy': 0, 'sell': 0}
        
        if high <= low:
            return signals, score
        
        day_range = high - low
        position = (price - low) / day_range
        position_pct = position * 100
        
        if position < 0.25:
            signals.append(f"💚 日内低点区({position_pct:.0f}%)")
            score['buy'] += 2
        elif position < 0.35:
            signals.append(f"💚 偏低位置({position_pct:.0f}%)")
            score['buy'] += 1
        elif position > 0.75:
            signals.append(f"💗 日内高点区({position_pct:.0f}%)")
            score['sell'] += 2
        elif position > 0.65:
            signals.append(f"💗 偏高位置({position_pct:.0f}%)")
            score['sell'] += 1
        else:
            signals.append(f"📊 中性位置({position_pct:.0f}%)")
        
        if low > 0 and abs(price - low) / low < config.SUPPORT_LEVEL_PCT:
            signals.append("🎯 接近日内支撑")
            score['buy'] += 1
        
        return signals, score
    
    def execute_buy(self, price: float, shares: int, source: str = "regular"):
        """执行买入"""
        fee_breakdown = estimate_fees(BUY, price=price, shares=shares)
        self.holding_shares += shares
        self.buy_price = price
        self.holding_cost_basis += fee_breakdown.gross_amount + fee_breakdown.total_fees
        self.position_source = source
        
        # 跨时段仓位用更保守的止盈止损
        if self._is_cross_session_source(source):
            self.target_price = round(price * (1 + config.CROSS_SESSION_PROFIT_PCT), 2)
            self.stop_price = round(price * (1 - config.CROSS_SESSION_STOP_PCT), 2)
        else:
            self.target_price = round(price * (1 + config.TAKE_PROFIT_PCT), 2)
            self.stop_price = round(price * (1 - config.STOP_LOSS_PCT), 2)
        
        self.available_cash -= fee_breakdown.gross_amount + fee_breakdown.total_fees
        self.daily_ops_count += 1
        self.daily_fees += fee_breakdown.total_fees
        self.cumulative_fees += fee_breakdown.total_fees
        
        # 记录跨时段仓位
        self.cross_session_positions.append({
            "shares": shares,
            "buy_price": price,
            "target_price": self.target_price,
            "stop_price": self.stop_price,
            "source": source,
            "bought_at": datetime.now(timezone.utc).isoformat()
        })
        
        self.save_position()
    
    def execute_sell(self, price: float, shares: int = None):
        """执行卖出"""
        sell_shares = shares or self.holding_shares
        fee_breakdown = estimate_fees(SELL, price=price, shares=sell_shares)
        avg_cost_basis = (self.holding_cost_basis / self.holding_shares) if self.holding_shares > 0 else 0.0
        allocated_cost_basis = avg_cost_basis * sell_shares
        profit = fee_breakdown.net_amount - allocated_cost_basis
        self.available_cash += fee_breakdown.net_amount
        self.holding_shares -= sell_shares
        self.daily_pnl += profit
        self.daily_fees += fee_breakdown.total_fees
        self.cumulative_fees += fee_breakdown.total_fees
        self.holding_cost_basis = max(self.holding_cost_basis - allocated_cost_basis, 0.0)
        
        if self.holding_shares <= 0:
            self.holding_shares = 0
            self.buy_price = 0
            self.holding_cost_basis = 0.0
            self.target_price = 0
            self.stop_price = 0
            self.position_source = ""
            self.cross_session_positions = []
        
        self.save_position()
        return profit


def format_trade_signal(signal: dict, strategy: TradingStrategy = None) -> str:
    """格式化交易信号"""
    action = signal.get("action", "UNKNOWN")
    price = signal.get("price", "N/A")
    source = signal.get("position_source", signal.get("source", ""))
    source_label = {"premarket-dip": "盘前低吸", "premarket-momentum": "盘前追涨", "overnight-dip": "夜盘低吸", "overnight-momentum": "夜盘追涨", "premarket": "盘前", "overnight": "夜盘", "regular": "盘中"}.get(source, "")
    cross_session = signal.get("cross_session", False)
    
    if action == "BUY":
        is_momentum = "momentum" in source
        strategy_type = "追涨" if is_momentum else "低吸" if "dip" in source else ""
        source_hint = f"（{source_label}）" if source_label and source != "regular" else "（盘中做T）"
        profit_pct = config.MOMENTUM_PROFIT_PCT if is_momentum else (config.CROSS_SESSION_PROFIT_PCT if source != "regular" else config.TAKE_PROFIT_PCT)
        stop_pct = config.MOMENTUM_STOP_PCT if is_momentum else (config.CROSS_SESSION_STOP_PCT if source != "regular" else config.STOP_LOSS_PCT)
        
        # 计算预估盈亏
        buy_price_val = float(price) if isinstance(price, (int, float, str)) else 0
        shares = signal.get('shares', 0)
        target_price_val = signal.get('target_price', 0)
        stop_price_val = signal.get('stop_price', 0)
        round_trip_profit = estimate_round_trip(buy_price_val, target_price_val, shares)
        round_trip_loss = estimate_round_trip(buy_price_val, stop_price_val, shares)
        estimated_profit = round_trip_profit["net_pnl"]
        estimated_loss = round_trip_loss["net_pnl"]
        estimated_buy_fee = round_trip_profit["buy"]["total_fees"]
        estimated_sell_fee = round_trip_profit["sell"]["total_fees"]
        
        lines = [
            f"🟢 **MSTU 买入建议{source_hint}**",
            f"",
            f"💰 价格: ${price}",
            f"📈 建议买入: {shares}股",
            f"🎯 目标价: ${target_price_val} (+{profit_pct*100:.1f}%)",
            f"⛔ 止损价: ${stop_price_val} (-{stop_pct*100:.1f}%)",
            f"💸 预估手续费: 买入${estimated_buy_fee:.2f} | 卖出约${estimated_sell_fee:.2f}",
            f"💵 预估净盈利: ${estimated_profit:+.2f} | 预估净亏损: ${estimated_loss:+.2f}",
            f"",
        ]
        
        if strategy and strategy.holding_shares > 0:
            existing_source = {"premarket-dip": "盘前低吸", "premarket-momentum": "盘前追涨", "overnight-dip": "夜盘低吸", "overnight-momentum": "夜盘追涨", "regular": "盘中仓"}.get(strategy.position_source, strategy.position_source)
            lines.extend([
                f"📦 当前持仓: {strategy.holding_shares}股 @ ${strategy.buy_price:.2f} [{existing_source}]",
                f"   目标: ${strategy.target_price:.2f} | 止损: ${strategy.stop_price:.2f}",
                ""
            ])
        
        lines.append(f"📍 信号: {signal.get('reason', '')}")
        
        # 加入技术指标明细
        indicators = signal.get('signals', [])
        if indicators:
            lines.append(f"📋 指标明细:")
            for i, ind in enumerate(indicators[:8], 1):
                lines.append(f"  {i}. {ind}")
        
        # MSTR 底层信号
        if signal.get('mstr_signal'):
            lines.append(f"📊 MSTR: {signal['mstr_signal']}")
        
        # 趋势和分数
        lines.append(f"📈 趋势: {signal.get('trend', 'neutral')} | 买分/卖分: {signal.get('buy_score', 0)}/{signal.get('sell_score', 0)}")
        
        lines.append("📌 分析基于MSTR正股 + MSTU行情")
        return "\n".join(lines)
    
    elif action == "SELL":
        signal_type = signal.get("signal_type", "")
        
        # 生成卖出交易ID
        from trade_confirmation import generate_trade_id, log_pending_trade
        sell_trade_id = generate_trade_id(signal)
        signal["trade_id"] = sell_trade_id
        signal["action"] = "SELL"
        signal["estimated_fees"] = estimate_fees(SELL, price=float(price), shares=int(signal.get("shares", 0))).total_fees
        
        # 记录卖出信号到 trade_log
        try:
            log_pending_trade(signal, sell_trade_id, agent_source="strategy")
        except:
            pass
        
        if signal_type == "TARGET_HIT":
            prefix = f"🎯 {source_label}仓到达目标价！" if cross_session else "🎯 到达目标价！"
            lines = [
                f"{prefix}",
                f"",
                f"💰 当前价: ${price}",
                f"📈 买入价: ${signal.get('buy_price', 0)}",
                f"🎯 目标价: ${signal.get('target_price', 0)}",
                f"💵 盈利: {signal.get('profit_pct', 0):+.1f}%",
                f"💸 预估卖出手续费: ${signal.get('estimated_fees', 0):.2f}",
                f"",
                f"💡 建议: 卖出 {signal['shares']}股 锁定利润",
                f"",
                f"📍 {signal.get('reason', '')}",
                f"",
                f"🔢 卖出ID: {sell_trade_id}",
                f"✅ 已卖出请回复\"已卖出\"或\"确认卖出\""
            ]
        elif signal_type == "STOP_LOSS":
            prefix = f"🚨 {source_label}仓触发止损！" if cross_session else "🚨 触发止损！"
            lines = [
                f"{prefix}",
                f"",
                f"💰 当前价: ${price}",
                f"📈 买入价: ${signal.get('buy_price', 0)}",
                f"⛔ 止损价: ${signal.get('stop_price', 0)}",
                f"💵 亏损: {signal.get('loss_pct', 0):+.1f}%",
                f"💸 预估卖出手续费: ${signal.get('estimated_fees', 0):.2f}",
                f"",
                f"⚠️ 建议: 立即卖出止损",
                f"",
                f"📍 {signal.get('reason', '')}",
                f"",
                f"🔢 卖出ID: {sell_trade_id}",
                f"✅ 已卖出请回复\"已卖出\"或\"确认卖出\""
            ]
        elif signal_type == "CROSS_SESSION_PROFIT":
            lines = [
                f"📊 **{source_label}仓盘中浮盈，建议卖出**",
                f"",
                f"💰 当前价: ${price}",
                f"📈 买入价: ${signal.get('buy_price', 0)}",
                f"💵 浮盈: {signal.get('profit_pct', 0):+.1f}%",
                f"💸 预估卖出手续费: ${signal.get('estimated_fees', 0):.2f}",
                f"",
                f"💡 盘前/夜盘建仓，盘中冲高可择机卖出",
                f"",
                f"📍 {signal.get('reason', '')}",
                f"",
                f"🔢 卖出ID: {sell_trade_id}",
                f"✅ 已卖出请回复\"已卖出\""
            ]
        else:
            lines = [
                "🔴 **MSTU 做T建议 - 卖出**",
                f"",
                f"💰 价格: ${price}",
                f"📉 建议卖出: {signal.get('shares', '全部')}股",
                f"",
                f"📍 {signal.get('reason', '')}",
            ]
        
        # 卖出信号也加指标明细
        indicators = signal.get('signals', [])
        if indicators:
            lines.append(f"📋 指标明细:")
            for i, ind in enumerate(indicators[:6], 1):
                lines.append(f"  {i}. {ind}")
        
        lines.extend(["", f"🔢 卖出ID: {sell_trade_id}", f"✅ 已卖出请回复\"已卖出\""])
        return "\n".join(lines)
    
    elif action == "PREMARKET":
        gap = signal.get('gap_pct', 0)
        buy_hint = ""
        if abs(gap) >= abs(config.PREMARKET_BUY_GAP_DOWN * 100):
            buy_hint = "\n💡 满足盘前买入条件，等待买入信号"
        
        indicators = signal.get('signals', [])
        ind_lines = ""
        if indicators:
            ind_lines = f"\n📋 指标明细:\n" + "\n".join(f"  {i}. {ind}" for i, ind in enumerate(indicators[:6], 1))
        
        return f"""🌅 **MSTU 盘前观察**

💰 价格: ${price}
📊 跳空: {gap:+.1f}%
📈 趋势: {signal.get('trend', 'neutral')} | 买分/卖分: {signal.get('buy_score', 0)}/{signal.get('sell_score', 0)}
📍 {signal['reason']}{ind_lines}{buy_hint}"""
    
    elif action == "OVERNIGHT":
        change = signal.get('change_pct', 0)
        alert = "⚠️ " if abs(change) > 3 else ""
        buy_hint = ""
        if change <= config.OVERNIGHT_BUY_DROP * 100:
            buy_hint = "\n💡 满足夜盘买入条件，等待买入信号"
        
        indicators = signal.get('signals', [])
        ind_lines = ""
        if indicators:
            ind_lines = f"\n📋 指标明细:\n" + "\n".join(f"  {i}. {ind}" for i, ind in enumerate(indicators[:6], 1))
        
        return f"""🌙 **MSTU 夜盘监控**

💰 价格: ${price}
📊 波动: {change:+.1f}%
📈 趋势: {signal.get('trend', 'neutral')} | 买分/卖分: {signal.get('buy_score', 0)}/{signal.get('sell_score', 0)}
{alert}{signal['reason']}{ind_lines}{buy_hint}"""

    elif action == "TIME_WINDOW_BLOCKED":
        blocked_reason = signal.get("blocked_reason", "当前时段不允许新开仓")
        indicators = signal.get('signals', [])
        mstr_signal = signal.get('mstr_signal', '')
        trend = signal.get('trend', 'neutral')
        lines = [
            f"⏱ **MSTU 信号已识别，但当前不执行**",
            f"",
            f"💰 价格: ${price}",
            f"📍 原因: {blocked_reason}",
            f"📊 买分/卖分: {signal.get('buy_score', 0)}/{signal.get('sell_score', 0)}",
            f"📈 趋势: {trend}",
        ]
        if indicators:
            lines.append(f"📋 指标明细:")
            for i, ind in enumerate(indicators[:8], 1):
                lines.append(f"  {i}. {ind}")
        if mstr_signal:
            lines.append(f"📊 MSTR: {mstr_signal}")
        lines.extend(["", "💡 当前仅禁止新开仓，已有持仓的止盈止损不受影响"])
        return "\n".join(lines)
    
    elif action in ["SLEEP", "CLOSED", "OFF"]:
        return None
    
    else:
        signals = signal.get('signals', [])
        mstr_signal = signal.get('mstr_signal', '')
        trend = signal.get('trend', 'neutral')
        buy_score = signal.get('buy_score', 0)
        sell_score = signal.get('sell_score', 0)
        lines = [
            f"📊 买分/卖分: {buy_score}/{sell_score}",
            f"📈 趋势: {trend}",
        ]
        if signals:
            lines.append(f"📋 指标明细:")
            for i, s in enumerate(signals[:8], 1):
                lines.append(f"  {i}. {s}")
        if mstr_signal:
            lines.append(f"📊 MSTR: {mstr_signal}")
        lines.extend(["", f"📍 {signal.get('reason', '继续监控')}"])
        return "\n".join(lines)

if __name__ == "__main__":
    strategy = TradingStrategy()
    test_quote = {
        "price": 6.50, 
        "prev_close": 7.27, 
        "high": 7.00, 
        "low": 6.20,
        "volume": 60_000_000,
        "session": "regular"
    }
    signal = strategy.analyze(test_quote)
    print(format_trade_signal(signal, strategy))
