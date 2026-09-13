import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from ephemeral_x25519_chunked_v1 import AUTHORITY, aad_bytes


def test_transport_default_authority_remains_research_only():
    aad = json.loads(aad_bytes(schema="s", run_id="1", harness="h", recipient_key_id="sha256:x").decode())
    assert AUTHORITY == "research_only"
    assert aad["authority"] == "research_only"
    broker = json.loads(aad_bytes(schema="s", run_id="1", harness="h", recipient_key_id="sha256:x", authority="mm_ibkr_paper_runtime").decode())
    assert broker["authority"] == "mm_ibkr_paper_runtime"


def test_r1_workflow_is_read_only_and_tears_down_private_material():
    text = (ROOT / ".github" / "workflows" / "ibkr-remote-paper-runtime-rendezvous-r1.yml").read_text()
    assert "R1 admits session_reconcile only" in text
    assert "ENABLE_LIVE_TRADING=0" in text
    assert "BOT_SELECTED_RUNTIME_NATURAL_CANDIDATE_14TH31BV_ENABLED=0" in text
    assert "STRATEGY_IBKR_PAPER_CANCEL_ENABLED_13Z37=0" in text
    assert "STRATEGY_IBKR_PAPER_GLOBAL_CANCEL_ENABLED_13Z37D=0" in text
    assert "/strategy/ibkr-paper-order-submit" not in text
    assert "/strategy/ibkr-paper-cancel-submit" not in text
    assert "/strategy/bot-owned-position-lifecycle" not in text
    assert "actions/upload-artifact" not in text
    assert "docker logs" not in text
    assert 'rm -rf \\\n' in text
