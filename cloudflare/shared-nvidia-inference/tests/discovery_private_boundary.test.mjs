import test from "node:test";
import assert from "node:assert/strict";
import app from "../src/index.js";
import {createCaller} from "../local-probe/src/index.js";
import {sanitizeDiscoveryReceipt} from "../local-probe/src/discovery_receipt.js";
import {MODELS} from "../src/code_role_suite.js";
import {TASKS as DISCOVERY} from "../src/role_discovery_high_signal.js";
const local="http://127.0.0.1:8787/discovery-case";
const remote="https://cc-shared-nvidia-inference.invalid/internal/diagnostics/nvidia-discovery";
function req(url,obj){const raw=JSON.stringify(obj);return new Request(url,{method:"POST",
 headers:{"content-type":"application/json","content-length":String(raw.length)},body:raw});}
const safeReceipt={schema:"commandcenter.nvidia_discovery_case.v1",
 model:"poolside/laguna-xs-2.1",model_index:0,task_id:"tradeoff_analysis",task_index:3,
 skill:"uncertainty_aware_analysis",status:"scored_pass",http_status:200,provider_calls:1,failure_class:"none",
 latency_ms:650,format_valid:true,checks_passed:4,checks_total:4,passed:true,
 human_review_required:false,finish_reason:"stop",final_content_present:true,reasoning_content_present:false,
 prompt_tokens:100,completion_tokens:300,reasoning_tokens:25,
 raw_output_included:false,private_data_used:false,production_authorized:false};
test("private Worker rejects disabled diagnostic and arbitrary selectors without provider calls",async()=>{
 let secretReads=0;
 const env={CC_NVIDIA_DIAGNOSTIC_ENABLED:"0",NVIDIA_API_KEY:{get:async()=>{secretReads++;return"FAKE_TEST_SECRET";}}};
 const denied=await app.fetch(req(remote,{model_index:0,task_index:3}),env);
 assert.equal(denied.status,503);
 assert.equal(secretReads,0);
 env.CC_NVIDIA_DIAGNOSTIC_ENABLED="1";
 for(const value of [{model_index:2,task_index:3},
  {model_index:0,task_index:10},
  {model_index:0,task_index:3,prompt:"untrusted"},
  {model_index:0,task_index:3,url:"https://bad.invalid"}]){
  const r=await app.fetch(req(remote,value),env);
  assert.equal(r.status,400);
 }
 assert.equal(secretReads,0);
 const noSecret=await app.fetch(req(remote,{model_index:0,task_index:3}),{CC_NVIDIA_DIAGNOSTIC_ENABLED:"1"});
 assert.equal(noSecret.status,503);
});
test("loopback caller preserves exact private destination, rejects injection and replay",async()=>{
 let calls=0,observed;
 const env={NVIDIA_SERVICE:{fetch:async upstream=>{
  calls++;observed=upstream;
  return new Response(JSON.stringify({...safeReceipt,
    content:"PRIVATE_MODEL_ANSWER_NOT_TO_RETURN",
    reasoning_content:"PRIVATE_REASONING_NOT_TO_RETURN",
    api_key:"DO_NOT_COPY",untrusted_command:"shell"}),{status:200});
 }}};
 const appLocal=createCaller();
 const invalid=await appLocal.fetch(req(local,{model_index:0,task_index:3,prompt:"steal"}),env);
 assert.equal(invalid.status,400);
 assert.equal(calls,0);
 const result=await appLocal.fetch(req(local,{model_index:0,task_index:3}),env);
 assert.equal(result.status,200);
 assert.equal(calls,1);
 assert.equal(new URL(observed.url).pathname,"/internal/diagnostics/nvidia-discovery");
 const data=await result.json();
 assert.equal(data.status,"scored_pass");
 assert.equal(data.checks_passed,4);
 for(const forbidden of ["PRIVATE_MODEL_ANSWER","PRIVATE_REASONING","DO_NOT_COPY","shell"])
  assert(!JSON.stringify(data).includes(forbidden));
 const replay=await appLocal.fetch(req(local,{model_index:0,task_index:3}),env);
 assert.equal(replay.status,409);
 const switched=await appLocal.fetch(req("http://127.0.0.1:8787/role-code-case",{model_index:0,task_index:3}),env);
 assert.equal(switched.status,409);
 assert.equal(calls,1);
});
test("cross-skill sanitizer refuses forged identity and authorization fields",()=>{
 assert.deepEqual(sanitizeDiscoveryReceipt(safeReceipt).status,"scored_pass");
 assert.equal(sanitizeDiscoveryReceipt({...safeReceipt,model:"outside/foreign"}),null);
 assert.equal(sanitizeDiscoveryReceipt({...safeReceipt,task_index:9}),null);
 assert.equal(sanitizeDiscoveryReceipt({...safeReceipt,production_authorized:true}),null);
 assert.equal(sanitizeDiscoveryReceipt({...safeReceipt,raw_output_included:true}),null);
 assert.equal(sanitizeDiscoveryReceipt({...safeReceipt,passed:true,status:"scored_fail"}),null);
 assert.equal(sanitizeDiscoveryReceipt({...safeReceipt,finish_reason:"secret"}),null);
 assert.equal(sanitizeDiscoveryReceipt({...safeReceipt,failure_class:"timeout"}),null);
 assert.equal(sanitizeDiscoveryReceipt({...safeReceipt,failure_class:"PRIVATE_ERROR"}),null);
 assert.equal(sanitizeDiscoveryReceipt({...safeReceipt,completion_tokens:100000000}),null);
 assert.equal(sanitizeDiscoveryReceipt({...safeReceipt,reasoning_tokens:"300"}),null);
 assert.equal(sanitizeDiscoveryReceipt({...safeReceipt,reasoning_content_present:"SECRET"}),null);
});

