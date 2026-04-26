"""Compatibility wrapper for legacy imports."""

import sys as _sys

from mstu_trading import config as _impl

_sys.modules[__name__] = _impl

