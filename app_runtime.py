"""Compatibility wrapper for legacy imports."""

import sys as _sys

from mstu_trading import app_runtime as _impl

_sys.modules[__name__] = _impl

