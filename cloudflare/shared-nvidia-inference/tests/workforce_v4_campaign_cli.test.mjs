import test from "node:test";
import assert from "node:assert/strict";
import {V4_MECHANISM_HOLDOUTS} from "../src/workforce_v4_mechanism_holdout.js";
import {sanitizeV4MechanismReceipt} from "../local-probe/src/workforce_v4_receipt.js";
import {newV4Campaign,runV4Campaign,checkV4Campaign,validateV4Host} from "../scripts/workforce_v4_campaign_cli.mjs";
const SHA="ab".repeat(20),ID="github-41460000000";
function fixture(i,status="human_review_required"){
 const c=V4_MECHANISM_HOLDOUTS[i],hold=status==="provider_rate_limited";
 return sanitizeV4MechanismReceipt({
  schema:"commandcenter.nvidia_workforce_v4_provider_case.v1",
  cohort:"mechanism_v4",case_id:c.id,case_index:i,mechanism_id:c.mechanism_id,
  role:c.role,model_index:0,model:"poolside/laguna-xs-2.1",
  status,provider_calls:2,catalog_status:200,completion_status:hold?429:200,
  finish_reason:hold?"not_recorded":"stop",prompt_tokens:hold?null:500,
  completion_tokens:hold?null:120,latency_ms:1450,
  objective_label_pass:!hold,first_pass:false,
  human_review_status:"unreviewed",full_task_accepted:false,
  format_valid:!hold,fields_correct:hold?0:4,fields_total:4,
  invalid_ref_count:0,critical_authority_violation:false,
  tool_calls_proposed:false,tools_executed:false,answer_exported:false,
  raw_response_exported:false,private_input_used:false,production_admitted:false
 });
}
test("bounded 8-case run checkpoints every sanitized result without leak or authority",async()=>{
 const checkpoints=[],state=newV4Campaign({sourceSha:SHA,runId:ID,modelIndex:0,caseIndex:0});
 const out=await runV4Campaign({state,limit:8,callCase:async ({case_index})=>fixture(case_index),
  onCheckpoint:async value=>checkpoints.push(value)});
 assert.equal(out.observations.length,8);
 assert.equal(out.next_case_index,8);
 assert.equal(out.provider_calls,8);
 assert.equal(out.provider_http_calls,16);
 assert.equal(checkpoints.length,8);
 assert.deepEqual(checkpoints.map(x=>x.observations.length),[1,2,3,4,5,6,7,8]);
 assert.equal(out.production_admitted,false);
 assert(!JSON.stringify(out).includes("rationale"));
 assert.equal(checkV4Campaign(out).size,8);
 const resumed=await runV4Campaign({state:out,limit:4,callCase:async ({case_index})=>fixture(case_index)});
 assert.equal(resumed.next_case_index,12);
 assert.equal(resumed.provider_calls,12);
});
test("provider hold preserves exact case for separately admitted retry",async()=>{
 const out=await runV4Campaign({state:newV4Campaign({sourceSha:SHA,runId:ID,modelIndex:0,caseIndex:3}),
  limit:8,callCase:async ({case_index})=>fixture(case_index,"provider_rate_limited")});
 assert.equal(out.status,"provider_hold");
 assert.equal(out.observations.length,0);
 assert.equal(out.held_attempts.length,1);
 assert.equal(out.next_case_index,3);
 const retried=await runV4Campaign({state:out,limit:1,callCase:async ({case_index})=>fixture(case_index)});
 assert.equal(retried.next_case_index,4);
 assert.equal(retried.held_attempts.length,1);
});
test("invalid source, budget, spoofed counter and forged result fail before publication",async()=>{
 const state=newV4Campaign({sourceSha:SHA,runId:ID,modelIndex:0,caseIndex:0});
 for(const limit of [0,-1,9,"1",1.4])await assert.rejects(
  runV4Campaign({state,limit,callCase:async()=>fixture(0)}),/invalid_v4_campaign_budget/);
 for(const n of [60,61,-1])assert.throws(
  ()=>newV4Campaign({sourceSha:SHA,runId:ID,modelIndex:0,caseIndex:n}),/invalid_v4_campaign_origin/);
 assert.throws(()=>checkV4Campaign({...state,production_admitted:true}),/invalid_v4_campaign_state/);
 assert.throws(()=>checkV4Campaign({...state,provider_http_calls:1}),/v4_provider_call_count_mismatch/);
 const cleaned=await runV4Campaign({state,limit:1,callCase:async()=>({...fixture(0),answer:"PRIVATE"})});
 assert.equal(cleaned.observations.length,1);
 assert(!JSON.stringify(cleaned).includes("PRIVATE"));
 assert.equal(cleaned.production_admitted,false);
});
test("host validation rejects every non-admitted repository, ref and event",()=>{
 const keys=["GITHUB_REPOSITORY","GITHUB_WORKFLOW_REF","GITHUB_EVENT_NAME","WORKFORCE_V4_SOURCE_SHA","GITHUB_RUN_ID"];
 const previous=Object.fromEntries(keys.map(k=>[k,process.env[k]]));
 try{
  process.env.GITHUB_REPOSITORY="XoticHaze/waterboys-fantasy-compute";
  process.env.GITHUB_WORKFLOW_REF="XoticHaze/waterboys-fantasy-compute/.github/workflows/nvidia-workforce-shadow-qualification.yml@refs/heads/main";
  process.env.GITHUB_EVENT_NAME="push";
  process.env.WORKFORCE_V4_SOURCE_SHA=SHA;
  process.env.GITHUB_RUN_ID="41460000000";
  assert.deepEqual(validateV4Host(),{sourceSha:SHA,runId:ID});
  process.env.GITHUB_EVENT_NAME="workflow_dispatch";
  assert.throws(()=>validateV4Host(),/v4_untrusted_execution_host/);
 }finally{for(const k of keys)previous[k]===undefined?delete process.env[k]:process.env[k]=previous[k];}
});
