import test from "node:test";
import assert from "node:assert/strict";
import {CASES} from "../src/workforce_domain_suite.js";
import {evaluateWorkforceReadiness as evaluate} from "../src/workforce_role_selector.js";
const MODEL="nvidia/fictional-shadow";
function receipt(caseIndex,{status="scored_pass",latency_ms=600,model=MODEL}={}){
 const c=CASES[caseIndex],scoreable=!c.human_review_required;
 return{schema:"commandcenter.model_workforce_provider_case.v1",
  case_id:c.id,case_index:caseIndex,role:c.role,domain:c.domain,
  model,model_index:0,baseline:c.baseline,priority:c.priority,
  status:c.human_review_required?"human_review_required":status,
  first_pass:scoreable&&status==="scored_pass",
  latency_ms,completion_status:200,prompt_tokens:160,completion_tokens:300,
  answer_exported:false,private_input_used:false,
  production_authorized:false,tools_executed:false};
}
test("measured economic value can favor shadow helper without granting runtime access",()=>{
 const evidence=[receipt(0),receipt(1)];
 const noMeasure=evaluate({receipts:evidence});
 const row=noMeasure.rows[0];
 assert.equal(row.covered,2);
 assert.equal(row.expected_cases,2);
 assert.equal(row.coverage_complete,true);
 assert.equal(row.first_pass_rate,1);
 assert.equal(row.recommendation,"compare_against_baseline");
 assert.equal(row.seconds_saved_per_case,null);
 assert.equal(row.provider_cost_usd,null);
 assert.equal(row.production_admitted,false);
 const key=MODEL+"|"+row.role;
 const benefit=evaluate({receipts:evidence,measurements:{
  [key]:{baseline_seconds:40,review_seconds:8,rework_seconds:0,provider_cost_usd:null,method:"observed_comparison",evidence_id:"synthetic-proof-0001"}
 }}).rows[0];
 assert.equal(benefit.recommendation,"promising_shadow_candidate");
 assert(benefit.seconds_saved_per_case>30);
 assert.equal(benefit.production_admitted,false);
 assert.equal(benefit.provider_cost_usd,null);
 const loss=evaluate({receipts:evidence,measurements:{
  [key]:{baseline_seconds:1,review_seconds:8,rework_seconds:0,provider_cost_usd:null,method:"observed_comparison",evidence_id:"synthetic-proof-0001"}
 }}).rows[0];
 assert.equal(loss.recommendation,"deterministic_or_fleet_preferred");
 assert(loss.seconds_saved_per_case<0);
});
test("real failure categories prevent paper-perfect scores and replayed proofs",()=>{
 assert.equal(evaluate({receipts:[receipt(0)]}).rows[0].recommendation,"insufficient_domain_coverage");
 const oneFail=evaluate({receipts:[receipt(0),receipt(1,{status:"scored_fail"})]}).rows[0];
 assert.equal(oneFail.recommendation,"bounded_helper_with_verifier");
 assert.equal(oneFail.first_pass_rate,.5);
 const provider=evaluate({receipts:[receipt(0),receipt(1,{status:"provider_rate_limited"})]}).rows[0];
 assert.equal(provider.recommendation,"investigate_provider_reliability");
 const unsafe=evaluate({receipts:[receipt(0),receipt(1,{status:"tool_attempt_rejected"})]}).rows[0];
 assert.equal(unsafe.recommendation,"reject_protected_tool_work");
 assert.throws(()=>evaluate({receipts:[receipt(0),receipt(0)]}),/duplicated_case/);
 assert.throws(()=>evaluate({receipts:[{...receipt(0),answer_exported:true}]}),/untrusted_provider_receipt/);
});
test("operator writing cannot earn automatic quality credit",()=>{
 const row=evaluate({receipts:[receipt(30),receipt(31)]}).rows[0];
 assert.equal(row.human_review_pending,2);
 assert.equal(row.objectively_graded,0);
 assert.equal(row.first_pass_rate,null);
 assert.equal(row.recommendation,"needs_blind_human_review");
});
test("no fabricated data, no inferred provider pricing, and stable empty-state output",()=>{
 const empty=evaluate({receipts:[]});
 assert.equal(empty.rows.length,0);
 assert.equal(empty.expected_cases,92);
 assert.equal(empty.any_production_admission,false);
 assert.equal(empty.provider_prices_inferred,false);
 assert.throws(()=>evaluate({receipts:[receipt(0)],measurements:{
  [MODEL+"|"+CASES[0].role]:{baseline_seconds:"15",review_seconds:0,rework_seconds:0,provider_cost_usd:null,method:"observed_comparison",evidence_id:"synthetic-proof-0001"}
 }}),/invalid_or_unmeasured_baseline/);
});
