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
    "producer": {
        "system": "research-compute-public",
        "repository": "XoticHaze/research-compute-public-",
        "executions": [{
            "workflow": ".github/workflows/example.yml",
            "run_id": 123,
            "run_started_at": "2026-09-09T00:00:00Z",
            "head_sha": "abc123",
            "artifact_digest": "sha256:deadbeef",
        }],
    },
    "claim": {
        "claim_type": "diagnostic.legacy_acceptance",
        "status": "MIXED",
        "statement": "sanitized acceptance fixture",
        "subject": "legacy adapter acceptance",
        "hypothesis_id": "PTEST",
        "capabilities": ["diagnostic.legacy_acceptance"],
    },
    "authority": {"max_scope": "RESEARCH_ONLY", "automatic_action_allowed": False},
    "evidence": {"metrics": {"delay1": {"excess_cagr": 0.01}}, "decision": "SANITIZED_ACCEPTANCE"},
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
print(json.dumps({"result": "PASS", "normalized_sha256": hashlib.sha256(canonical(a)).hexdigest(), "automatic_action_allowed": False}, sort_keys=True))
