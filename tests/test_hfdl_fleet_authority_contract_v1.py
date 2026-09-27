import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_hfdl_authority_is_separate_from_ibkr_authority():
    source = (ROOT / "cloudflare/fleet-authority/src/index.js").read_text()

    assert "const EXPECTED_AUTHORITY = 'ibkr-paper-readonly';" in source
    assert "const HFDL_AUTHORITY = 'hfdl-readonly';" in source
    assert "refs/heads/ibkr-b1-authority-v1" in source
    assert "refs/heads/hfdl-e1-authority-v1" in source
    assert "/v1/authorities/ibkr-paper/seal" in source
    assert "/v1/authorities/hfdl/seal" in source
    assert "HFDL_API_KEY" in source
    assert "hfdl_authority_configured" in source
    exchange = (ROOT / "cloudflare/fleet-authority/src/source_exchange.js").read_text()
    assert "const HFDL_E1_CANONICAL_IDENTITY = {" in exchange
    assert "refs/heads/hfdl-e1-authority-v1" in exchange
    assert "hfdl-equity-history-e1-r1.yml@refs/heads/hfdl-e1-authority-v1" in exchange
    assert "matchedHfdlE1Canonical && privateTestProbeUnwrapPathAllowed" in exchange


def test_hfdl_workflow_identity_is_narrowly_bound():
    workflow = (ROOT / ".github/workflows/hfdl-equity-history-e1-r1.yml").read_text()
    assert "branches: [hfdl-e1-authority-v1]" in workflow
    assert "id-token: write" in workflow
    assert "scripts/hfdl_api_key_envelope_consumer_v1.py" in workflow
    assert "research/hfdl_equity_history_e1.py" in workflow
    assert "scripts/mmibkr_source_vault_consumer_v1.py" in workflow
    assert "materialize_admitted_stock_source_canonical.py" in workflow
    assert "HFDL_E1_MM_CANONICALIZATION=PASS" in workflow
    fire = json.loads(
        (ROOT / "rendezvous/fire/hfdl-equity-history-e1-r1").read_text()
    )
    assert fire["schema"] == "public_research.hfdl_e1_fire.v1"
    assert fire["symbols"] == ["AMAT", "APH"]
    assert fire["provider_timeframe"] == "1min"
    assert fire["provider_format"] == "parquet"
    assert fire["acquisition_endpoint"] == "GET /v1/bars/{ticker}?version=raw"
    assert fire["mm_source_sha"] == "24128a842cd860cbf1fe6c93f368fabdae925f80"
    assert fire["canonical_target_timeframe"] == "15Min"
    assert fire["authority"]["broker"] is False
    assert fire["authority"]["live"] is False
