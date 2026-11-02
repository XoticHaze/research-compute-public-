import test from "node:test";
import assert from "node:assert/strict";
import {CASES} from "../src/workforce_domain_suite.js";
import {eligibleWorkforceCatalog,runWorkforceCase,discoveryProfile} from "../src/workforce_provider_runner.js";
const allModels=["nvidia/nv-embed-v1","minimaxai/minimax-m3.1-flash",
 "poolside/laguna-xs-2.1","openai/gpt-oss-20b"];
const candidates=["minimaxai/minimax-m3.1-flash","openai/gpt-oss-20b","poolside/laguna-xs-2.1"];
test("authenticated full catalog is deduplicated and includes more than old two-model limit",()=>{
 assert.deepEqual(eligibleWorkforceCatalog({data:allModels.map(id=>({id}))}),candidates);
 assert.deepEqual(eligibleWorkforceCatalog({data:allModels.map(id=>({id})).concat([{id:allModels[2]}])}),candidates);
 assert.deepEqual(eligibleWorkforceCatalog({data:["missing"]}),[]);
 for(const rows of [null,{},new Array(10001).fill({id:"nvidia/x"})])
   assert.throws(()=>eligibleWorkforceCatalog({data:rows}),/invalid_catalog/);
});
test("all 32 source-grounded challenges can be scored for any catalog-admitted candidate, no answer exported",async()=>{
 for(let i=0;i<CASES.length;i++){
  let calls=[];
  const modelIndex=i%3;
  const got=await runWorkforceCase({modelIndex,caseIndex:i,providerFetch:async (url,request)=>{
   calls.push({url,request});
   if(url.endsWith("/models"))return{status:200,async json(){return{data:allModels.map(id=>({id}))};}};
   const body=JSON.parse(request.body);
   assert.equal(body.model,candidates[modelIndex]);
   assert.equal(body.messages[0].role,"system");
   assert.equal(body.messages[1].role,"user");
   assert(body.messages[1].content.includes(CASES[i].question));
   assert.equal(body.max_tokens,body.model==="minimaxai/minimax-m3.1-flash"?16384:8192);
   assert.equal(body.temperature,1.0);
   assert.equal(body.tools,undefined);
   return{status:200,async json(){return{
    choices:[{finish_reason:"stop",message:{content:JSON.stringify(CASES[i].expected),reasoning_content:"PRIVATE_THOUGHT_NOT_EXPORTED"}}],
    usage:{prompt_tokens:320,completion_tokens:88,completion_tokens_details:{reasoning_tokens:15}},
    dangerous:"SECRET_NEVER_RETURNED"
   };}};
  }});
  assert.equal(calls.length,2);
  assert.equal(calls[0].url,"https://integrate.api.nvidia.com/v1/models");
  assert.equal(calls[1].url,"https://integrate.api.nvidia.com/v1/chat/completions");
  assert.equal(got.provider_calls,2);
  assert.equal(got.model,candidates[modelIndex]);
  assert.equal(got.eligible_model_count,3);
  assert.equal(got.prompt_tokens,320);
  assert.equal(got.reasoning_tokens,15);
  assert.equal(got.status,CASES[i].human_review_required?"human_review_required":"scored_pass");
  assert.equal(got.first_pass,!CASES[i].human_review_required);
  assert.equal(got.tools_executed,false);
  assert.equal(got.tool_calls_proposed,false);
  assert.equal(got.production_authorized,false);
  assert(!JSON.stringify(got).includes("PRIVATE_THOUGHT"));
  assert(!JSON.stringify(got).includes("SECRET"));
  assert(!JSON.stringify(got).includes(CASES[i].input));
 }
});
test("provider 429, missing model and untrusted model tool requests are separately classified",async()=>{
 const catalog=async()=>({status:200,json:async()=>({data:allModels.map(id=>({id}))})});
 let requests=0;
 const limited=await runWorkforceCase({modelIndex:0,caseIndex:0,
  providerFetch:async(url)=>{requests++;return url.endsWith("/models")?await catalog():{status:429};}});
 assert.equal(limited.status,"provider_rate_limited");
 assert.equal(limited.first_pass,false);
 assert.equal(requests,2);
 const absent=await runWorkforceCase({modelIndex:999,caseIndex:0,providerFetch:catalog});
 assert.equal(absent.provider_calls,1);
 assert.equal(absent.status,"model_index_not_in_authenticated_catalog");
 const tool=await runWorkforceCase({modelIndex:0,caseIndex:2,providerFetch:async(url)=>{
  if(url.endsWith("/models"))return await catalog();
  return{status:200,json:async()=>({choices:[{finish_reason:"tool_calls",message:{
   content:JSON.stringify(CASES[2].expected),tool_calls:[{name:"send_trade",arguments:"DO_NOT_EXPORT"}]
  }}]})};
 }});
 assert.equal(tool.status,"tool_attempt_rejected");
 assert.equal(tool.first_pass,false);
 assert.equal(tool.tool_calls_proposed,true);
 assert.equal(tool.tools_executed,false);
 assert(!JSON.stringify(tool).includes("send_trade"));
});
test("invalid selectors and provider responses never become model errors or leakage",async()=>{
 for(const value of [undefined,-1,10000,"0",1.5]){
  await assert.rejects(()=>runWorkforceCase({modelIndex:value,caseIndex:0,providerFetch:async()=>{}}),/invalid_fixed_workforce_selector/);
 }
 for(const value of [undefined,-1,32,"0",0.3]){
  await assert.rejects(()=>runWorkforceCase({modelIndex:0,caseIndex:value,providerFetch:async()=>{}}),/invalid_fixed_workforce_selector/);
 }
 const err=await runWorkforceCase({modelIndex:0,caseIndex:0,providerFetch:async()=>{throw Error("PRIVATE_CREDENTIAL_NOT_TO_COPY");}});
 assert.equal(err.status,"transport_or_decoding_failure");
 assert(!JSON.stringify(err).includes("PRIVATE_CREDENTIAL"));
 const badCatalog=await runWorkforceCase({modelIndex:0,caseIndex:0,providerFetch:async()=>({status:403})});
 assert.equal(badCatalog.status,"catalog_unavailable");
 assert.equal(badCatalog.completion_status,null);
});

test("NVIDIA-listed output defaults are per-model first-wave profiles, not user overrides",()=>{
 assert.deepEqual(discoveryProfile("minimaxai/minimax-m3.1-flash"),
  {temperature:1.0,top_p:0.95,max_tokens:16384});
 assert.deepEqual(discoveryProfile("poolside/laguna-xs-2.1"),
  {temperature:1.0,top_p:0.95,max_tokens:8192});
 assert.equal(discoveryProfile("openai/gpt-oss-20b").max_tokens,8192);
});
test("HTTP 400 profile rejections and upstream 503 are not model accuracy failures",async()=>{
 const catalog=async()=>({status:200,json:async()=>({data:allModels.map(id=>({id}))})});
 for(const [code,status] of [[400,"request_profile_rejected"],[503,"provider_upstream_error"]]){
  const r=await runWorkforceCase({modelIndex:0,caseIndex:0,providerFetch:async url=>
   url.endsWith("/models")?await catalog():{status:code}});
  assert.equal(r.status,status);
  assert.equal(r.first_pass,false);
  assert.equal(r.fields_correct,0);
 }
});
