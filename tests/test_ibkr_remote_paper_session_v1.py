import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from ibkr_remote_paper_session_v1 import build_receipt


def runtime():
    return {
        "mode": "session_reconcile",
        "mmibkr_repository": "XoticHaze/mm-IBKR",
        "mmibkr_head": "a" * 40,
        "source_archive_sha256": "b" * 64,
        "paper_only": True,
        "read_only_api": "yes",
        "host_dependency": False,
        "live_trading_change": False,
    }


def test_ready_requires_one_du_paper_account_and_broker_reads():
    out = build_receipt(
        run_id="123", job="consume", public_head="c" * 40, runtime=runtime(),
        health=(200, {"ok": True}),
        open_orders=(200, {"ok": True, "open_order_count": 0, "unresolved_open_order_count": 0, "account_identity": {"managed_account_count": 1, "du_account_count": 1, "selected_account_is_paper_du": True}}),
        positions=(200, {"ok": True, "position_count": 0}),
    )
    assert out["ok"] is True
    assert out["side_effects"]["broker_order_placed"] is False
    assert out["secrets_published"] is False


def test_nonpaper_account_fails_closed():
    out = build_receipt(
        run_id="123", job="consume", public_head="c" * 40, runtime=runtime(),
        health=(200, {"ok": True}),
        open_orders=(200, {"ok": True, "account_identity": {"managed_account_count": 1, "du_account_count": 0, "selected_account_is_paper_du": False}}),
        positions=(200, {"ok": True}),
    )
    assert out["ok"] is False
    assert out["status"] == "REMOTE_PAPER_SESSION_NOT_READY"
