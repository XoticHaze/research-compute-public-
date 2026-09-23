from __future__ import annotations

"""Chronology-enabled entrypoint for the canonical MM-IBKR workload dispatcher.

This is a narrow release adapter: it preserves the canonical dispatcher's validation,
execution, authority, caching, and receipt contracts while extending only the
sanitized CRW result with bounded aggregate chronology folds. Raw timestamped rows
remain inside the trusted process boundary.
"""

from typing import Any

from scripts import mmibkr_canonical_workload_dispatch_v1 as canonical
from scripts.crw_chronology_fold_receipt_v1 import chronology_fold_receipt


_ORIGINAL_SANITIZE = canonical.sanitize_crw_result


def sanitize_crw_result(raw: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    result = _ORIGINAL_SANITIZE(raw, args)
    rows = raw.get("trade_rows") or []
    result["chronology_folds"] = chronology_fold_receipt(rows, fold_count=4)
    return result


def install() -> None:
    """Install the bounded sanitizer extension for this process only."""
    canonical.sanitize_crw_result = sanitize_crw_result


def main() -> int:
    install()
    return canonical.main()


if __name__ == "__main__":
    raise SystemExit(main())
