from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCER = ROOT / "scripts" / "mnq_exact_corpus_producer_v1.py"
PRODUCER_WORKFLOW = ROOT / ".github" / "workflows" / "mnq-exact-corpus-producer-r1.yml"
CANONICAL_WORKFLOW = ROOT / ".github" / "workflows" / "mmibkr-canonical-research-session-bau-r1.yml"


def test_exact_corpus_refiller_is_content_addressed_and_authority_bounded():
    text = PRODUCER.read_text(encoding="utf-8")
    assert "c04a95debfde500aa245d187a1d30620a88703113013a63af0c3553b0509e44e" in text
    assert "18_026_715" in text
    assert "192_553" in text
    assert "fc5508e2c152938d6d9eb70a36b888ae26107176" in text
    assert "633eb4338a3aa60aedb542b12085acca29ff237c7cadff65442a638466f37667" in text
    assert '"research_only"' in text
    assert '"promotion_authority": False' in text
    assert '"strategy_spec_write": False' in text
    assert '"runtime_activation": False' in text
    assert '"broker_submit": False' in text
    assert '"live_trading_change": False' in text


def test_exact_corpus_refiller_publishes_ciphertext_then_envelope():
    text = PRODUCER.read_text(encoding="utf-8")
    chunk_pos = text.index('path = f"{response_root}/mnq-corpus-{index:03d}.txt"')
    envelope_pos = text.index('f"{response_root}/mnq-corpus-envelope.json"')
    assert chunk_pos < envelope_pos
    assert "ChaCha20Poly1305(key).encrypt" in text
    assert "x25519.X25519PrivateKey.generate()" in text
    assert "direct_exact_corpus_gzip" in text


def test_canonical_session_dispatches_producer_after_recipient_before_wait():
    text = CANONICAL_WORKFLOW.read_text(encoding="utf-8")
    recipient = text.index("- name: Publish run-bound corpus recipient")
    dispatch = text.index("- name: Dispatch exact admitted MNQ corpus producer")
    wait = text.index("- name: Wait for run-bound corpus envelope")
    assert recipient < dispatch < wait
    assert "actions: write" in text
    assert "mnq-exact-corpus-producer-r1.yml/dispatches" in text
    assert "seq 1 360" in text


def test_producer_workflow_is_dispatch_only_and_cleans_plaintext():
    text = PRODUCER_WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text
    assert "schedule:" not in text
    assert "push:" in text
    assert "rendezvous/fire/mnq-exact-corpus-producer-r1.json" in text
    assert "mnq.exact_corpus_producer_fire.v1" in text
    assert "contents: write" in text
    assert "mnq_exact_corpus_producer_v1.py" in text
    assert "Remove plaintext producer work" in text
