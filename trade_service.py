"""Compatibility wrapper for legacy imports."""

import sys as _sys

from mstu_trading.trading import service as _impl

_sys.modules[__name__] = _impl
