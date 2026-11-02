import test from "node:test";
import assert from "node:assert/strict";
import {compareV4Methods as compare} from "../src/workforce_v4_value_gate.js";
const ROLE="cc.receipt_intelligence";
function data(n=20,{modelMs=4000,baselineMs=20000,strongerMs=12000,
  modelAcc=true,review=true,correlated=false,unknownCost=false,held=false}={}){
  return Array.from({length:n},(_,i)=>{
    const input=i.toString(16).padStart(64,"0");
    const o=(kind,ms,correct=true)=>({
      input_sha:input,correct,observed:true,
      evidence_id:"receipt-"+kind+"-"+i,
      total_seconds_ms:ms,cost_usd:unknownCost&&kind==="small_model"?null:0
    });
    return {
      role:ROLE,task_id:"task-"+String(i).padStart(8,"0"),
      mechanism_id:"mechanism-"+String(correlated?i%5:i).padStart(6,"0"),
      format_family:"format-"+(i%3===0?"alpha":i%3===1?"bravo":"delta"),
      input_sha:input,verified_origin:true,
      deterministic:o("deterministic",baselineMs),
      small_model:o("small_model",modelMs,modelAcc),
      stronger_worker:o("stronger_worker",strongerMs),
      human_review_accepted:review,critical_authority_violations:0,
      invented_source_refs:0,provider_held:held
    };
  });
}
test("unmeasured comparisons cannot recommend a model or produce admission",()=>{
  const r=compare({role:ROLE,measurements:[]});
  assert.equal(r.recommendation,"INSUFFICIENT_INDEPENDENT_EVIDENCE");
  assert.equal(r.median_saved_ms,null);
  assert.equal(r.production_admitted,false);
  assert.equal(r.private_workload_admitted,false);
});
test("even apparent model benefit stays research-only after 20 distinct observed cases",()=>{
  const r=compare({role:ROLE,measurements:data()});
  assert.equal(r.recommendation,"RESEARCH_SHADOW_CANDIDATE_NOT_ADMITTED");
  assert.equal(r.median_saved_fraction,.8);
  assert.equal(r.measured_cost_advantage_verified,false);
  assert.equal(r.signed_origin_verified_by_this_module,false);
  assert.equal(r.authority_granted,false);
});
test("model slower, human-rejected, or unpriced means no demonstrated advantage",()=>{
  assert.equal(compare({role:ROLE,measurements:data(20,{baselineMs:1000})}).recommendation,
    "DETERMINISTIC_PREFERRED_OR_VALUE_NOT_PROVEN");
  assert.equal(compare({role:ROLE,measurements:data(20,{review:false})}).recommendation,
    "KEEP_DETERMINISTIC_OR_STRONGER_BASELINE");
  assert.equal(compare({role:ROLE,measurements:data(20,{unknownCost:true})}).recommendation,
    "DETERMINISTIC_PREFERRED_OR_VALUE_NOT_PROVEN");
});
test("repeated case mechanisms are not twenty independent holdouts",()=>{
  const r=compare({role:ROLE,measurements:data(20,{correlated:true})});
  assert.equal(r.distinct_mechanisms,5);
  assert.equal(r.recommendation,"INSUFFICIENT_INDEPENDENT_EVIDENCE");
  assert.equal(compare({role:ROLE,measurements:data(19)}).recommendation,
    "INSUFFICIENT_INDEPENDENT_EVIDENCE");
});
test("receipt mismatch and critical unsafe proposal fail closed",()=>{
  const bad=data();bad[0].small_model.input_sha="f".repeat(64);
  assert.throws(()=>compare({role:ROLE,measurements:bad}),/untrusted_or_unmeasured_comparison/);
  const forged=data();forged[1].invented_source_refs=1;
  assert.equal(compare({role:ROLE,measurements:forged}).recommendation,
    "KEEP_DETERMINISTIC_OR_STRONGER_BASELINE");
  const held=data(20,{held:true});
  assert.equal(compare({role:ROLE,measurements:held}).recommendation,
    "KEEP_DETERMINISTIC_OR_STRONGER_BASELINE");
  const dup=data();dup[1].task_id=dup[0].task_id;
  assert.throws(()=>compare({role:ROLE,measurements:dup}),/untrusted_or_unmeasured_comparison/);
});
