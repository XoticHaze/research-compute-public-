import hashlib
import json
import re


ALLOWED_STATUSES = {"SUPPORTED", "REJECTED", "INSUFFICIENT_SUPPORT", "MIXED", "PARKED"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def metric_name(parts):
    raw = ".".join(str(p) for p in parts if str(p)) or "value"
    value = re.sub(r"[^a-z0-9_.-]+", "_", raw.lower()).strip("_.-") or "value"
    return value if value[0].isalpha() else f"metric.{value}"


def flatten(value, parts=None):
    parts = parts or []
    if isinstance(value, dict):
        out = []
        for key in sorted(value):
            out += flatten(value[key], [*parts, key])
        return out
    if not isinstance(value, (str, int, float, bool)) and value is not None:
        value = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return [{"name": metric_name(parts), "value": value, "direction": "DESCRIPTIVE"}]


def normalize(compact):
    producer = compact["producer"]
    executions = producer.get("executions", [])
    primary = executions[0] if executions else {}
    workflow = primary.get("workflow")
    head = primary.get("head_sha")
    out = json.loads(json.dumps(compact))
    out["producer"] = {
        "system": producer.get("system", "unknown"),
        "repository": producer.get("repository", "unknown"),
        "source_ref": f"{workflow}@{head}" if workflow and head else compact["evidence_id"],
        "run_id": str(primary["run_id"]) if primary.get("run_id") is not None else None,
        "generated_at": primary.get("run_started_at"),
        "artifact_digest": primary.get("artifact_digest"),
    }
    evidence = compact["evidence"]
    out["evidence"] = {
        "inputs": [],
        "metrics": flatten(evidence.get("metrics", {})),
    }
    out["boundaries"] = {
        "applies_to": {"hypothesis_id": compact["claim"].get("hypothesis_id"), "subject": compact["claim"]["subject"]},
        "does_not_establish": ["portfolio allocation authority", "runtime authority", "broker authority", "live-trading authority"],
    }
    out["lineage"] = {"parents": [compact["claim"].get("hypothesis_id") or compact["claim"]["subject"]], "related": []}
    decision = evidence.get("decision")
    if isinstance(decision, str):
        out["decision"] = {"disposition": decision}
    return out


def validate_release_claim(claim):
    assert claim["schema"] == "foundry.shared_evidence_claim.v1"
    assert claim["evidence_id"]
    producer = claim["producer"]
    assert producer["repository"]
    assert producer["source_ref"]
    assert str(producer["run_id"])
    body = claim["claim"]
    assert body["claim_type"]
    assert body["status"] in ALLOWED_STATUSES
    assert body["statement"]
    assert body["capabilities"]
    authority = claim["authority"]
    assert authority["max_scope"] == "RESEARCH_ONLY"
    assert authority["automatic_action_allowed"] is False
    evidence = claim["evidence"]
    assert evidence["inputs"]
    assert evidence["metrics"]
    support = evidence["support"]
    assert support
    for execution in support:
        assert execution["run_id"]
        assert execution["job_id"]
        assert execution["started_at_utc"]
        assert execution["head_sha"]
        assert execution["artifact_id"]
        assert execution["artifact_sha256"]
    boundaries = claim["boundaries"]
    assert boundaries["does_not_establish"]
    assert boundaries["prohibited_inferences"]
    assert claim["decision"]["disposition"]
    assert claim["lineage"]["parents"]
    return hashlib.sha256(canonical(claim)).hexdigest()


fixture = {
    "schema": "foundry.shared_evidence_claim.v1",
    "evidence_id": "acceptance:legacy:001",
    "producer": {"system": "research-compute-public", "repository": "XoticHaze/research-compute-public-", "executions": [{"workflow": ".github/workflows/example.yml", "run_id": 123, "run_started_at": "2026-09-09T00:00:00Z", "head_sha": "abc123", "artifact_digest": "sha256:deadbeef"}]},
    "claim": {"claim_type": "diagnostic.legacy_acceptance", "status": "MIXED", "statement": "sanitized acceptance fixture", "subject": "legacy adapter acceptance", "hypothesis_id": "PTEST", "capabilities": ["diagnostic.legacy_acceptance"]},
    "authority": {"max_scope": "RESEARCH_ONLY", "automatic_action_allowed": False},
    "evidence": {"metrics": {"delay1": {"excess_cagr": 0.01}}, "decision": "SANITIZED_ACCEPTANCE"},
}

p29_release = {
    "schema": "foundry.shared_evidence_claim.v1",
    "evidence_id": "P29-R3:smh_opportunity_cost_recent_weak:2026-09-09",
    "producer": {"system": "continue-release", "repository": "XoticHaze/CommandCenter", "source_ref": "0bb09cb71c050b12b1b5da9ef772f6459c9b3244", "run_id": "34336319507", "artifact_digest": "sha256:3575b4e9302239736503e3d293553b41b434ec05916c32af29774758a05b2bf6"},
    "claim": {"claim_type": "diagnostic.p29_smh_opportunity_cost", "status": "MIXED", "statement": "historical SMH excess remains broad but 2022-forward opportunity-cost superiority is weak", "subject": "P29 monthly top-3 PIT semiconductor 6-month cross-sectional momentum", "hypothesis_id": "P29", "capabilities": ["diagnostic.p29_smh_opportunity_cost"]},
    "authority": {"max_scope": "RESEARCH_ONLY", "automatic_action_allowed": False},
    "evidence": {"parameters": {"execution_delay_grid_days": list(range(11)), "cost_bps": 50, "no_delay_selection_or_tuning": True}, "metrics": [{"name": "full_positive_delay_fraction_vs_smh", "value": 1.0}, {"name": "recent_2022_forward_positive_delay_fraction_vs_smh", "value": 5 / 11}, {"name": "recent_2022_forward_median_excess_vs_smh", "value": -0.016241202674003308}]},
    "boundaries": {"does_not_establish": ["preferred execution delay", "current fund candidacy", "runtime authority", "broker authority", "live-trading authority"], "prohibited_inferences": ["do not select the best historical delay", "do not use full-history excess to override weak recent opportunity cost"]},
    "decision": {"disposition": "HISTORICAL_ALPHA_RECENT_OPPORTUNITY_COST_WEAK"},
    "lineage": {"parents": ["P29"], "supersedes": ["P29-C3:semiconductor_cross_sectional_momentum_validation_state:2026-09-08"]},
}

p13_release = {
    "schema": "foundry.shared_evidence_claim.v1",
    "evidence_id": "P13-R3:immutable_monthly_record_replay_exact:2026-09-09",
    "producer": {"system": "continue-release", "repository": "XoticHaze/CommandCenter", "source_ref": "0f1769e4e89f3a2fda075f705eaf5062ace6777c", "run_id": "34336946321", "artifact_digest": "sha256:77f91d11e5543f558ad0832bc5272ed5bb97d97902483656b3b0c7dfbda745ca"},
    "claim": {"claim_type": "diagnostic.p13_immutable_record_replay", "status": "MIXED", "statement": "immutable monthly records replay exactly while rounded CSV and raw-price lineage remain insufficient for bit-exact regeneration", "subject": "P13 two-factor residual selector deterministic replay boundary", "hypothesis_id": "P13", "capabilities": ["diagnostic.p13_immutable_record_replay"]},
    "authority": {"max_scope": "RESEARCH_ONLY", "automatic_action_allowed": False},
    "evidence": {"parameters": {"source_artifact_id": 10093700209, "selection_return_fingerprint_sha256": "e6b63d26f01d7b21f752a9bb32cd6866f2551e7dfe9aeb59363d6a9a6a59f64f"}, "metrics": [{"name": "full_months", "value": 92}, {"name": "full_candidate_cagr", "value": 0.5841555845436586}, {"name": "recent_2022_forward_months", "value": 56}, {"name": "recent_2022_forward_candidate_cagr", "value": 0.5313469766023933}]},
    "boundaries": {"does_not_establish": ["bit-exact raw-price corpus reproducibility", "bit-exact model regeneration from rounded CSV", "concentration or serial-persistence robustness", "runtime authority", "broker authority", "live-trading authority"], "prohibited_inferences": ["do not re-download Yahoo as a replay substitute", "do not claim raw-price lineage is solved"]},
    "decision": {"disposition": "IMMUTABLE_MONTHLY_RECORD_REPLAY_EXACT_RAW_CORPUS_UNSOLVED"},
    "lineage": {"parents": ["P13"], "related": ["P13-R2", "P13-R3"]},
}

p300_release = {
    "schema": "foundry.shared_evidence_claim.v1",
    "evidence_id": "P300:spmo_xmmo_complementarity_rejected:2026-09-10",
    "producer": {"system": "continue-release", "repository": "XoticHaze/CommandCenter", "source_ref": "76d71c845f0869a732a25dee115fb026860f579d", "run_id": "34457853220"},
    "claim": {"claim_type": "diagnostic.p300_momentum_pair_complementarity", "status": "REJECTED", "statement": "sanitized P300 redundancy release shape", "subject": "P300 SPMO/XMMO momentum complementarity", "role": "research_result_consumer", "mechanism": "terminal-result first consumer", "capabilities": ["diagnostic.p300_momentum_pair_complementarity", "diagnostic.portfolio_redundancy"]},
    "authority": {"max_scope": "RESEARCH_ONLY", "automatic_action_allowed": False},
    "evidence": {"inputs": [{"kind": "terminal_scientific_consequence", "identity": "market-research-consume-p300-redundancy-20260910T090820Z"}], "metrics": [{"name": "overall_2017_matched_relative_excess_correlation", "value": 0.5843686009444969}, {"name": "calendar_blocks_below_0_6", "value": 1}], "support": [{"run_id": 34457853220, "job_id": 102808346029, "started_at_utc": "2026-09-10T08:56:06Z", "head_sha": "f524a920eefbae7a74e1f885870ecfcb612fdf7e", "artifact_id": 10144232128, "artifact_sha256": "03ae2d2163c37e4e0b8b9ffae32839e2fe81ae43c4eeb4e10776b4934d42412c"}]},
    "boundaries": {"does_not_establish": ["standalone failure of either momentum survivor", "portfolio allocation authority"], "prohibited_inferences": ["do not optimize pair weights", "do not rescue the pair through a nearby correlation threshold"]},
    "decision": {"disposition": "NAIVE_SPMO_XMMO_COMPLEMENTARITY_REJECTED_STANDALONE_SURVIVORS_PRESERVED"},
    "lineage": {"parents": ["P300", "P290", "P297"], "related": []},
}

p301_p302_release = {
    "schema": "foundry.shared_evidence_claim.v1",
    "evidence_id": "P301-P302:smallvalue_momentum_orthogonality_supported:2026-09-10",
    "producer": {"system": "continue-release", "repository": "XoticHaze/CommandCenter", "source_ref": "a9a5a3d82d9ad1518c73e9fed02e6dcc6164e0ea", "run_id": "34458926425"},
    "claim": {"claim_type": "diagnostic.p301_p302_smallvalue_momentum_orthogonality", "status": "SUPPORTED", "statement": "sanitized P301/P302 orthogonality release shape", "subject": "P301/P302 momentum-small-value orthogonality", "role": "research_result_consumer", "mechanism": "terminal-result first consumer", "capabilities": ["diagnostic.p301_p302_smallvalue_momentum_orthogonality", "diagnostic.return_source_complementarity"]},
    "authority": {"max_scope": "RESEARCH_ONLY", "automatic_action_allowed": False},
    "evidence": {"inputs": [{"kind": "terminal_scientific_consequence", "identity": "market-research-consume-p301-complementarity-20260910T090850Z"}, {"kind": "terminal_scientific_consequence", "identity": "market-research-consume-p302-complementarity-20260910T090910Z"}], "metrics": [{"name": "spmo_smallvalue_overall_excess_corr", "value": -0.3927906376529453}, {"name": "xmmo_smallvalue_overall_excess_corr", "value": -0.5901127887300728}], "support": [{"run_id": 34458847316, "job_id": 102811578750, "started_at_utc": "2026-09-10T09:06:59Z", "head_sha": "d20b72a272706e4b54f325b06471e559e4f551bf", "artifact_id": 10144633024, "artifact_sha256": "dc16d1e0c83865f7e9b578501d9573310dc3d5dbac2b7c96fb3ff97bf78126a7"}, {"run_id": 34458926425, "job_id": 102811830231, "started_at_utc": "2026-09-10T09:07:51Z", "head_sha": "b2cdfdd9f826f918c3052bc97b91b882ee2e62d2", "artifact_id": 10144667020, "artifact_sha256": "182d9f85f79680e2700dd9b7c8fe7f87251d1d41c30db249445e935ca88522ec"}]},
    "boundaries": {"does_not_establish": ["after-cost portfolio utility", "momentum representative choice", "portfolio allocation authority"], "prohibited_inferences": ["do not optimize weights", "do not stack both momentum sleeves"]},
    "decision": {"disposition": "SMALLVALUE_ORTHOGONALITY_REPLICATED_ACROSS_BOTH_MOMENTUM_SURVIVORS"},
    "lineage": {"parents": ["P301", "P302", "P290", "P297", "P249"], "related": ["P300"]},
}


a = normalize(fixture)
b = normalize(fixture)
assert a == b
assert hashlib.sha256(canonical(a)).hexdigest() == hashlib.sha256(canonical(b)).hexdigest()
assert a["producer"]["source_ref"] == ".github/workflows/example.yml@abc123"
assert a["producer"]["run_id"] == "123"
assert a["evidence"]["metrics"] == [{"name": "delay1.excess_cagr", "value": 0.01, "direction": "DESCRIPTIVE"}]
assert a["boundaries"]["does_not_establish"][-1] == "live-trading authority"
assert a["lineage"]["parents"] == ["PTEST"]
assert a["authority"]["automatic_action_allowed"] is False

p29_a = json.loads(canonical(p29_release))
assert p29_a == json.loads(canonical(p29_release))
assert p29_a["producer"]["run_id"] == "34336319507"
assert p29_a["claim"]["status"] == "MIXED"
assert p29_a["authority"] == {"automatic_action_allowed": False, "max_scope": "RESEARCH_ONLY"}
assert p29_a["evidence"]["parameters"]["execution_delay_grid_days"] == list(range(11))
assert p29_a["evidence"]["parameters"]["no_delay_selection_or_tuning"] is True
assert p29_a["evidence"]["metrics"][1]["value"] == 5 / 11
assert p29_a["evidence"]["metrics"][2]["value"] < 0
assert "preferred execution delay" in p29_a["boundaries"]["does_not_establish"]

p13_a = json.loads(canonical(p13_release))
assert p13_a == json.loads(canonical(p13_release))
assert p13_a["producer"]["run_id"] == "34336946321"
assert p13_a["claim"]["status"] == "MIXED"
assert p13_a["authority"] == {"automatic_action_allowed": False, "max_scope": "RESEARCH_ONLY"}
assert p13_a["evidence"]["parameters"]["source_artifact_id"] == 10093700209
assert p13_a["evidence"]["metrics"][0]["value"] == 92
assert "bit-exact raw-price corpus reproducibility" in p13_a["boundaries"]["does_not_establish"]
assert "concentration or serial-persistence robustness" in p13_a["boundaries"]["does_not_establish"]

p300_sha = validate_release_claim(p300_release)
p301_p302_sha = validate_release_claim(p301_p302_release)
assert p300_release["claim"]["status"] == "REJECTED"
assert p301_p302_release["claim"]["status"] == "SUPPORTED"
assert p300_release["authority"]["automatic_action_allowed"] is False
assert p301_p302_release["authority"]["automatic_action_allowed"] is False
assert p300_release["evidence"]["metrics"][1]["value"] == 1
assert p301_p302_release["evidence"]["metrics"][0]["value"] < 0
assert p301_p302_release["evidence"]["metrics"][1]["value"] < 0

print(json.dumps({"result": "PASS", "legacy_normalized_sha256": hashlib.sha256(canonical(a)).hexdigest(), "p29_release_sha256": hashlib.sha256(canonical(p29_a)).hexdigest(), "p13_release_sha256": hashlib.sha256(canonical(p13_a)).hexdigest(), "p300_release_sha256": p300_sha, "p301_p302_release_sha256": p301_p302_sha, "automatic_action_allowed": False}, sort_keys=True))
