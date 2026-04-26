"""Unified trading fee model for MSTU T-trading workflows.

The system mainly trades U.S. NMS stocks such as MSTU, so the default fee
stack models the broker fees that apply to U.S. equity orders. Malaysia stamp
duty is kept as an explicit optional field and defaults to disabled because its
applicability/currency conversion depends on account and market setup.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math


BUY = "BUY"
SELL = "SELL"

COMMISSION_RATE = 0.0003
COMMISSION_MIN = 0.01
PLATFORM_FEE_PER_ORDER = 0.99
SETTLEMENT_FEE_PER_SHARE = 0.003
SETTLEMENT_FEE_MAX_RATE = 0.01
SEC_FEE_RATE = 0.0000206
SEC_FEE_MIN = 0.01
TAF_FEE_PER_SHARE = 0.000195
TAF_FEE_MIN = 0.01
TAF_FEE_MAX = 9.79
STAMP_DUTY_PER_BLOCK = 1.0
STAMP_DUTY_BLOCK_SIZE = 1000.0
STAMP_DUTY_MAX = 1000.0


@dataclass(frozen=True)
class FeeBreakdown:
    side: str
    shares: int
    price: float
    gross_amount: float
    commission: float
    platform_fee: float
    settlement_fee: float
    sec_fee: float
    taf_fee: float
    stamp_duty: float
    total_fees: float
    net_amount: float

    def to_dict(self) -> dict:
        return asdict(self)


def _round_money(value: float) -> float:
    return round(value + 1e-12, 2)


def _stamp_duty(
    gross_amount: float,
    *,
    enabled: bool = False,
    notional_to_stamp_currency_fx: float | None = None,
) -> float:
    """Optional stamp duty.

    If enabled, caller must provide the FX used to translate USD notional into
    the stamp-duty currency. Without that input, the safest behavior is to keep
    the charge at zero instead of inventing a conversion.
    """
    if not enabled or notional_to_stamp_currency_fx is None or notional_to_stamp_currency_fx <= 0:
        return 0.0
    converted_notional = gross_amount * notional_to_stamp_currency_fx
    blocks = math.ceil(converted_notional / STAMP_DUTY_BLOCK_SIZE)
    stamp_in_local = min(blocks * STAMP_DUTY_PER_BLOCK, STAMP_DUTY_MAX)
    return stamp_in_local / notional_to_stamp_currency_fx


def _default_stamp_settings() -> tuple[bool, float | None]:
    try:
        import mstu_trading.config as config

        return (
            bool(getattr(config, "STAMP_DUTY_ENABLED", False)),
            float(getattr(config, "STAMP_DUTY_USD_TO_RM_FX", 0.0) or 0.0),
        )
    except Exception:
        return (False, None)


def estimate_fees(
    side: str,
    *,
    price: float,
    shares: int,
    stamp_duty_enabled: bool | None = None,
    stamp_duty_fx: float | None = None,
) -> FeeBreakdown:
    side = (side or "").upper()
    shares = max(int(shares), 0)
    price = float(price or 0.0)
    gross_amount = price * shares

    if side not in {BUY, SELL} or shares <= 0 or price <= 0:
        return FeeBreakdown(
            side=side or BUY,
            shares=shares,
            price=price,
            gross_amount=_round_money(gross_amount),
            commission=0.0,
            platform_fee=0.0,
            settlement_fee=0.0,
            sec_fee=0.0,
            taf_fee=0.0,
            stamp_duty=0.0,
            total_fees=0.0,
            net_amount=_round_money(gross_amount if side == SELL else -gross_amount),
        )

    if stamp_duty_enabled is None:
        default_enabled, default_fx = _default_stamp_settings()
        stamp_duty_enabled = default_enabled
        if stamp_duty_fx is None:
            stamp_duty_fx = default_fx

    commission = max(gross_amount * COMMISSION_RATE, COMMISSION_MIN)
    platform_fee = PLATFORM_FEE_PER_ORDER
    settlement_fee = min(shares * SETTLEMENT_FEE_PER_SHARE, gross_amount * SETTLEMENT_FEE_MAX_RATE)
    sec_fee = max(gross_amount * SEC_FEE_RATE, SEC_FEE_MIN) if side == SELL else 0.0
    taf_fee = min(max(shares * TAF_FEE_PER_SHARE, TAF_FEE_MIN), TAF_FEE_MAX) if side == SELL else 0.0
    stamp_duty = _stamp_duty(
        gross_amount,
        enabled=stamp_duty_enabled,
        notional_to_stamp_currency_fx=stamp_duty_fx,
    )
    total_fees = commission + platform_fee + settlement_fee + sec_fee + taf_fee + stamp_duty
    if side == BUY:
        net_amount = -(gross_amount + total_fees)
    else:
        net_amount = gross_amount - total_fees

    return FeeBreakdown(
        side=side,
        shares=shares,
        price=price,
        gross_amount=_round_money(gross_amount),
        commission=_round_money(commission),
        platform_fee=_round_money(platform_fee),
        settlement_fee=_round_money(settlement_fee),
        sec_fee=_round_money(sec_fee),
        taf_fee=_round_money(taf_fee),
        stamp_duty=_round_money(stamp_duty),
        total_fees=_round_money(total_fees),
        net_amount=_round_money(net_amount),
    )


def estimate_buy_total(price: float, shares: int) -> float:
    fee = estimate_fees(BUY, price=price, shares=shares)
    return fee.gross_amount + fee.total_fees


def estimate_sell_net(price: float, shares: int) -> float:
    return estimate_fees(SELL, price=price, shares=shares).net_amount


def max_affordable_shares(cash_limit: float, price: float, *, min_shares: int = 1) -> int:
    cash_limit = float(cash_limit or 0.0)
    price = float(price or 0.0)
    min_shares = max(int(min_shares), 1)
    if cash_limit <= 0 or price <= 0:
        return 0

    # Start with a simple bound, then walk down until fees fit inside the cap.
    shares = max(int(cash_limit / price), 0)
    while shares >= min_shares:
        buy_fee = estimate_fees(BUY, price=price, shares=shares)
        if buy_fee.gross_amount + buy_fee.total_fees <= cash_limit + 1e-9:
            return shares
        shares -= 1
    return 0


def estimate_round_trip(entry_price: float, exit_price: float, shares: int) -> dict:
    entry = estimate_fees(BUY, price=entry_price, shares=shares)
    exit_trade = estimate_fees(SELL, price=exit_price, shares=shares)
    pnl = _round_money(exit_trade.net_amount - (entry.gross_amount + entry.total_fees))
    return {
        "buy": entry.to_dict(),
        "sell": exit_trade.to_dict(),
        "net_pnl": pnl,
    }
