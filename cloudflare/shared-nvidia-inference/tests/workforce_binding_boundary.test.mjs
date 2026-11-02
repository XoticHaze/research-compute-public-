import test from "node:test";
import assert from "node:assert/strict";
import worker from "../src/index.js";
import {createCaller} from "../local-probe/src/index.js";
import {sanitizeWorkforceReceipt} from "../local-probe/src/workforce_receipt.js";
import {CASES} from "../src/workforce_domain_suite.js";
const local="http://127.0.0.1:8787/workforce-case";
const remote="https://cc-shared-nvidia-inference.invalid/internal/diagnostics/nvidia-workforce";
const selector={model_index:0,case_index:2};
function req(url,doc){const raw=JSON.stringify(doc);return new Request(url,{method:"POST",
 headers:{"content-type":"application/json","content-length":String(raw.length)},body:raw});}
function fixture(index=2){
 const c=CASES[index];
 return{schema:"commandcenter.model_workforce_provider_case.v1",
  model:"minimaxai/minimax-m3.1-flash",model_index:0,
  case_id:c.id,case_index:index,role:c.role,domain:c.domain,
  baseline:c.baseline,priority:c.priority,status:c.human_review_required?
    "human_review_required":"scored_pass",
  provider_calls:2,catalog_status:200,completion_status:200,
  catalog_count:61,eligible_model_count:55,
  finish_reason:"stop",prompt_tokens:400,completion_tokens:600,
  reasoning_tokens:200,first_pass:!c.human_review_required,
  format_valid:true,fields_correct:Object.keys(c.expected).length,
  fields_total:Object.keys(c.expected).length,
  field_checks:Object.fromEntries(Object.keys(c.expected).map(k=>[k,true])),
  human_review_required:c.human_review_required,
  latency_ms:2100,tool_calls_proposed:false,tools_executed:false,
  answer_exported:false,private_input_used:false,production_authorized:false};
}
test("diagnostic gate rejects requests before credentials or provider reads",async()=>{
 let keyReads=0;
 const env={CC_NVIDIA_DIAGNOSTIC_ENABLED:"0",NVIDIA_API_KEY:{get:async()=>{keyReads++;return"FAKE_SECRET";}}};
 const disabled=await worker.fetch(req(remote,selector),env);
 assert.equal(disabled.status,503);
 assert.equal(keyReads,0);
 env.CC_NVIDIA_DIAGNOSTIC_ENABLED="1";
 for(const bad of [{model_index:0,case_index:92},{model_index:0,case_index:-1},
  {model_index:10000,case_index:0},{model_index:0,case_index:0,prompt:"private"},
  {model_index:"0",case_index:0} ]){
  const r=await worker.fetch(req(remote,bad),env);
  assert.equal(r.status,400,JSON.stringify(bad));
 }
 assert.equal(keyReads,0);
 const noSecret=await worker.fetch(req(remote,selector),{CC_NVIDIA_DIAGNOSTIC_ENABLED:"1"});
 assert.equal(noSecret.status,503);
});
test("local caller forwards only exact indexed selector through private Service Binding",async()=>{
 let calls=0,used;
 const bound={NVIDIA_SERVICE:{fetch:async request=>{
  calls++;used=request;
  return new Response(JSON.stringify({...fixture(),
   content:"MODEL_PRIVATE_PROSE_DO_NOT_EXPORT",
   reasoning_content:"REASONING_DO_NOT_EXPORT",
   authorization:"SECRET_DO_NOT_EXPORT",shell:"IGNORE_ALL_RULES"}),{status:200});
 }}};
 const caller=createCaller();
 const rejected=await caller.fetch(req(local,{...selector,shell:"whoami"}),bound);
 assert.equal(rejected.status,400);
 assert.equal(calls,0);
 const result=await caller.fetch(req(local,selector),bound);
 assert.equal(result.status,200);
 assert.equal(calls,1);
 assert.equal(new URL(used.url).pathname,"/internal/diagnostics/nvidia-workforce");
 assert.deepEqual(await used.json(),selector);
 const doc=await result.json();
 assert.equal(doc.status,"scored_pass");
 assert.equal(doc.fields_correct,doc.fields_total);
 assert.equal(doc.tools_executed,false);
 for(const secret of ["MODEL_PRIVATE_PROSE","REASONING_DO_NOT_EXPORT","SECRET_DO_NOT_EXPORT","IGNORE_ALL_RULES"])
  assert(!JSON.stringify(doc).includes(secret));
 const replay=await caller.fetch(req(local,selector),bound);
 assert.equal(replay.status,409);
 const different=await caller.fetch(req("http://127.0.0.1:8787/discovery-case",{model_index:0,task_index:0}),bound);
 assert.equal(different.status,409);
 assert.equal(calls,1);
});
test("sanitizer rejects forged completion, extra identity, protected actions and invalid cost",()=>{
 const good=sanitizeWorkforceReceipt(fixture());
 assert(good);
 assert.equal(good.model,"minimaxai/minimax-m3.1-flash");
 assert.equal(good.answer_exported,false);
 for(const bad of [
  {case_id:"different"},{role:"other"},{model:"../../../fake"},
  {fields_correct:100},{fields_total:0,fields_correct:0},
  {field_checks:null},{provider_calls:12},{first_pass:true,status:"scored_fail"},
  {answer_exported:true},{private_input_used:true},{tools_executed:true},
  {production_authorized:true},{finish_reason:"SECRET_OUTPUT"},
  {prompt_tokens:-1},{completion_tokens:"300"},
  {completion_status:403,status:"scored_pass"}
 ])assert.equal(sanitizeWorkforceReceipt({...fixture(),...bad}),null,JSON.stringify(bad));
 const review=sanitizeWorkforceReceipt(fixture(30));
 assert(review);
 assert.equal(review.first_pass,false);
 assert.equal(review.human_review_required,true);
 assert.equal(review.status,"human_review_required");
});
test("old code role is still fixed at five functions, broad trial cannot expand its authority",async()=>{
 let calls=0;
 const bound={NVIDIA_SERVICE:{fetch:async()=>{calls++;throw Error("not reachable");}}};
 const response=await createCaller().fetch(req("http://127.0.0.1:8787/role-code-case",
  {model_index:0,task_index:7}),bound);
 assert.equal(response.status,400);
 assert.equal(calls,0);
});

