"""Compatibility wrapper for legacy imports."""

import sys as _sys

from mstu_trading.strategy import indicators_enhanced as _impl

_sys.modules[__name__] = _impl

