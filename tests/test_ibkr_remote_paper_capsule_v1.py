import base64
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ibkr_remote_paper_capsule_v1 as mod


def _return_recipient():
    raw = bytes(range(32))
    return {
        "schema": mod.RETURN_RECIPIENT_SCHEMA,
        "recipient_b64": base64.b64encode(raw).decode("ascii"),
        "recipient_key_id": "sha256:" + hashlib.sha256(raw).hexdigest(),
    }


def capsule(mode="session_reconcile"):
    request = {}
    cleanup = {
        "cancel_open_order": False,
        "flatten_filled_position": False,
        "require_zero_baseline": False,
        "allow_global_cancel": False,
    }
    if mode == "paper_submit_proof":
        request = {"canonical_submit_payload": {"symbol": "MNQ", "orderType": "LMT", "totalQuantity": 1}}
        cleanup.update(cancel_open_order=True, flatten_filled_position=True, require_zero_baseline=True)
    return {
        "schema": mod.CAPSULE_SCHEMA,
        "mode": mode,
        "source": {
            "repository": mod.SOURCE_REPOSITORY,
            "head": "a" * 40,
            "archive_url": "https://api.github.com/repos/XoticHaze/mm-IBKR/tarball/" + "a" * 40,
            "archive_sha256": "b" * 64,
            "authorization_bearer": "ghs_example_source_capability_123456789",
        },
        "ibkr": {"username": "paper-user", "password": "paper-password", "trading_mode": "paper"},
        "request": request,
        "cleanup": cleanup,
    }


def validate(node):
    return mod.validate_capsule(json.dumps(node).encode())


def test_session_reconcile_legacy_empty_request_still_accepted():
    out = validate(capsule())
    assert out["mode"] == "session_reconcile"
    assert out["ibkr"]["trading_mode"] == "paper"
    assert out["request"] == {}


def test_session_reconcile_accepts_only_authenticated_return_recipient():
    node = capsule()
    node["request"] = {"encrypted_return": _return_recipient()}
    out = validate(node)
    assert out["request"]["encrypted_return"]["recipient_key_id"] == _return_recipient()["recipient_key_id"]


def test_return_recipient_fingerprint_mismatch_fails_closed():
    node = capsule()
    recipient = _return_recipient()
    recipient["recipient_key_id"] = "sha256:" + "0" * 64
    node["request"] = {"encrypted_return": recipient}
    with pytest.raises(RuntimeError, match="fingerprint mismatch"):
        validate(node)


def test_session_reconcile_rejects_any_other_request_field():
    node = capsule()
    node["request"] = {"observe_symbols": ["SMH"]}
    with pytest.raises(RuntimeError, match="admits only encrypted_return"):
        validate(node)


def test_live_mode_is_rejected():
    node = capsule()
    node["ibkr"]["trading_mode"] = "live"
    with pytest.raises(RuntimeError, match="only IBKR paper"):
        validate(node)


def test_live_authority_hidden_in_submit_payload_is_rejected():
    node = capsule("paper_submit_proof")
    node["request"]["canonical_submit_payload"]["ENABLE_LIVE_TRADING"] = True
    with pytest.raises(RuntimeError, match="live authority rejected"):
        validate(node)


def test_private_source_must_be_exact_mmibkr_head():
    node = capsule()
    node["source"]["archive_url"] = "https://api.github.com/repos/Elsewhere/mm-IBKR/tarball/" + "a" * 40
    with pytest.raises(RuntimeError, match="source archive URL/head mismatch"):
        validate(node)


def test_paper_submit_requires_exact_cleanup_guards():
    node = capsule("paper_submit_proof")
    node["cleanup"]["flatten_filled_position"] = False
    with pytest.raises(RuntimeError, match="filled-position cleanup"):
        validate(node)


def test_global_cancel_is_never_admitted_by_remote_proof():
    node = capsule("paper_submit_proof")
    node["cleanup"]["allow_global_cancel"] = True
    with pytest.raises(RuntimeError, match="global cancel is prohibited"):
        validate(node)
