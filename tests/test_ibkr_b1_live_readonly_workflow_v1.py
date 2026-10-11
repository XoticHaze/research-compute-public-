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
    end = WORKFLOW.index("warm_state_args=()", start)
    scope = WORKFLOW[start:end]
    assert "IBKR_PAPER_PROOF_MODE" in scope
    assert "IBKR_PAPER_EXECUTE_MODE" in scope
    assert "IBKR_PAPER_ACCOUNT_HYGIENE_MODE" in scope
    assert 'test "$api_read_only" = yes' in scope
    assert 'gateway_mode=live' in scope
    assert 'gateway_host_port=4001' in scope
    assert 'gateway_container_port=4003' in scope


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
    assert "if: env.IBKR_WARM_READ_RETURN_REQUESTED == '1' && env.IBKR_PRODUCTION_LIVE_READONLY_MODE != '1'" in WORKFLOW
    assert "- name: Reject paper-only snapshot return contract in live mode" in WORKFLOW
    assert "IBKR_LIVE_READONLY_PAPER_SNAPSHOT_RETURN_UNSUPPORTED=1" in WORKFLOW


def test_live_readonly_mode_has_no_live_order_execution_step():
    assert "IBKR_LIVE_EXECUTE_MODE" not in WORKFLOW
    assert "IBKR_LIVE_SUBMIT_MODE" not in WORKFLOW
    assert "live_order_submit" not in WORKFLOW

def test_live_readonly_uses_live_gateway_port_and_never_relabels_paper_reads():
    assert '-e TRADING_MODE="$gateway_mode"' in WORKFLOW
    assert '-p "127.0.0.1:$gateway_host_port:$gateway_container_port"' in WORKFLOW
    assert "int(os.environ['IBKR_GATEWAY_API_PORT']),clientId=76" in WORKFLOW
    assert "int(os.environ['IBKR_GATEWAY_API_PORT']),clientId=77" in WORKFLOW
    assert "IBKR_PRODUCTION_LIVE_READONLY_MODE != '1'" in WORKFLOW
    assert "IBKR_LIVE_AUTHENTICATED_API=1" in WORKFLOW
    assert "IBKR_LIVE_EXPECTED_NON_DU_ACCOUNT_BOUND=1" in WORKFLOW
    assert "IBKR_LIVE_ORDER_MUTATION_ATTEMPTED=0" in WORKFLOW
    assert "if not expected or expected.upper().startswith('DU')" in WORKFLOW
    assert "if expected not in accounts" in WORKFLOW


def test_live_readonly_never_passes_through_paper_only_post_auth_or_snapshot():
    paper_handoff = WORKFLOW.index("- name: Materialize canonical post-auth broker and forward-data handoff")
    assert "IBKR_PRODUCTION_LIVE_READONLY_MODE != '1'" in WORKFLOW[paper_handoff:paper_handoff+350]
    paper_return = WORKFLOW.index("- name: Encrypt optional detailed warm read snapshot for private consumer")
    assert "IBKR_PRODUCTION_LIVE_READONLY_MODE != '1'" in WORKFLOW[paper_return:paper_return+260]


def test_live_mobile_approval_is_distinct_from_verified_gateway_api_readiness():
    # The broker may accept IB Key before the Gateway API becomes usable.
    # An API timeout must preserve that distinction and emit no account data.
    assert "IBKR_LIVE_POST_2FA_DIAGNOSTIC=" in WORKFLOW
    assert '"launcher_authentication_complete"' in WORKFLOW
    assert '"api_ready_verified": False' in WORKFLOW
    assert '"controller_health"' in WORKFLOW
    assert '"private_account_fields_emitted": False' in WORKFLOW
    assert "IBKR_GATEWAY_API_READY_VERIFIED=0" in WORKFLOW
    assert "IBKR_OPERATOR_APPROVAL_ACCEPTED=0" in WORKFLOW
    assert "IBKR_LIVE_ORDER_MUTATION_ATTEMPTED=0" in WORKFLOW
