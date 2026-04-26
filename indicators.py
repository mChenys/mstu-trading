"""Compatibility wrapper for legacy imports."""

import sys as _sys

from mstu_trading.strategy import indicators as _impl

_sys.modules[__name__] = _impl

