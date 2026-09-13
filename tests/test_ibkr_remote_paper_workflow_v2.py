from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_r2_workflow_is_paper_only_bounded_and_publishes_failure_receipt():
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


def test_r2_driver_calls_only_exact_cancel_and_single_symbol_lifecycle():
    text = (ROOT / "scripts" / "ibkr_remote_paper_submit_v2.py").read_text()
    assert 'CANCEL_PATH = "/strategy/ibkr-paper-cancel-submit"' in text
    assert 'LIFECYCLE_PATH = "/strategy/bot-owned-position-lifecycle"' in text
    assert '"mode": "flatten_symbol"' in text
    assert '"require_symbol_match": True' in text
    assert '"global_cancel_called": False' in text
    assert '"flatten_all_called": False' in text
    assert "/strategy/ibkr-paper-global-cancel-submit" not in text
