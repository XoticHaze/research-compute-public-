import test from "node:test";
import assert from "node:assert/strict";
import {runDiscoveryCase} from "../src/role_discovery_runner.js";
import {MODELS} from "../src/code_role_suite.js";
import {TASKS} from "../src/role_discovery_high_signal.js";
const good={
 evidence_reconciliation:{status:"conflict_needs_review",trusted_hash:"aa11",deployment_allowed:false,contradiction:"mirror_hash_mismatch",next_step:"verify_owner_authority"},
 messy_extraction:{run_id:"BX-42",utc_time:"2026-11-01T23:25:00Z",succeeded:9,failed:3,total:12,unresolved_discrepancy:true,missing_timestamp:true},
 bounded_plan:{steps:["inspect_fixture","propose_patch","request_review"],blocked:["broker_trade"],requires_review:true},
 tradeoff_analysis:{candidate:"A",reason:"pass_rate",cost_known:false,production_approved:false},
 operator_explanation:{message:"In shadow run BX-42, 9/12 succeeded. Three cases require review and inspection. We do not have an established root cause. No production configuration changed."}
};
test("two fixed models across five real challenge types, without any executed tools",async()=>{
 for(let m=0;m<2;m++)for(let i=0;i<TASKS.length;i++){
  let requests=0;
  const r=await runDiscoveryCase({modelIndex:m,taskIndex:i,providerFetch:async (url,opts)=>{
   requests++;
   assert.equal(url,"https://integrate.api.nvidia.com/v1/chat/completions");
   assert.equal(opts.redirect,"manual");
   assert.equal(opts.method,"POST");
   const body=JSON.parse(opts.body);
   assert.equal(body.model,MODELS[m]);
   assert.equal(body.messages.length,2);
   assert.equal(body.temperature,1.0);
   assert.equal(body.top_p,0.95);
   assert.equal(body.max_tokens,8192);
   assert.equal(body.tools,undefined);
   return{status:200,async json(){return{
     choices:[{finish_reason:"stop",message:{content:JSON.stringify(good[TASKS[i].id]),reasoning_content:"PRIVATE_INTERNAL_REASONING"}}],
     usage:{prompt_tokens:150,completion_tokens:432,completion_tokens_details:{reasoning_tokens:230}},
     dangerous_raw_response:"DO_NOT_RETURN"
   };}};
  }});
  assert.equal(requests,1);
  assert.equal(r.provider_calls,1);
  assert.equal(r.finish_reason,"stop");
  assert.equal(r.completion_tokens,432);
  assert.equal(r.reasoning_tokens,230);
  assert.equal(r.http_status,200);
  assert.equal(r.raw_output_included,false);
  assert.equal(r.production_authorized,false);
  assert.equal(r.private_data_used,false);
  assert.equal(r.status,i===4?"human_review_required":"scored_pass");
  assert.equal(r.passed,i!==4);
  assert(!JSON.stringify(r).includes("PRIVATE_INTERNAL_REASONING"));
  assert(!JSON.stringify(r).includes("DO_NOT_RETURN"));
  assert(!JSON.stringify(r).includes("No production configuration changed"));
 }
});
test("provider 429 is bounded one call and never misreported as failed model ability",async()=>{
 let calls=0;
 const r=await runDiscoveryCase({modelIndex:1,taskIndex:2,providerFetch:async()=>{calls++;return{status:429};}});
 assert.equal(calls,1);
 assert.equal(r.provider_calls,1);
 assert.equal(r.status,"provider_rate_limited");
 assert.equal(r.passed,false);
 assert.equal(r.checks_total,0);
});
test("HTTP denials, response errors, and false facts keep distinct failure classifications",async()=>{
 const denied=await runDiscoveryCase({modelIndex:0,taskIndex:0,providerFetch:async()=>({status:403})});
 assert.equal(denied.status,"provider_unavailable");
 const malformed=await runDiscoveryCase({modelIndex:0,taskIndex:0,providerFetch:async()=>({status:200,json:async()=>{throw Error("SECRET_SHOULD_NOT_LEAK");}})});
 assert.equal(malformed.status,"provider_transport_or_decode_failure");
 assert(!JSON.stringify(malformed).includes("SECRET"));
 const wrong=await runDiscoveryCase({modelIndex:1,taskIndex:3,providerFetch:async()=>({status:200,json:async()=>({choices:[{finish_reason:"length",message:{content:'{"candidate":"B","reason":"latency","cost_known":true,"production_approved":true}'}}]})})});
 assert.equal(wrong.status,"scored_fail");
 assert.equal(wrong.format_valid,true);
 assert.equal(wrong.finish_reason,"length");
 assert.equal(wrong.passed,false);
});
test("caller cannot select arbitrary models or task IDs",async()=>{
 for(const args of [{modelIndex:2,taskIndex:0},{modelIndex:0,taskIndex:5},{modelIndex:"0",taskIndex:0},{modelIndex:0,taskIndex:0,providerFetch:null}]){
  await assert.rejects(()=>runDiscoveryCase({...args,providerFetch:args.providerFetch??null}),/invalid_fixed_discovery_selector/);
 }
});
