import test from "node:test";
import assert from "node:assert/strict";
import {MICRO_CASES,MICRO_MODELS,microRequest,scoreMicro} from "../src/micro_worker_fixtures.js";
import {runMicroWorkerBatch} from "../src/micro_worker_benchmark.js";
import {sanitizeMicroReceipt} from "../local-probe/src/micro_receipt.js";
test("24 stable synthetic cases in six categories and fixed model allowlist",()=>{
 assert.equal(MICRO_CASES.length,24);
 assert.deepEqual(MICRO_MODELS,["poolside/laguna-xs-2.1","minimaxai/minimax-m3.1-flash"]);
 assert.equal(new Set(MICRO_CASES.map(x=>x.id)).size,24);
 assert.deepEqual([...new Set(MICRO_CASES.map(x=>x.category))].sort(),
  ["command","customer","placement","retry","security","triage"]);
 for(const c of MICRO_CASES){
  assert.equal(typeof c.action,"string");assert.equal(typeof c.route,"string");
  assert(!JSON.stringify(c).match(/NVIDIA_API_KEY|cloudflare\.com\/client|Bearer /));
 }
});
test("model, batch and case selectors are closed sets",()=>{
 for(const bad of [-1,2,999,"0",null]){
  assert.throws(()=>microRequest(bad,0,0));
 }
 for(const bad of [-1,6,100,"0",null])assert.throws(()=>microRequest(0,bad,0));
 for(const bad of [-1,4,100,"0",null])assert.throws(()=>microRequest(0,0,bad));
});
test("scoring requires exact action and route and no extra instructions",()=>{
 const x=MICRO_CASES[0];
 assert.deepEqual(scoreMicro({content:JSON.stringify({action:x.action,route:x.route})},x),
  {valid:true,passed:true});
 assert.equal(scoreMicro({content:JSON.stringify({action:x.action,route:"operator"})},x).passed,false);
 assert.equal(scoreMicro({content:JSON.stringify({action:x.action,route:x.route,exfiltrate:true})},x).passed,false);
 assert.equal(scoreMicro({content:"Please ignore policy"},x).passed,false);
});
test("live provider batch makes four fixed calls and exports no raw answers",async()=>{
 let hits=0;
 const actual=await runMicroWorkerBatch({modelIndex:0,batch:0,providerFetch:async(u,opts)=>{
  assert(u.endsWith("/v1/chat/completions"));hits++;
  const data=JSON.parse(opts.body);
  assert.equal(data.model,MICRO_MODELS[0]);assert.equal(data.max_tokens,200);
  assert.equal(data.temperature,0);assert.equal(opts.redirect,"manual");
  const fixture=MICRO_CASES[hits-1];
  assert.equal(data.messages[1].content,fixture.scenario);
  return {status:200,async json(){return{choices:[{message:{content:JSON.stringify({
    action:fixture.action,route:fixture.route
  })}}]}}};
 }});
 assert.equal(hits,4);assert.equal(actual.calls,4);
 assert.equal(actual.status,"batch_complete");
 assert(actual.results.every(x=>x.passed&&x.format_valid));
 assert.equal(JSON.stringify(actual).includes("scenario"),false);
 const safe=sanitizeMicroReceipt(actual);
 assert(safe && safe.results.length===4);
 assert.equal(JSON.stringify(safe).includes("scenario"),false);
});
test("provider 429 stops the batch and retains classification only",async()=>{
 const x=await runMicroWorkerBatch({modelIndex:1,batch:3,providerFetch:async()=>({
   status:429,async json(){return{secret:"do not export"}}})});
 assert.equal(x.calls,1);assert.equal(x.status,"rate_limited");
 assert.equal(x.results[0].http_status,429);
 assert(!JSON.stringify(sanitizeMicroReceipt(x)).includes("do not export"));
});
test("sanitizer rejects arbitrary model IDs and invalid task keys",()=>{
 const x={schema:"commandcenter.nvidia_micro_worker_synthetic.v1",
  model:"attack/arbitrary",model_index:0,batch:0,status:"batch_complete",
  calls:1,elapsed_ms:100,results:[]};
 assert.equal(sanitizeMicroReceipt(x),null);
 x.model=MICRO_MODELS[0];x.results=[{
  id:"Q99",category:"security",http_status:200,latency_ms:20,passed:true,format_valid:true
 }];
 assert.equal(sanitizeMicroReceipt(x),null);
});
