"""Compatibility wrapper for legacy imports."""

import sys as _sys

from mstu_trading.storage import sqlite_storage as _impl

_sys.modules[__name__] = _impl

