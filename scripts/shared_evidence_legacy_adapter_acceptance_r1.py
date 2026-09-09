import hashlib
import json
import re


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

print(json.dumps({"result": "PASS", "legacy_normalized_sha256": hashlib.sha256(canonical(a)).hexdigest(), "p29_release_sha256": hashlib.sha256(canonical(p29_a)).hexdigest(), "p13_release_sha256": hashlib.sha256(canonical(p13_a)).hexdigest(), "automatic_action_allowed": False}, sort_keys=True))
