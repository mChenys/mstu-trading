"""Compatibility wrapper for legacy imports."""

import runpy as _runpy

if __name__ == "__main__":
    _runpy.run_module("mstu_trading.integrations.webhook_daemon", run_name="__main__")
else:
    import sys as _sys
    from mstu_trading.integrations import webhook_daemon as _impl

    _sys.modules[__name__] = _impl
