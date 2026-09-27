from __future__ import annotations
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
WF=(ROOT/".github/workflows/mmibkr-canonical-research-session-bau-r1.yml").read_text()
def test_generic_bau_session_workflow_composes_existing_owners():
    for token in ("workflow_dispatch:","dispatch_nonce:","run-name: canonical-session-",
      "mmibkr_source_vault_consumer_v1.py","mmibkr_attested_source_to_canonical_receipt_v1.py",
      "mnq_corpus_ephemeral_materialize_v1.py","mmibkr_canonical_session_runner_v1.py",
      "canonical-session-terminal","artifact-digest"):
        assert token in WF
def test_generic_bau_session_workflow_does_not_encode_strategy_architecture():
    assert "DCA_" not in WF
    assert "WINDOW" not in WF
    assert "ENTRY_EXTREME" not in WF
    assert "EXIT_EXTREME" not in WF
def test_generic_bau_session_workflow_preserves_authority_boundaries():
    for token in ("'strategy_spec_write':False","'runtime_activation':False","'broker_submit':False",
                  "'broker_cancel':False","'broker_flatten':False","'promotion_mutation':False","'live_trading':False"):
        assert token in WF
