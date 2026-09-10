import hashlib
import json


def canonical(v):
    return json.dumps(v, sort_keys=True, separators=(",", ":")).encode()


def validate(claim, status, capability):
    assert claim["schema"] == "foundry.shared_evidence_claim.v1"
    assert claim["claim"]["status"] == status
    assert capability in claim["claim"]["capabilities"]
    assert claim["authority"]["max_scope"] == "RESEARCH_ONLY"
    assert claim["authority"]["automatic_action_allowed"] is False
    assert claim["evidence"]["support"]
    for row in claim["evidence"]["support"]:
        for key in ("run_id", "job_id", "started_at_utc", "head_sha", "artifact_id", "artifact_sha256"):
            assert row[key]
    assert claim["boundaries"]["does_not_establish"]
    assert claim["boundaries"]["prohibited_inferences"]
    assert claim["decision"]["disposition"]
    return hashlib.sha256(canonical(claim)).hexdigest()


p305 = {
    "schema":"foundry.shared_evidence_claim.v1","evidence_id":"P305:spmo_smallvalue_cost_robustness_supported:2026-09-10",
    "producer":{"system":"continue-release","repository":"XoticHaze/CommandCenter","source_ref":"b1f8f08ef346a9c51e96fa596ef4b300b0db1391","run_id":"34459425610"},
    "claim":{"claim_type":"diagnostic.p305_spmo_smallvalue_cost_robustness","status":"SUPPORTED","statement":"sanitized P305 cost robustness","subject":"P305 fixed SPMO+IJS cost robustness","capabilities":["diagnostic.p305_spmo_smallvalue_cost_robustness","diagnostic.transaction_cost_robustness"]},
    "authority":{"max_scope":"RESEARCH_ONLY","automatic_action_allowed":False},
    "evidence":{"inputs":[{"kind":"terminal_scientific_consequence","identity":"P305"}],"metrics":[{"name":"50bp_2017_matched_excess_cagr","value":0.023170400749996434}],"support":[{"run_id":34459425610,"job_id":102813444036,"started_at_utc":"2026-09-10T09:13:15Z","head_sha":"f020eecd76f7edd8ed0a2f5ee8faf3a1a6c9e533","artifact_id":10144873068,"artifact_sha256":"8d6d9f4a4547406045ad217f925258ecb443edf6ee0a00acd097b914ad418b10"}]},
    "boundaries":{"does_not_establish":["optimal weights","allocation authority"],"prohibited_inferences":["do not mine cost grid","do not retune weights"]},
    "decision":{"disposition":"FIXED_SPMO_SMALLVALUE_AFTER_COST_ROBUSTNESS_SUPPORTED"},"lineage":{"parents":["P305","P304","P303"]}
}


def risk_claim(pid, run_id, job_id, started, head, artifact_id, digest, capability, subject):
    return {
        "schema":"foundry.shared_evidence_claim.v1","evidence_id":f"{pid}:risk_shaping_only:2026-09-10",
        "producer":{"system":"continue-release","repository":"XoticHaze/CommandCenter","source_ref":pid,"run_id":str(run_id)},
        "claim":{"claim_type":capability,"status":"MIXED","statement":f"sanitized {subject} risk-shaping only","subject":subject,"capabilities":[capability,"diagnostic.drawdown_shaping"]},
        "authority":{"max_scope":"RESEARCH_ONLY","automatic_action_allowed":False},
        "evidence":{"inputs":[{"kind":"terminal_scientific_consequence","identity":pid}],"metrics":[{"name":"standalone_alpha_supported","value":False},{"name":"drawdown_shaping_preserved","value":True}],"support":[{"run_id":run_id,"job_id":job_id,"started_at_utc":started,"head_sha":head,"artifact_id":artifact_id,"artifact_sha256":digest}]},
        "boundaries":{"does_not_establish":["standalone alpha","allocation authority"],"prohibited_inferences":["do not treat lower drawdown as alpha","do not parameter-rescue"]},
        "decision":{"disposition":f"{pid}_ALPHA_REJECTED_RISK_SHAPING_ONLY"},"lineage":{"parents":[pid]}
    }

p306 = risk_claim("P306",34459648372,102814155627,"2026-09-10T09:15:39Z","bc1568e8beb2ba5c652663c5b8ede9874b516584",10144963310,"2b27bb4cf15503d1cbc267d3c1a546566c70002f50cfb7bb04dda40c183f95d8","diagnostic.p306_lowvol_risk_shaping_only","P306 low-volatility factor")
p307 = risk_claim("P307",34459804845,102814668381,"2026-09-10T09:17:22Z","35106403336a44edfe9e0190f2fc70841b444391",10145032012,"5ac19f64e5bcb668ea723f83151c0da2dc17057227d9b4c27ef038ca71532e68","diagnostic.p307_dividend_growth_risk_shaping_only","P307 dividend-growth factor")

out = {
    "p305_sha256": validate(p305,"SUPPORTED","diagnostic.p305_spmo_smallvalue_cost_robustness"),
    "p306_sha256": validate(p306,"MIXED","diagnostic.p306_lowvol_risk_shaping_only"),
    "p307_sha256": validate(p307,"MIXED","diagnostic.p307_dividend_growth_risk_shaping_only"),
    "automatic_action_allowed": False,
    "allocation_authority": False,
    "result":"PASS"
}
print(json.dumps(out, sort_keys=True))
