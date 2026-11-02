import test from "node:test";
import assert from "node:assert/strict";
import {newCampaign,runCampaign,resultsFromCampaign,validatePublicHost} from "../scripts/workforce_campaign_cli.mjs";
import {CASES} from "../src/workforce_domain_suite.js";
const SHA="ab".repeat(20),RUN="github-990000";
const models=["minimaxai/minimax-m3.1-flash","poolside/laguna-xs-2.1"];
const make=({model_index,case_index},status)=>{
 const c=CASES[case_index],human=c.human_review_required,
  absent=status==="model_index_not_in_authenticated_catalog",
  failed=status==="model_http_unavailable",rate=status==="provider_rate_limited";
 const state=status??(human?"human_review_required":"scored_pass");
 return{schema:"commandcenter.model_workforce_provider_case.v1",
  model_index,model:absent?null:models[model_index]??null,
  case_id:c.id,case_index,role:c.role,domain:c.domain,
  baseline:c.baseline,priority:c.priority,status:state,
  provider_calls:absent?1:2,catalog_status:200,
  completion_status:absent?null:failed?403:rate?429:200,
  catalog_count:65,eligible_model_count:2,
  finish_reason:absent||failed||rate?"not_recorded":"stop",
  prompt_tokens:absent||failed||rate?null:200,
  completion_tokens:absent||failed||rate?null:90,reasoning_tokens:null,
  first_pass:!human&&!absent&&!failed&&!rate,
  format_valid:!absent&&!failed&&!rate,
  fields_correct:absent||failed||rate?0:Object.keys(c.expected).length,
  fields_total:Object.keys(c.expected).length,
  human_review_required:human,latency_ms:1600,
  tool_calls_proposed:false,tools_executed:false,
  answer_exported:false,private_input_used:false,production_authorized:false};
};
test("fixed work is checkpointed every case and resumes on the exact next case",async()=>{
 const checkpoints=[];
 const first=await runCampaign({state:newCampaign({sourceSha:SHA,runId:RUN}),
   callCase:async selector=>make(selector),limit:3,
   onCheckpoint:async v=>checkpoints.push(v)});
 assert.equal(first.status,"session_call_limit_reached");
 assert.equal(first.observations.length,3);
 assert.equal(first.provider_http_calls,6);
 assert.equal(first.next_case_index,3);
 assert.equal(checkpoints.length,3);
 assert.deepEqual(checkpoints.map(x=>x.observations.length),[1,2,3]);
 const second=await runCampaign({state:first,callCase:async selector=>make(selector),limit:2});
 assert.equal(second.observations.length,5);
 assert.equal(second.next_case_index,5);
 assert.equal(second.model_id_by_index[0],models[0]);
});
test("multi-model full corpus is a capacity slice, not a lifetime two-model limit",async()=>{
 const all=await runCampaign({state:newCampaign({sourceSha:SHA,runId:RUN}),
   callCase:async selector=>make(selector),limit:64});
 assert.equal(all.observations.length,64);
 assert.equal(all.calls,64);
 assert.equal(all.provider_http_calls,128);
 assert.equal(all.next_model_index,2);
 assert.equal(all.next_case_index,0);
 const result=resultsFromCampaign(all);
 assert.equal(result.observed_cases,64);
 assert.equal(result.any_production_admission,false);
 assert(result.rows.some(x=>x.role==="mm.trader_ops_shadow"));
 assert(result.rows.every(x=>x.production_admitted===false));
});
test("HTTP 429 records a held attempt without consuming the unfinished case",async()=>{
 const first=await runCampaign({state:newCampaign({sourceSha:SHA,runId:RUN}),
  callCase:async selector=>make(selector,"provider_rate_limited"),limit:16});
 assert.equal(first.status,"provider_hold");
 assert.equal(first.attempt_history.length,1);
 assert.equal(first.observations.length,0);
 assert.equal(first.next_case_index,0);
 assert.equal(first.provider_http_calls,2);
 const resumed=await runCampaign({state:first,callCase:async selector=>make(selector),limit:2});
 assert.equal(resumed.attempt_history.length,1);
 assert.equal(resumed.observations.length,2);
 assert.equal(resumed.next_case_index,2);
 assert.equal(resumed.calls,3);
});
test("unsupported catalog index ends the campaign; rejected model stops wasting further tasks",async()=>{
 const first=await runCampaign({state:newCampaign({sourceSha:SHA,runId:RUN,modelIndex:2}),
  callCase:async selector=>make(selector,"model_index_not_in_authenticated_catalog"),limit:64});
 assert.equal(first.status,"catalog_complete");
 assert.equal(first.observations.length,1);
 assert.equal(first.observations[0].model,null);
 let extra=0;
 const second=await runCampaign({state:first,callCase:async()=>{extra++;throw Error("should not run");}});
 assert.equal(extra,0);
 assert.equal(second.status,"catalog_complete");
 const denied=await runCampaign({state:newCampaign({sourceSha:SHA,runId:RUN}),
  callCase:async selector=>make(selector,"model_http_unavailable"),limit:1});
 assert.equal(denied.observations.length,1);
 assert.equal(denied.next_model_index,1);
 assert.equal(denied.next_case_index,0);
});
test("catalog reordering cannot silently relabel a previous model's observations",async()=>{
 const state=await runCampaign({state:newCampaign({sourceSha:SHA,runId:RUN}),
  callCase:async selector=>make(selector),limit:1});
 await assert.rejects(()=>runCampaign({state,callCase:async selector=>({
  ...make(selector),model:"nvidia/surprise-model"
 })}),/catalog_index_mapping_changed/);
 await assert.rejects(()=>runCampaign({state:{...state,production_admitted:true},callCase:async()=>{}}),/invalid_campaign_checkpoint/);
 await assert.rejects(()=>runCampaign({state,callCase:async()=>({prompt:"PRIVATE_CONTENT"})}),/untrusted_workforce_case_result/);
});
test("invalid session budgets, run identity and forged states fail closed",async()=>{
 for(const x of [-1,0,65,2.2,"64"]){
  await assert.rejects(()=>runCampaign({state:newCampaign({sourceSha:SHA,runId:RUN}),
   callCase:async()=>{},limit:x}),/invalid_bounded_campaign/);
 }
 assert.throws(()=>newCampaign({sourceSha:"fake",runId:RUN}),/invalid_source_or_campaign_identity/);
 assert.throws(()=>newCampaign({sourceSha:SHA,runId:"no spaces allowed"}),/invalid_source_or_campaign_identity/);
 assert.throws(()=>newCampaign({sourceSha:SHA,runId:RUN,caseIndex:32}),/invalid_source_or_campaign_identity/);
});

