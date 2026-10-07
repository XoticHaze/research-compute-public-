from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (
    ROOT / ".github/workflows/ibkr-cloudflare-readonly-b1-r1.yml"
).read_text(encoding="utf-8")


def test_live_readonly_mode_is_explicit_and_uses_live_fleet_profile():
    assert "- production_live_readonly" in WORKFLOW
    assert "/v1/authorities/ibkr-live-readonly/seal" in WORKFLOW
    assert "FLEET_AUTHORITY_PROFILE:" in WORKFLOW
    assert "'production_live_readonly'" in WORKFLOW
    assert '--profile "$FLEET_AUTHORITY_PROFILE"' in WORKFLOW


def test_live_readonly_mode_never_enables_paper_mutation_flags():
    for flag in (
        "IBKR_PAPER_PROOF_MODE:",
        "IBKR_PAPER_EXECUTE_MODE:",
        "IBKR_PAPER_ACCOUNT_HYGIENE_MODE:",
    ):
        line = next(line for line in WORKFLOW.splitlines() if flag in line)
        assert "production_live_readonly" not in line

    start = WORKFLOW.index("api_read_only=yes")
    end = WORKFLOW.index("IBKR_API_READ_ONLY=", start)
    scope = WORKFLOW[start:end]
    assert "IBKR_PAPER_PROOF_MODE" in scope
    assert "IBKR_PAPER_EXECUTE_MODE" in scope
    assert "IBKR_PAPER_ACCOUNT_HYGIENE_MODE" in scope
    assert "IBKR_PRODUCTION_LIVE_READONLY_MODE" not in scope


def test_live_readonly_never_reuses_or_publishes_paper_warm_state():
    restore = WORKFLOW.index("- name: Restore encrypted warm Gateway state if available")
    restore_scope = WORKFLOW[restore:restore + 500]
    assert "IBKR_PRODUCTION_LIVE_READONLY_MODE != '1'" in restore_scope

    seal = WORKFLOW.index("- name: Seal authenticated Gateway warm state")
    seal_scope = WORKFLOW[seal:seal + 500]
    assert "IBKR_PRODUCTION_LIVE_READONLY_MODE != '1'" in seal_scope

    publish = WORKFLOW.index("- name: Publish reusable encrypted warm state")
    publish_scope = WORKFLOW[publish:publish + 500]
    assert "IBKR_PRODUCTION_LIVE_READONLY_MODE != '1'" in publish_scope


def test_live_readonly_detailed_broker_truth_uses_encrypted_return_only():
    warm_line = next(
        line for line in WORKFLOW.splitlines()
        if "IBKR_WARM_READ_RETURN_REQUESTED:" in line
    )
    assert "production_live_readonly" in warm_line

    publish = WORKFLOW.index("- name: Publish canonical session and forward-data handoff")
    publish_scope = WORKFLOW[publish:publish + 700]
    assert "IBKR_PRODUCTION_LIVE_READONLY_MODE != '1'" in publish_scope

    assert "- name: Publish encrypted warm read return" in WORKFLOW


def test_live_readonly_mode_has_no_live_order_execution_step():
    assert "IBKR_LIVE_EXECUTE_MODE" not in WORKFLOW
    assert "IBKR_LIVE_SUBMIT_MODE" not in WORKFLOW
    assert "live_order_submit" not in WORKFLOW