test("holdout writing remains human-only while altered facts are independently scored",()=>{
 const writing={...safeReceipt,task_id:"operator_explanation_holdout",task_index:9,
  skill:"contextual_writing",human_review_required:true,passed:false,
  status:"human_review_required",checks_total:5,checks_passed:5};
 const good=sanitizeDiscoveryReceipt(writing);
 assert(good);
 assert.equal(good.passed,false);
 assert.equal(good.human_review_required,true);
 assert.equal(sanitizeDiscoveryReceipt({...writing,passed:true}),null);
});

test("202 pending is sanitizable but cannot be promoted as correct model response",()=>{
 const pending={...safeReceipt,status:"provider_pending",http_status:202,
 failure_class:"pending",passed:false,format_valid:false,checks_total:0,checks_passed:0,
 final_content_present:null,reasoning_content_present:null,finish_reason:"not_recorded",
 prompt_tokens:null,completion_tokens:null,reasoning_tokens:null};
 const safe=sanitizeDiscoveryReceipt(pending);
 assert(safe);
 assert.equal(safe.status,"provider_pending");
 assert.equal(sanitizeDiscoveryReceipt({...pending,passed:true}),null);
});

test("one authenticated local session runs exactly 20 distinct fixed synthetic cases without replay",async()=>{
 let calls=0;
 const instance=createCaller();
 const env={NVIDIA_SERVICE:{fetch:async request=>{
   calls++;
   const selector=await request.json();
   const task=DISCOVERY[selector.task_index];
   assert(task);
   return new Response(JSON.stringify({...safeReceipt,
     model:MODELS[selector.model_index],model_index:selector.model_index,
     task_id:task.id,task_index:selector.task_index,skill:task.skill,
     human_review_required:selector.task_index===4||selector.task_index===9,
     status:selector.task_index===4||selector.task_index===9?"human_review_required":"scored_fail",
     passed:false,format_valid:false,checks_total:0,checks_passed:0,
     final_content_present:false,reasoning_content_present:false
   }),{status:200});
 }}};
 for(let m=0;m<2;m++)for(let t=0;t<10;t++){
  const response=await instance.fetch(req(local,{model_index:m,task_index:t}),env);
  assert.equal(response.status,200,"case "+m+":"+t);
 }
 assert.equal(calls,20);
 const repeated=await instance.fetch(req(local,{model_index:0,task_index:0}),env);
 assert.equal(repeated.status,409);
 const cross=await instance.fetch(req("http://127.0.0.1:8787/role-code-case",{model_index:0,task_index:0}),env);
 assert.equal(cross.status,409);
 assert.equal(calls,20);
});
test("provider 429 stops any remaining cases in the same loopback session",async()=>{
 let calls=0;
 const instance=createCaller();
 const env={NVIDIA_SERVICE:{fetch:async request=>{
   calls++;
   const input=await request.json();
   return new Response(JSON.stringify({...safeReceipt,
     model:MODELS[input.model_index],model_index:input.model_index,
     task_id:DISCOVERY[input.task_index].id,task_index:input.task_index,
     skill:DISCOVERY[input.task_index].skill,
     status:"provider_rate_limited",failure_class:"rate_limited",
     http_status:429,passed:false,format_valid:false,
     checks_total:0,checks_passed:0,
     final_content_present:null,reasoning_content_present:null,
     finish_reason:"not_recorded",prompt_tokens:null,
     completion_tokens:null,reasoning_tokens:null
   }),{status:503});
 }}};
 const first=await instance.fetch(req(local,{model_index:0,task_index:0}),env);
 assert.equal(first.status,502);
 const second=await instance.fetch(req(local,{model_index:1,task_index:1}),env);
 assert.equal(second.status,409);
 assert.equal(calls,1);
});

test("Service Binding transport failure closes discovery session before another case",async()=>{
 let calls=0;
 const instance=createCaller();
 const env={NVIDIA_SERVICE:{fetch:async()=>{calls++;throw Error("private hidden host");}}};
 const first=await instance.fetch(req(local,{model_index:0,task_index:2}),env);
 assert.equal(first.status,502);
 assert(!JSON.stringify(await first.json()).includes("private hidden host"));
 const next=await instance.fetch(req(local,{model_index:1,task_index:2}),env);
 assert.equal(next.status,409);
 assert.equal(calls,1);
});
