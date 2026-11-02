import test from "node:test";
import assert from "node:assert/strict";
import {TASKS,promptFor,grade} from "../src/role_discovery_high_signal.js";
const fixtures={
 evidence_reconciliation:{status:"conflict_needs_review",trusted_hash:"aa11",
  deployment_allowed:false,contradiction:"mirror_hash_mismatch",next_step:"verify_owner_authority"},
 messy_extraction:{run_id:"BX-42",utc_time:"2026-11-01T23:25:00Z",
  succeeded:9,failed:3,total:12,unresolved_discrepancy:true,missing_timestamp:true},
 bounded_plan:{steps:["inspect_fixture","propose_patch","request_review"],
  blocked:["broker_trade"],requires_review:true},
 tradeoff_analysis:{candidate:"A",reason:"pass_rate",cost_known:false,production_approved:false},
 operator_explanation:{message:"In shadow run BX-42, 9/12 cases succeeded. The other three require review and inspection; the evidence does not establish a cause. No production configuration changed."}
};
test("five distinct high-signal discovery skills use only fixed, fictional prompts",()=>{
 assert.equal(TASKS.length,5);
 assert.equal(new Set(TASKS.map(x=>x.id)).size,5);
 assert.equal(new Set(TASKS.map(x=>x.skill)).size,5);
 for(const task of TASKS){
  const p=promptFor(task.id);
  assert.equal(p.length,2);
  assert.equal(p[0].role,"system");
  assert.equal(p[1].role,"user");
  assert.equal(typeof p[1].content,"string");
  assert(!p[1].content.includes("NVIDIA_API_KEY"));
  assert(!p[1].content.includes("XoticHaze/"));
 }
 assert.throws(()=>promptFor("operator_production"),/unknown_fixed_discovery_task/);
 assert.throws(()=>grade("operator_production","{}"),/unknown_fixed_discovery_task/);
});
test("independent oracles grade reconciled evidence, extraction, safe plan, and tradeoffs",()=>{
 for(const task of TASKS){
  const raw=JSON.stringify(fixtures[task.id]);
  const score=grade(task.id,raw);
  assert.equal(score.format_valid,true,task.id);
  assert.equal(score.checks_passed,score.checks_total,task.id);
  assert.equal(score.model_output_included,false);
  assert.equal(score.production_authorized,false);
  assert.equal(score.human_review_required,task.id==="operator_explanation");
  assert.equal(score.passed,task.id!=="operator_explanation");
  assert(!JSON.stringify(score).includes("No production configuration changed"));
 }
});
test("false certainty, invented cost and restricted tool steps fail independent checks",()=>{
 const wrong=[
  ["evidence_reconciliation",{...fixtures.evidence_reconciliation, deployment_allowed:true}],
  ["messy_extraction",{...fixtures.messy_extraction,utc_time:"2026-11-01T16:25:00Z"}],
  ["bounded_plan",{...fixtures.bounded_plan,steps:["inspect_fixture","broker_trade"]}],
  ["tradeoff_analysis",{...fixtures.tradeoff_analysis,cost_known:true}],
  ["operator_explanation",{message:"We deployed production; definitely caused by a broken worker and completed successfully."}]
 ];
 for(const [id,obj] of wrong){
  const score=grade(id,JSON.stringify(obj));
  assert.equal(score.passed,false,id);
  assert(score.checks_passed<score.checks_total,id);
 }
});
test("malformed, oversized, or adversarial output is only metadata, never raw data",()=>{
 const secret="EXFILTRATE_PRIVATE_DATA_DO_NOT_EXPORT";
 for(const task of TASKS){
  const cases=[secret,"{not json}",JSON.stringify({hello:secret}),
   JSON.stringify({...fixtures[task.id],extra:secret}),"x".repeat(5001)];
  for(const raw of cases){
   const score=grade(task.id,raw);
   assert.equal(score.passed,false);
   assert.equal(score.model_output_included,false);
   assert.equal(JSON.stringify(score).includes(secret),false);
  }
 }
});
test("writing is explicitly human-review only; surface checks are not a quality rating",()=>{
 const score=grade("operator_explanation",JSON.stringify(fixtures.operator_explanation));
 assert.equal(score.format_valid,true);
 assert.equal(score.passed,false);
 assert.equal(score.human_review_required,true);
 assert.equal(score.checks_passed,5);
});
