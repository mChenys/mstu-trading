"""Compatibility wrapper for legacy imports."""

import sys as _sys

from mstu_trading.trading import execution_notifier as _impl

_sys.modules[__name__] = _impl
