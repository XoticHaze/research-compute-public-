import hashlib
import json


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def validate(claim):
    assert claim["schema"] == "foundry.shared_evidence_claim.v1"
    assert claim["evidence_id"].startswith("P303-P304:")
    assert claim["claim"]["claim_type"] == "evidence.p303_p304_spmo_smallvalue_fixed_utility"
    assert claim["claim"]["status"] == "SUPPORTED"
    assert claim["authority"]["max_scope"] == "RESEARCH_ONLY"
    assert claim["authority"]["automatic_action_allowed"] is False
    assert "Portfolio ranking or allocation authority" in claim["boundaries"]["does_not_establish"]
    assert any("Do not optimize" in x for x in claim["boundaries"]["prohibited_inferences"])
    assert len(claim["evidence"]["support"]) == 2
    for row in claim["evidence"]["support"]:
        for key in ("run_id", "job_id", "started_at_utc", "head_sha", "artifact_id", "artifact_sha256"):
            assert row[key]
    values = {m["name"]: m["value"] for m in claim["evidence"]["metrics"]}
    for prefix in ("p303", "p304"):
        assert values[f"{prefix}_2017_matched_excess_cagr"] > 0
        assert values[f"{prefix}_2020_matched_excess_cagr"] > 0
        assert values[f"{prefix}_2022_matched_excess_cagr"] > 0
        assert values[f"{prefix}_positive_chronological_folds"] == 4
    return hashlib.sha256(canonical(claim)).hexdigest()


claim = {
    "schema": "foundry.shared_evidence_claim.v1",
    "evidence_id": "P303-P304:spmo_smallvalue_fixed_utility_representation_robust:2026-09-10",
    "producer": {"system": "continue-release", "repository": "XoticHaze/CommandCenter", "source_ref": "49fc6f9270adb0fd5edcff13d169d0c2a6f7adbd", "run_id": "34459259666"},
    "claim": {"claim_type": "evidence.p303_p304_spmo_smallvalue_fixed_utility", "status": "SUPPORTED", "statement": "sanitized representation-robust fixed utility release shape", "subject": "P303/P304 fixed SPMO plus small-value combination", "role": "research_result_consumer", "mechanism": "terminal-result first consumer", "capabilities": ["evidence.p303_p304_spmo_smallvalue_fixed_utility", "evidence.matched_alpha", "diagnostic.independent_representation_transport"]},
    "authority": {"max_scope": "RESEARCH_ONLY", "automatic_action_allowed": False, "authority_source": "XoticHaze/CommandCenter@49fc6f9270adb0fd5edcff13d169d0c2a6f7adbd"},
    "evidence": {
        "inputs": [{"kind": "terminal_scientific_consequence", "identity": "market-research-consume-p303-fixed-utility-20260910T091020Z"}, {"kind": "terminal_scientific_consequence", "identity": "market-research-consume-p304-representation-20260910T091210Z"}],
        "metrics": [
            {"name": "p303_2017_matched_excess_cagr", "value": 0.02307880900788528}, {"name": "p303_2020_matched_excess_cagr", "value": 0.03872599050347314}, {"name": "p303_2022_matched_excess_cagr", "value": 0.05302656002335726}, {"name": "p303_positive_chronological_folds", "value": 4},
            {"name": "p304_2017_matched_excess_cagr", "value": 0.023862697387168064}, {"name": "p304_2020_matched_excess_cagr", "value": 0.03520522706437568}, {"name": "p304_2022_matched_excess_cagr", "value": 0.04972165748538271}, {"name": "p304_positive_chronological_folds", "value": 4}
        ],
        "support": [
            {"run_id": 34459097977, "job_id": 102812375326, "started_at_utc": "2026-09-10T09:09:41Z", "head_sha": "e1cdff0a4598b018c37714b34ca0bd3bc8d4fd56", "artifact_id": 10144735823, "artifact_sha256": "c1d7d7655e5206d8cedf1b69ca811c222059539757ea55f454c3767447aaf972"},
            {"run_id": 34459259666, "job_id": 102812907365, "started_at_utc": "2026-09-10T09:11:27Z", "head_sha": "25f23de9507d6a883d285e2aabe7728c55c1f747", "artifact_id": 10144803862, "artifact_sha256": "d1dfd771ac1d08b88343fb3412b80df971a35d56cbba5267cce73b64335904e2"}
        ]
    },
    "boundaries": {"applies_to": {"parents": ["P303", "P304"], "research_only": True}, "does_not_establish": ["Broad standalone small-value premium", "Portfolio ranking or allocation authority", "Product/runtime/broker/live-trading authority"], "prohibited_inferences": ["Do not optimize the fixed 50/50 weight.", "Do not select small-value products post hoc.", "Do not promote automatic action."]},
    "decision": {"disposition": "FIXED_SPMO_SMALLVALUE_UTILITY_SUPPORTED_AND_INDEPENDENT_REPRESENTATION_CONFIRMED"},
    "lineage": {"parents": ["P303", "P304", "P301", "P290", "P249"], "related": ["P300", "P302"]}
}

sha = validate(claim)
assert validate(json.loads(canonical(claim))) == sha
print(json.dumps({"result": "PASS", "claim_sha256": sha, "automatic_action_allowed": False, "allocation_authority": False}, sort_keys=True))
