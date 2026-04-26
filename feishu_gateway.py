"""Compatibility wrapper for legacy imports."""

import sys as _sys

from mstu_trading.integrations import feishu_gateway as _impl

_sys.modules[__name__] = _impl
