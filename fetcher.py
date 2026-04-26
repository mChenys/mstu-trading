"""Compatibility wrapper for legacy imports."""

import sys as _sys

from mstu_trading.market_data import fetcher as _impl

if __name__ == "__main__":
    print(f"当前时段: {_impl.get_session_type()}")
    quote = _impl.get_mstu_quote()
    print(_impl.format_price_info(quote))
else:
    _sys.modules[__name__] = _impl
