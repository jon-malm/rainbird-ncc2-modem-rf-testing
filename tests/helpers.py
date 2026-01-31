"""
Test helper utilities.

Plain functions (not fixtures) for common test operations.
"""

import logging

logger = logging.getLogger(__name__)


def safe_cleanup(*callables):
    """Execute each callable, suppressing any exceptions.

    Used for best-effort cleanup where failure should not mask test results.

    Args:
        *callables: Functions to call. Each is called with no arguments.
                    Exceptions are logged at DEBUG level and suppressed.

    Example::

        safe_cleanup(lte1.deactivate_cell, lte2.deactivate_cell)
    """
    for fn in callables:
        try:
            fn()
        except Exception:
            logger.debug("Cleanup call %s failed (suppressed)", fn)
