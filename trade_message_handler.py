"""Compatibility wrapper for legacy imports."""

import sys as _sys

from mstu_trading.trading import message_handler as _impl

_sys.modules[__name__] = _impl
