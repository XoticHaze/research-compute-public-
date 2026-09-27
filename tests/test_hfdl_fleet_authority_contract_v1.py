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


def test_hfdl_workflow_identity_is_narrowly_bound():
    workflow = (ROOT / ".github/workflows/hfdl-equity-history-e1-r1.yml").read_text()
    assert "branches: [hfdl-e1-authority-v1]" in workflow
    assert "id-token: write" in workflow
    assert "scripts/hfdl_api_key_envelope_consumer_v1.py" in workflow
    assert "research/hfdl_equity_history_e1.py" in workflow
    assert "AMAT,APH" in (ROOT / "rendezvous/fire/hfdl-equity-history-e1-r1").read_text()
