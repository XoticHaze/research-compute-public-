import hashlib
import json
from pathlib import Path

PRODUCT_HEAD = "afbbd8441c1f42b6b27e323aa98d72d4373fd36b"


def reconcile(runtime_id, rows):
    identified = [row for row in rows if row.get("runtime_id")]
    matches = [row["experiment_id"] for row in identified if row["runtime_id"] == runtime_id and row.get("experiment_id")]
    if matches:
        state = "MATCH"
    elif rows and len(identified) == len(rows):
        state = "NO_MATCH"
    else:
        state = "UNRESOLVED"
    preferred = matches[0] if len(matches) == 1 else ""
    return {"state": state, "matches": matches, "preferred_experiment_id": preferred}


def context(runtime_id, reconciliation):
    preferred = reconciliation["preferred_experiment_id"]
    return {
        "review_runtime": runtime_id,
        "destination": "Experiment Review",
        "authority": "CONTEXT ONLY",
        "attributed_experiment": preferred or None,
        "attribution_basis": "UNIQUE RUNTIME MATCH" if preferred else None,
    }


def main():
    cases = {
        "unique_match": reconcile("runtime-target", [
            {"experiment_id": "exp-other", "runtime_id": "runtime-other"},
            {"experiment_id": "exp-target", "runtime_id": "runtime-target"},
        ]),
        "multiple_match": reconcile("runtime-target", [
            {"experiment_id": "exp-a", "runtime_id": "runtime-target"},
            {"experiment_id": "exp-b", "runtime_id": "runtime-target"},
        ]),
        "no_match": reconcile("runtime-target", [
            {"experiment_id": "exp-other", "runtime_id": "runtime-other"},
        ]),
        "unresolved": reconcile("runtime-target", [
            {"experiment_id": "exp-unknown"},
        ]),
    }
    contexts = {name: context("runtime-target", result) for name, result in cases.items()}

    assert cases["unique_match"] == {
        "state": "MATCH",
        "matches": ["exp-target"],
        "preferred_experiment_id": "exp-target",
    }
    assert contexts["unique_match"]["attributed_experiment"] == "exp-target"
    assert contexts["unique_match"]["attribution_basis"] == "UNIQUE RUNTIME MATCH"
    assert cases["multiple_match"]["state"] == "MATCH"
    assert cases["multiple_match"]["matches"] == ["exp-a", "exp-b"]
    assert cases["multiple_match"]["preferred_experiment_id"] == ""
    assert contexts["multiple_match"]["attributed_experiment"] is None
    assert contexts["multiple_match"]["attribution_basis"] is None
    assert cases["no_match"] == {"state": "NO_MATCH", "matches": [], "preferred_experiment_id": ""}
    assert contexts["no_match"]["attributed_experiment"] is None
    assert cases["unresolved"] == {"state": "UNRESOLVED", "matches": [], "preferred_experiment_id": ""}
    assert contexts["unresolved"]["attributed_experiment"] is None
    assert all(item["authority"] == "CONTEXT ONLY" for item in contexts.values())

    semantic_payload = json.dumps({"cases": cases, "contexts": contexts}, sort_keys=True, separators=(",", ":")).encode()
    receipt = {
        "schema": "mm.model_lab_runtime_focus_sanitized_acceptance.v2",
        "product_head": PRODUCT_HEAD,
        "acceptance_class": "SANITIZED_OPERATOR_SELECTION_AND_ATTRIBUTION_CONTEXT_SEMANTICS",
        "protected_boundaries": {
            "strategy_spec_mutation": False,
            "runtime_authority_change": False,
            "portfolio_allocation": False,
            "broker_submission": False,
            "live_trading_change": False,
        },
        "cases": cases,
        "contexts": contexts,
        "semantic_sha256": hashlib.sha256(semantic_payload).hexdigest(),
        "result": "PASS",
    }
    Path("model-lab-runtime-focus-acceptance-r1-result.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