test("source-pinned campaign is admitted only on exact public Cloudflare workflow",()=>{
 const names=["GITHUB_REPOSITORY","GITHUB_WORKFLOW_REF","GITHUB_EVENT_NAME",
   "WORKFORCE_SOURCE_SHA","GITHUB_RUN_ID"];
 const prior=Object.fromEntries(names.map(k=>[k,process.env[k]]));
 try{
  process.env.GITHUB_REPOSITORY="XoticHaze/waterboys-fantasy-compute";
  process.env.GITHUB_WORKFLOW_REF="XoticHaze/waterboys-fantasy-compute/.github/workflows/nvidia-workforce-shadow-qualification.yml@refs/heads/main";
  process.env.GITHUB_EVENT_NAME="push";
  process.env.WORKFORCE_SOURCE_SHA=SHA;
  process.env.GITHUB_RUN_ID="41397754463";
  assert.deepEqual(validatePublicHost(),{sourceSha:SHA,runId:"github-41397754463"});
  process.env.GITHUB_WORKFLOW_REF="XoticHaze/waterboys-fantasy-compute/.github/workflows/arbitrary.yml@refs/heads/main";
  assert.throws(()=>validatePublicHost(),/untrusted_execution_host/);
  process.env.GITHUB_WORKFLOW_REF="XoticHaze/waterboys-fantasy-compute/.github/workflows/nvidia-workforce-shadow-qualification.yml@refs/heads/main";
  process.env.GITHUB_REPOSITORY="XoticHaze/research-compute-public-";
  assert.throws(()=>validatePublicHost(),/untrusted_execution_host/);
  process.env.GITHUB_REPOSITORY="XoticHaze/waterboys-fantasy-compute";
  process.env.GITHUB_EVENT_NAME="pull_request";
  assert.throws(()=>validatePublicHost(),/untrusted_execution_host/);
 }finally{
  for(const k of names){
   if(prior[k]===undefined)delete process.env[k];
   else process.env[k]=prior[k];
  }
 }
});
