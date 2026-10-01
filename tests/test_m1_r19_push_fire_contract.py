from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
WORKFLOW=ROOT/".github/workflows/m1-h12-sealed-private-r19.yml"

def test_r19_has_only_explicit_main_fire_marker_push_trigger():
    text=WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text
    assert "branches: [main]" in text
    assert "- 'rendezvous/fire/m1-h12-sealed-private-r19'" in text
    assert "paths-ignore" not in text
    assert "schedule:" not in text

def test_r19_keeps_fixed_harness_and_no_live_or_broker_authority():
    text=WORKFLOW.read_text(encoding="utf-8")
    assert "EXPECTED_HARNESS: research_foundry_m1_h12_r18_v1" in text
    assert "authority':'research_only'" in text or "authority\":\"research_only" in text
    assert "m1-payload.tar.gz.age" in text
