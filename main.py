"""Compatibility entrypoint for realtime scan."""

import runpy as _runpy

if __name__ == "__main__":
    _runpy.run_module("mstu_trading.strategy.realtime", run_name="__main__")
else:
    import sys as _sys
    from mstu_trading.strategy import realtime as _impl

    _sys.modules[__name__] = _impl
