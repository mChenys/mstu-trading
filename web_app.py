"""Compatibility wrapper for legacy imports."""

import os
import sys as _sys

from mstu_trading.web import app as _impl

if __name__ == "__main__":
    port = int(os.environ.get("WEB_APP_PORT", "5000"))
    _impl.app.run(host="127.0.0.1", port=port, debug=False)
else:
    _sys.modules[__name__] = _impl
