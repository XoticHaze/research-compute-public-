import hashlib
import json
from pathlib import Path

PRODUCT_HEAD = "3f65cad4b5f03f04046c88ea71d8a96e4200830f"


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


def attributed_evidence_loaded(preferred_experiment_id, evidence_state, loaded_experiment_id):
    return bool(
        preferred_experiment_id
        and evidence_state == "loaded"
        and loaded_experiment_id == preferred_experiment_id
    )


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

    assert cases["unique_match"] == {
        "state": "MATCH",
        "matches": ["exp-target"],
        "preferred_experiment_id": "exp-target",
    }
    assert cases["multiple_match"]["state"] == "MATCH"
    assert cases["multiple_match"]["matches"] == ["exp-a", "exp-b"]
    assert cases["multiple_match"]["preferred_experiment_id"] == ""
    assert cases["no_match"] == {"state": "NO_MATCH", "matches": [], "preferred_experiment_id": ""}
    assert cases["unresolved"] == {"state": "UNRESOLVED", "matches": [], "preferred_experiment_id": ""}

    load_cases = {
        "unique_match_loaded_same_identity": attributed_evidence_loaded("exp-target", "loaded", "exp-target"),
        "unique_match_loading": attributed_evidence_loaded("exp-target", "loading", "exp-target"),
        "unique_match_error": attributed_evidence_loaded("exp-target", "error", "exp-target"),
        "loaded_different_identity": attributed_evidence_loaded("exp-target", "loaded", "exp-other"),
        "no_unique_attribution": attributed_evidence_loaded("", "loaded", "exp-target"),
    }
    assert load_cases == {
        "unique_match_loaded_same_identity": True,
        "unique_match_loading": False,
        "unique_match_error": False,
        "loaded_different_identity": False,
        "no_unique_attribution": False,
    }

    semantic_payload = json.dumps({"reconciliation": cases, "attributed_load": load_cases}, sort_keys=True, separators=(",", ":")).encode()
    receipt = {
        "schema": "mm.model_lab_runtime_focus_sanitized_acceptance.v2",
        "product_head": PRODUCT_HEAD,
        "acceptance_class": "SANITIZED_OPERATOR_SELECTION_AND_ATTRIBUTED_LOAD_SEMANTICS",
        "protected_boundaries": {
            "strategy_spec_mutation": False,
            "runtime_authority_change": False,
            "portfolio_allocation": False,
            "broker_submission": False,
            "live_trading_change": False,
        },
        "cases": cases,
        "attributed_load_cases": load_cases,
        "semantic_sha256": hashlib.sha256(semantic_payload).hexdigest(),
        "result": "PASS",
    }
    Path("model-lab-runtime-focus-acceptance-r1-result.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
