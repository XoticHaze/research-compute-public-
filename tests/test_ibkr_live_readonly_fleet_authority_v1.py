from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER = (ROOT / "cloudflare/fleet-authority/src/index.js").read_text(encoding="utf-8")
CONSUMER = (ROOT / "scripts/fleet_authority_envelope_consumer_v1.py").read_text(encoding="utf-8")


def test_live_readonly_authority_is_separate_and_read_only():
    assert "const LIVE_READONLY_AUTHORITY = 'ibkr-live-readonly';" in WORKER
    assert "/v1/authorities/ibkr-live-readonly/seal" in WORKER
    assert "IBKR_LIVE_USERNAME" in WORKER
    assert "IBKR_LIVE_PASSWORD" in WORKER
    assert "IBKR_LIVE_ACCOUNT" in WORKER
    assert "'MMIBKR_ACCOUNT_MODE=production_live'" in WORKER
    assert "'TRADING_MODE=live'" in WORKER
    assert "'READ_ONLY_API=yes'" in WORKER
    assert "'ENABLE_LIVE_TRADING=0'" in WORKER


def test_live_readonly_profile_never_falls_back_to_paper_secret_names():
    start = WORKER.index("async function sealIbkrLiveReadonlyGatewayEnv")
    end = WORKER.index("async function sealHfdlApiKey", start)
    scope = WORKER[start:end]
    for forbidden in (
        "IBKR_PAPER_USERNAME",
        "IBKR_PAPER_PASSWORD",
        "IBKR_PAPER_TWOFACTOR_CODE",
        "IBKR_PAPER_TWOFA_DEVICE",
        "IBKR_PAPER_TWS_SERVER",
    ):
        assert forbidden not in scope
    assert "IBKR_LIVE_TWOFACTOR_CODE" in scope
    assert "IBKR_LIVE_TWOFA_DEVICE" in scope
    assert "IBKR_LIVE_TWS_SERVER" in scope


def test_live_account_binding_remains_inside_encrypted_plaintext_only():
    start = WORKER.index("async function sealIbkrLiveReadonlyGatewayEnv")
    end = WORKER.index("async function sealHfdlApiKey", start)
    scope = WORKER[start:end]
    assert "MMIBKR_PRODUCTION_LIVE_ACCOUNT=${liveAccount}" in scope
    return_scope = scope[scope.index("return {"):]
    assert "liveAccount" not in return_scope
    assert "IBKR_LIVE_ACCOUNT" not in return_scope


def test_live_readonly_authority_rejects_du_account_binding():
    start = WORKER.index("async function sealIbkrLiveReadonlyGatewayEnv")
    end = WORKER.index("async function sealHfdlApiKey", start)
    scope = WORKER[start:end]
    assert "liveAccount.toUpperCase().startsWith('DU')" in scope
    assert "live_authority_account_rejected" in scope


def test_consumer_has_only_exact_allowlisted_profiles():
    assert '"paper": {' in CONSUMER
    assert '"production_live_readonly": {' in CONSUMER
    assert 'raise RuntimeError("authority_profile_rejected")' in CONSUMER
    assert 'choices=sorted(PROFILES)' in CONSUMER
    assert 'LIVE_READONLY_AUTHORITY = "ibkr-live-readonly"' in CONSUMER


def test_no_live_mutation_authority_endpoint_exists():
    assert "/v1/authorities/ibkr-live/seal" not in WORKER
    assert "ibkr-live-submit" not in WORKER
    assert "ibkr-live-mutation" not in WORKER