test("bounded sessions cover all fixed cases without lifting the 64-request per-session gate",async()=>{
 let seen=0;
 const service={NVIDIA_SERVICE:{fetch:async request=>{
  seen++;
  const {model_index,case_index}=await request.json();
  return new Response(JSON.stringify({...fixture(case_index),model_index}),{status:200});
 }}};
 for(const start of [0,32,64]){
  const caller=createCaller();
  for(let i=start;i<Math.min(start+32,CASES.length);i++)for(let model_index=0;model_index<2;model_index++){
   const got=await caller.fetch(req(local,{model_index,case_index:i}),service);
   assert.equal(got.status,200,"case "+i+" model "+model_index);
  }
  const duplicate=await caller.fetch(req(local,{model_index:0,case_index:start}),service);
  assert.equal(duplicate.status,409);
  if(start<64){
   const overflow=await caller.fetch(req(local,{model_index:2,case_index:0}),service);
   assert.equal(overflow.status,409);
  }
 }
 assert.equal(seen,CASES.length*2);
});
test("provider hold stops further requests without treating it as model inability",async()=>{
 let calls=0;
 const service={NVIDIA_SERVICE:{fetch:async()=>{
  calls++;
  return new Response(JSON.stringify({...fixture(),status:"provider_rate_limited",
    completion_status:429,first_pass:false,format_valid:false,fields_correct:0,
    field_checks:Object.fromEntries(Object.keys(CASES[2].expected).map(k=>[k,false]))}),{status:503});
 }}};
 const caller=createCaller();
 const first=await caller.fetch(req(local,selector),service);
 assert.equal(first.status,502);
 assert.equal((await first.json()).status,"provider_rate_limited");
 const second=await caller.fetch(req(local,{model_index:0,case_index:3}),service);
 assert.equal(second.status,409);
 assert.equal(calls,1);
});

test("only independent source-keyed field checks cross the private boundary",()=>{
 const src=fixture(2);
 const keys=Object.keys(CASES[2].expected);
 const checks=Object.fromEntries(keys.map(k=>[k,true]));
 const accepted=sanitizeWorkforceReceipt({...src,field_checks:checks});
 assert(accepted);
 assert.deepEqual(accepted.field_checks,checks);
 assert.equal(accepted.answer_exported,false);
 assert.equal(sanitizeWorkforceReceipt({...src,field_checks:{...checks,private_text:true}}),null);
 assert.equal(sanitizeWorkforceReceipt({...src,field_checks:{...checks,[keys[0]]:"PRIVATE_ANSWER"}}),null);
 assert.equal(sanitizeWorkforceReceipt({...src,field_checks:{...checks,[keys[0]]:false}}),null);
});
