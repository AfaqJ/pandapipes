"""
Hook installation — intercepts Python and IPython exceptions without
modifying pandapipes or the user's exception flow.
"""

from __future__ import annotations

import sys
from types import TracebackType
from typing import Type

from pandapipes.explain.core.config import get_config
from pandapipes.explain.core import log_capture

# The hook that was active BEFORE we installed ours. Captured in install()
# (not at module import time) so we don't race with pytest / Sentry / IPython
# hooks that may be installed after import but before enable().
_saved_excepthook = None
_installed = False


def _hook(
    exc_type: Type[BaseException],
    exc_value: BaseException,
    exc_tb: TracebackType | None,
) -> None:
    """Replacement sys.excepthook — shows original error then explains."""
    # 1. Always delegate to the hook that was active when we installed.
    if _saved_excepthook is not None:
        _saved_excepthook(exc_type, exc_value, exc_tb)
    else:
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    # 2. Only explain if we are enabled.
    if not get_config().enabled:
        return

    # 3. Skip KeyboardInterrupt and SystemExit — not user errors.
    if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
        return

    # 4. Explain — wrapped so we can NEVER crash the user's program.
    try:
        from pandapipes.explain.core import dispatcher
        dispatcher.handle(exc_type, exc_value, exc_tb)
    except Exception:
        pass


def install() -> None:
    """Install the global exception hook and, if available, the IPython hook."""
    global _saved_excepthook, _installed
    if _installed:
        return  # idempotent — no double-registration
    _saved_excepthook = sys.excepthook  # capture whoever is live RIGHT NOW
    _installed = True
    get_config().enabled = True
    log_capture.install()
    sys.excepthook = _hook
    _try_install_ipython_hook()


def uninstall() -> None:
    """Restore the exception hook that was active before install()."""
    global _saved_excepthook, _installed
    if not _installed:
        return
    get_config().enabled = False
    log_capture.uninstall()
    sys.excepthook = _saved_excepthook if _saved_excepthook is not None else sys.__excepthook__
    _saved_excepthook = None
    _installed = False


def _try_install_ipython_hook() -> None:
    """Register with IPython/Jupyter if running inside one."""
    # `get_ipython` is only injected into IPython's own exec namespace, not into
    # arbitrary imported modules — so we have to import it explicitly instead of
    # calling it as a builtin. ImportError means IPython isn't installed; a
    # None return means IPython is installed but we're not running inside it.
    try:
        from IPython.core.getipython import get_ipython
        ip = get_ipython()
        if ip is not None:
            ip.set_custom_exc((Exception,), _ipython_handler)
    except Exception:
        pass


def _ipython_handler(shell, etype, evalue, tb, tb_offset=None):
    """IPython-compatible exception handler."""
    # Show the normal IPython traceback first.
    shell.showtraceback((etype, evalue, tb), tb_offset=tb_offset)

    if not get_config().enabled:
        return None

    if issubclass(etype, (KeyboardInterrupt, SystemExit)):
        return None

    try:
        from pandapipes.explain.core import dispatcher
        dispatcher.handle(etype, evalue, tb)
    except Exception:
        pass

    return None
