import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ibkr_remote_paper_submit_v2 as r2


def runtime():
    return {
        "mode": "paper_submit_proof",
        "read_only_api": "no",
        "paper_only": True,
        "live_trading_change": False,
        "cleanup": {
            "cancel_open_order": True,
            "flatten_filled_position": True,
            "require_zero_baseline": True,
            "allow_global_cancel": False,
        },
        "mmibkr_repository": "XoticHaze/mm-IBKR",
        "mmibkr_head": "a" * 40,
        "source_archive_sha256": "b" * 64,
    }


def request():
    return {"canonical_submit_payload": {"symbol": "AMAT", "action": "BUY", "quantity": 1, "order_type": "LMT", "limit_price": 1.0}}


def test_validate_is_bounded():
    out = r2.validate_submit_request(request())
    assert out["action"] == "BUY" and out["quantity"] == 1 and out["order_type"] == "LMT"
    assert out["operator_approved"] is True
    assert out["allow_market_order"] is False
    for bad in [
        {"symbol": "AMAT", "action": "SELL", "quantity": 1, "order_type": "LMT", "limit_price": 1},
        {"symbol": "AMAT", "action": "BUY", "quantity": 2, "order_type": "LMT", "limit_price": 1},
        {"symbol": "AMAT", "action": "BUY", "quantity": 1, "order_type": "MKT", "limit_price": 1},
    ]:
        with pytest.raises(RuntimeError):
            r2.validate_submit_request({"canonical_submit_payload": bad})


def test_exact_identity_requires_one_order_id():
    with pytest.raises(RuntimeError):
        r2.exact_order_identity({"broker_submit": {"order": {}}}, "AMAT")
    out = r2.exact_order_identity({"broker_submit": {"order": {"orderId": 12, "permId": 34, "orderRef": "X"}}}, "AMAT")
    assert out["order_id"] == 12 and out["order_ref"] == "X"


def test_nonzero_baseline_blocks_before_submit(monkeypatch):
    calls = []

    def fake(base, path, **kw):
        calls.append(path)
        if path == r2.OPEN_ORDERS_PATH:
            return 200, {"ok": True, "matched_count": 0, "orders": []}
        if path == r2.POSITION_PATH:
            return 200, {"ok": True, "position_read_error": None, "flatten_candidates": [{"symbol": "AMAT", "position": 1.0}]}
        raise AssertionError(path)

    monkeypatch.setattr(r2, "_request", fake)
    out = r2.execute("http://x", runtime(), request(), run_id="1", job="j", public_head="c" * 40)
    assert not out["ok"] and out["status"] == "BASELINE_BLOCKED"
    assert r2.SUBMIT_PATH not in calls


def test_unfilled_order_is_cancelled_by_exact_id(monkeypatch):
    open_calls = 0

    def fake(base, path, **kw):
        nonlocal open_calls
        if path == r2.OPEN_ORDERS_PATH:
            open_calls += 1
            if open_calls == 1:
                return 200, {"ok": True, "matched_count": 0, "orders": []}
            if open_calls == 2:
                return 200, {"ok": True, "matched_count": 1, "orders": [{"orderId": 77, "unresolved": True}]}
            return 200, {"ok": True, "matched_count": 0, "orders": []}
        if path == r2.POSITION_PATH:
            return 200, {"ok": True, "position_read_error": None, "flatten_candidates": []}
        if path == r2.SUBMIT_PATH:
            return 200, {
                "ok": True,
                "status": "submitted",
                "place_order_called": True,
                "broker_order_placed": True,
                "broker_submit": {"order": {"orderId": 77, "permId": 88, "orderRef": "R"}, "order_status": {"status": "Submitted", "filled": 0, "remaining": 1}},
                "open_trades_after_for_ref": [{"order": {"orderId": 77, "permId": 88, "orderRef": "R"}}],
                "post_submit": {},
            }
        if path == r2.CANCEL_PATH:
            payload = kw["payload"]
            assert payload["order_id"] == 77 and payload["symbol"] == "AMAT" and payload["require_symbol_match"] is True
            return 200, {"ok": True, "post_cancel_remaining_matched_count": 0}
        raise AssertionError(path)

    monkeypatch.setattr(r2, "_request", fake)
    out = r2.execute("http://x", runtime(), request(), run_id="1", job="j", public_head="c" * 40)
    assert out["ok"] and out["status"] == "PAPER_SUBMIT_AND_CLEANUP_PROVEN"
    assert out["cleanup"]["exact_order_cancel_attempted"] is True
    assert out["cleanup"]["exact_order_cancel_reconciled"] is True
    assert out["cleanup"]["flatten_symbol_attempted"] is False
    assert out["cleanup"]["global_cancel_called"] is False


def test_fill_from_zero_baseline_uses_single_symbol_flatten(monkeypatch):
    pos_calls = 0

    def fake(base, path, **kw):
        nonlocal pos_calls
        if path == r2.OPEN_ORDERS_PATH:
            return 200, {"ok": True, "matched_count": 0, "orders": []}
        if path == r2.POSITION_PATH:
            pos_calls += 1
            rows = [] if pos_calls in {1, 3} else [{"symbol": "AMAT", "position": 1.0}]
            return 200, {"ok": True, "position_read_error": None, "flatten_candidates": rows}
        if path == r2.SUBMIT_PATH:
            return 200, {
                "ok": True,
                "status": "submitted",
                "place_order_called": True,
                "broker_order_placed": True,
                "broker_submit": {"order": {"orderId": 90, "permId": 91, "orderRef": "R"}, "order_status": {"status": "Filled", "filled": 1, "remaining": 0}},
                "open_trades_after_for_ref": [],
                "post_submit": {"classification": "filled_or_no_remaining"},
            }
        if path == r2.LIFECYCLE_PATH:
            payload = kw["payload"]
            assert payload["mode"] == "flatten_symbol" and payload["symbol"] == "AMAT" and payload["submit"] is True
            assert payload["live_allowed"] is False
            return 200, {"ok": True, "status": "submitted"}
        raise AssertionError(path)

    monkeypatch.setattr(r2, "_request", fake)
    out = r2.execute("http://x", runtime(), request(), run_id="1", job="j", public_head="c" * 40)
    assert out["ok"]
    assert out["cleanup"]["flatten_symbol_attempted"] is True
    assert out["cleanup"]["flatten_symbol_reported_ok"] is True
    assert out["cleanup"]["flatten_all_called"] is False


def test_r2_workflow_is_paper_only_and_publishes_failure_receipt():
    text = (ROOT / ".github" / "workflows" / "ibkr-remote-paper-runtime-rendezvous-r2.yml").read_text()
    assert "paper_submit_proof" in text
    assert "ENABLE_LIVE_TRADING=0" in text
    assert "STRATEGY_IBKR_PAPER_ORDER_SUBMIT_ENABLED_13Z53=1" in text
    assert "STRATEGY_IBKR_PAPER_CANCEL_ENABLED_13Z37=1" in text
    assert "STRATEGY_IBKR_PAPER_GLOBAL_CANCEL_ENABLED_13Z37D=0" in text
    assert "/strategy/ibkr-paper-global-cancel" not in text
    assert "flatten_all" not in text
    assert "actions/upload-artifact" not in text
    assert "docker logs" not in text
    publish = text.index("Publish sanitized deterministic receipt")
    enforce = text.index("Enforce paper proof result after receipt publication")
    destroy = text.index("Destroy private runtime material")
    assert publish < enforce < destroy
    assert text.count("if: always()") >= 3
