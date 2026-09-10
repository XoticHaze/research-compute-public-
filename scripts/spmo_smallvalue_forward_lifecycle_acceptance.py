import hashlib
import json
from datetime import date


def h(v):
    return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",", ":")).encode()).hexdigest()

contract={"id":"spmo-smallvalue-fixed50-forward-20260910-r1","decision":"2026-09-30","maturity":"2026-10-30","candidate":{"SPMO":.5,"IJS":.5},"matched":{"SPY":.5,"IJR":.5},"opportunity":["SPY","QQQ"],"cost_bps":[25,50],"automatic_action_allowed":False,"allocation_authority":False}

def seal(today):
    if today != date.fromisoformat(contract["decision"]): raise RuntimeError("not exact decision boundary")
    identity={"contract_sha256":h(contract),"decision_date":contract["decision"],"maturity_date":contract["maturity"],"candidate":contract["candidate"],"matched":contract["matched"],"opportunity":contract["opportunity"],"cost_bps":contract["cost_bps"]}
    return {"observation_id":f"spmo-smallvalue:{contract['decision']}:{h(identity)[:20]}","identity":identity,"identity_sha256":h(identity),"selection_frozen_before_outcome":True,"outcome_fields_present":False,"automatic_action_allowed":False,"allocation_authority":False}

def mature(d, today, rr):
    if today < date.fromisoformat(contract["maturity"]): raise RuntimeError("premature outcome")
    if rr["start"] != contract["decision"] or rr["end"] != contract["maturity"]: raise RuntimeError("interval mismatch")
    for x in ("SPMO","IJS","SPY","IJR","QQQ"):
        assert x in rr["r"]
    r=rr["r"]; gross=.5*r["SPMO"]+.5*r["IJS"]; drift=.5*(1+r["SPMO"])/(1+gross); turnover=2*abs(drift-.5); matched=.5*r["SPY"]+.5*r["IJR"]
    scores={}
    for bp in contract["cost_bps"]:
        net=gross-turnover*bp/10000
        scores[str(bp)]={"net":net,"turnover":turnover,"matched_excess":net-matched,"spy_excess":net-r["SPY"],"qqq_excess":net-r["QQQ"]}
    return {"observation_id":d["observation_id"],"decision_identity_sha256":d["identity_sha256"],"returns_sha256":h(rr),"scores":scores,"automatic_action_allowed":False,"allocation_authority":False}

try:
    seal(date(2026,9,10)); raise AssertionError("pre-boundary seal must fail")
except RuntimeError: pass
D=seal(date(2026,9,30))
RR={"start":"2026-09-30","end":"2026-10-30","source":{"provider":"sanitized-fixed-fixture","input_identity":"sha256:test"},"r":{"SPMO":.10,"IJS":.02,"SPY":.04,"IJR":.01,"QQQ":.05}}
try:
    mature(D,date(2026,10,29),RR); raise AssertionError("prematurity must fail")
except RuntimeError: pass
O=mature(D,date(2026,10,30),RR)
expected_gross=.06; expected_drift=.5*1.10/1.06; expected_turnover=2*abs(expected_drift-.5); expected_matched=.025
assert O["scores"]["25"]["turnover"] == expected_turnover
assert abs(O["scores"]["25"]["net"]-(expected_gross-expected_turnover*.0025))<1e-15
assert abs(O["scores"]["25"]["matched_excess"]-(O["scores"]["25"]["net"]-expected_matched))<1e-15
assert D["outcome_fields_present"] is False
assert D["automatic_action_allowed"] is O["automatic_action_allowed"] is False
assert D["allocation_authority"] is O["allocation_authority"] is False
print(json.dumps({"result":"PASS","contract_sha256":h(contract),"decision_identity_sha256":D["identity_sha256"],"returns_sha256":O["returns_sha256"],"turnover":expected_turnover,"automatic_action_allowed":False,"allocation_authority":False},sort_keys=True))
