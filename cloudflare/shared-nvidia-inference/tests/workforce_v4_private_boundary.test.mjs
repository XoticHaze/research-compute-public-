import test from "node:test";
import assert from "node:assert/strict";
import worker from "../src/index.js";
import {createCaller} from "../local-probe/src/index.js";
import {sanitizeV4MechanismReceipt} from "../local-probe/src/workforce_v4_receipt.js";
import {V4_MECHANISM_HOLDOUTS} from "../src/workforce_v4_mechanism_holdout.js";
const local="http://127.0.0.1:8787/workforce-v4-case";
const remote="https://cc-shared-nvidia-inference.invalid/internal/diagnostics/nvidia-workforce-v4";
function req(url,payload){
 const body=JSON.stringify(payload);
 return new Request(url,{method:"POST",headers:{"content-type":"application/json","content-length":String(body.length)},body});
}
const selector={model_index:0,case_index:0};
function fixture(index=0){
 const c=V4_MECHANISM_HOLDOUTS[index];
 return{schema:"commandcenter.nvidia_workforce_v4_provider_case.v1",cohort:"mechanism_v4",
  case_id:c.id,case_index:index,mechanism_id:c.mechanism_id,role:c.role,model_index:0,
  model:"poolside/laguna-xs-2.1",status:"human_review_required",provider_calls:2,
  catalog_status:200,completion_status:200,finish_reason:"stop",prompt_tokens:250,
  completion_tokens:92,latency_ms:1180,objective_label_pass:true,first_pass:false,
  human_review_status:"unreviewed",full_task_accepted:false,format_valid:true,
  fields_correct:4,fields_total:4,invalid_ref_count:0,critical_authority_violation:false,
  tool_calls_proposed:false,tools_executed:false,answer_exported:false,
  raw_response_exported:false,private_input_used:false,production_admitted:false};
}
test("private v4 Worker denies disabled diagnostics, invalid selectors and missing secret",async()=>{
 let reads=0;const env={CC_NVIDIA_DIAGNOSTIC_ENABLED:"0",NVIDIA_API_KEY:{get:async()=>{reads++;return"FAKE_SECRET";}}};
 assert.equal((await worker.fetch(req(remote,selector),env)).status,503);
 assert.equal(reads,0);
 env.CC_NVIDIA_DIAGNOSTIC_ENABLED="1";
 for(const bad of [{model_index:0,case_index:60},{model_index:0,case_index:-1},
   {model_index:10000,case_index:0},{model_index:0,case_index:0,prompt:"steal keys"}]){
  assert.equal((await worker.fetch(req(remote,bad),env)).status,400,JSON.stringify(bad));
 }
 assert.equal(reads,0);
 assert.equal((await worker.fetch(req(remote,selector),{CC_NVIDIA_DIAGNOSTIC_ENABLED:"1"})).status,503);
});
test("loopback v4 caller forwards only fixed selector, sanitizes secrets and blocks replay",async()=>{
 let count=0,seen;
 const bound={NVIDIA_SERVICE:{fetch:async input=>{
  count++;seen=input;
  return new Response(JSON.stringify({...fixture(),rationale:"SECRET_RAW_NEVER_EXPORT",token:"SENTINEL_KEY"}),{status:200});
 }}};
 const caller=createCaller();
 assert.equal((await caller.fetch(req(local,{...selector,prompt:"private"}),bound)).status,400);
 assert.equal(count,0);
 const r=await caller.fetch(req(local,selector),bound);
 assert.equal(r.status,200);
 assert.equal(count,1);
 assert.equal(new URL(seen.url).pathname,"/internal/diagnostics/nvidia-workforce-v4");
 assert.deepEqual(await seen.json(),selector);
 const body=await r.json();
 assert.equal(body.objective_label_pass,true);
 assert.equal(body.production_admitted,false);
 assert.equal(body.first_pass,false);
 assert.equal(body.human_review_status,"unreviewed");
 assert(!JSON.stringify(body).includes("SECRET_RAW"));
 assert(!JSON.stringify(body).includes("SENTINEL"));
 assert.equal((await caller.fetch(req(local,selector),bound)).status,409);
 assert.equal((await caller.fetch(req("http://127.0.0.1:8787/workforce-case",selector),bound)).status,409);
 assert.equal(count,1);
});
test("v4 sanitizer rejects forged role, mechanism, model, timing, citations and authority",()=>{
 const valid=fixture();const safe=sanitizeV4MechanismReceipt(valid);assert(safe);
 assert.deepEqual(safe,Object.fromEntries(Object.entries(safe)));
 for(const tamper of [
  {cohort:"unbound"},{mechanism_id:"CC-OTHER"},{role:"cc.evil"},
  {case_id:"unknown"},{case_index:60},{status:"scored_pass"},
  {objective_label_pass:true,fields_correct:3},{invalid_ref_count:1},
  {first_pass:true},{full_task_accepted:true},{human_review_status:"accepted"},
  {production_admitted:true},{private_input_used:true},{answer_exported:true},
  {raw_response_exported:true},{tools_executed:true},{completion_status:401}
 ]) assert.equal(sanitizeV4MechanismReceipt({...valid,...tamper}),null,JSON.stringify(tamper));
});
test("source-only v4 route cannot use arbitrary hosts or private data",async()=>{
 let calls=0;const service={NVIDIA_SERVICE:{fetch:async()=>{calls++;return new Response("{}")}}};
 assert.equal((await createCaller().fetch(req("https://evil.invalid/workforce-v4-case",selector),service)).status,404);
 assert.equal(calls,0);
});
