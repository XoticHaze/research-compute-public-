"""Public Actions read-only IBKR probe log privacy guard.

ib_insync can emit production account identifiers in its logger during API
timeouts before caller exception handlers run. Never install in the canonical
private bot or its durable execution/ledger process.
"""
from __future__ import annotations

import logging
import re
import sys


def install() -> None:
    """Suppress upstream logger payloads and publish exception type only."""
    logging.disable(logging.CRITICAL)

    def safe_excepthook(exc_type, _exc, _tb) -> None:
        name = getattr(exc_type, "__name__", "Unknown")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", name):
            name = "Unknown"
        print("MMIBKR_PUBLIC_BROKER_EXCEPTION_CLASS=" + name, file=sys.stderr, flush=True)

    sys.excepthook = safe_excepthook
