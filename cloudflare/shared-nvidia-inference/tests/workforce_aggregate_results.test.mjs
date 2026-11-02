import test from "node:test";
import assert from "node:assert/strict";
import {newCampaign,runCampaign} from "../scripts/workforce_campaign_cli.mjs";
import {aggregateWorkforceCampaigns as aggregate} from "../scripts/workforce_aggregate_results.mjs";
import {CASES} from "../src/workforce_domain_suite.js";
const SHA="ab".repeat(20),OTHER="cd".repeat(20);
function receipt({model_index,case_index},model="nvidia/synthetic-model"){
 const c=CASES[case_index],keys=Object.keys(c.expected);
 return {schema:"commandcenter.model_workforce_provider_case.v1",
  model_index,model,case_id:c.id,case_index,role:c.role,domain:c.domain,
  baseline:c.baseline,priority:c.priority,status:"scored_pass",
  provider_calls:2,catalog_status:200,completion_status:200,
  catalog_count:61,eligible_model_count:61,finish_reason:"stop",
  prompt_tokens:100,completion_tokens:80,reasoning_tokens:null,
  first_pass:true,format_valid:true,fields_correct:keys.length,
  fields_total:keys.length,field_checks:Object.fromEntries(keys.map(k=>[k,true])),
  human_review_required:false,latency_ms:800,
  tool_calls_proposed:false,tools_executed:false,
  answer_exported:false,private_input_used:false,production_authorized:false};
}
async function run(id,caseIndex=0,model="nvidia/synthetic-model"){
 return runCampaign({state:newCampaign({
  sourceSha:SHA,runId:"github-"+id,caseIndex
 }),limit:1,callCase:async s=>receipt(s,model)});
}
test("independent same-source paired cases combine without fabricated promotion",async()=>{
 const a=await run("900001",0),b=await run("900002",1);
 const v=aggregate({sourceSha:SHA,campaigns:[a,b]});
 assert.equal(v.campaign_count,2);
 assert.equal(v.unique_scored_or_review_cases,2);
 assert.equal(v.provider_http_calls,4);
 assert.equal(v.readiness.rows.length,1);
 assert.equal(v.readiness.rows[0].coverage_complete,true);
 assert.equal(v.readiness.rows[0].first_pass_rate,1);
 assert.equal(v.production_admitted,false);
 assert.equal(v.raw_model_responses_exported,false);
 assert.deepEqual(v.run_ids,["github-900001","github-900002"]);
});
test("cross-run duplicates and reused provenance never earn additional credit",async()=>{
 const a=await run("900001");
 assert.throws(()=>aggregate({sourceSha:SHA,campaigns:[a,a]}),
  /duplicate_execution_run/);
 assert.throws(()=>aggregate({sourceSha:SHA,campaigns:[a,{
  ...a,run_id:"github-900002"
 }]}),/duplicate_model_case_cross_run/);
});
test("source gold revisions cannot be mixed into one scoreboard",async()=>{
 const a=await run("900001"),b=await run("900002",1);
 assert.throws(()=>aggregate({sourceSha:SHA,campaigns:[a,{
  ...b,source_sha:OTHER
 }]}),/source_or_execution_identity_mismatch/);
 assert.throws(()=>aggregate({sourceSha:SHA,campaigns:[{
  ...a,run_id:"not-a-verified-github-run"
 }]}),/source_or_execution_identity_mismatch/);
});
test("catalog index reuse is separated by authenticated model identity",async()=>{
 const a=await run("900001",0,"nvidia/synthetic-model");
 const b=await run("900002",1,"nvidia/another-model");
 const v=aggregate({sourceSha:SHA,campaigns:[a,b]});
 assert.equal(v.readiness.rows.length,2);
 assert(v.readiness.rows.every(r=>r.coverage_complete===false));
 assert.equal(v.unique_scored_or_review_cases,2);
});
test("unsafe receipts fail at original sanitizer, not only final readiness",async()=>{
 const a=await run("900001");
 for(const bad of [{fields_total:0,fields_correct:0},
  {field_checks:null},{answer_exported:true}]){
  const broken={...a,observations:[{...a.observations[0],...bad}]};
  assert.throws(()=>aggregate({sourceSha:SHA,campaigns:[broken]}),
   /unsafe_campaign_observation/);
 }
});
