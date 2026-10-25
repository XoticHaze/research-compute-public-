import test from "node:test";
import assert from "node:assert/strict";
import {BATCH_SIZE,MAX_REQUESTS_PER_BATCH,runSyntheticRoleBatch,sanitizeModelCatalog} from "../src/benchmark_runner.js";

test("catalog is complete across known IDs, not a three-model shortlist",async()=>{
 const ids=["nvidia/nemotron-3-super-120b-a12b","openai/gpt-oss-20b",
            "nvidia/nv-embed-v1","meta/llama-3.3-70b-instruct"];
 const requests=[];
 const got=await runSyntheticRoleBatch({batch:-1,providerFetch:async(url,opts)=>{
   requests.push({url,opts});return{status:200,async json(){return{data:ids.map(id=>({id}))};}};
 }});
 assert.equal(got.status,"catalog_only");
 assert.equal(got.catalog_count,4);
 assert.deepEqual(got.catalog_model_ids,[...ids].sort());
 assert.equal(got.calls,1);
 assert.equal(got.results.length,0);
 assert.equal(requests[0].opts.redirect,"manual");
 assert.equal(got.secret_exposed,false);
});
test("two models get four real synthetic tasks with correct structured tool score",async()=>{
 let clock=100, calls=0;
 const providerFetch=async(url,opts)=>{
   calls++;clock+=75;
   if(url.endsWith("/models"))return{status:200,async json(){return{data:[
     {id:"openai/gpt-oss-20b"},{id:"meta/llama-3.3-70b-instruct"}
   ]}}};
   assert.equal(opts.redirect,"manual");
   const input=JSON.parse(opts.body);
   if(input.tools)return{status:200,async json(){return{choices:[{message:{
     content:null,tool_calls:[{type:"function",function:{
       name:"set_demo_light",arguments:'{"entity_id":"light.demo_desk","brightness_pct":35}'
     }}]
   }}]}}};
   let content="";
   const prompt=input.messages[0].content;
   if(prompt.includes("tulips"))content="NO";
   if(prompt.includes("17 multiplied"))content="323";
   if(prompt.includes("three keys"))content='{"event":"motion","count":2,"urgent":false}';
   return{status:200,async json(){return{choices:[{message:{content}}]}}};
 };
 const result=await runSyntheticRoleBatch({batch:0,providerFetch,now:()=>clock});
 assert.equal(result.status,"batch_complete");
 assert.equal(result.results.length,BATCH_SIZE);
 assert.equal(result.calls,MAX_REQUESTS_PER_BATCH);
 for(const model of result.results){
  assert.equal(model.results.length,4);
  assert(model.results.every(row=>row.passed && row.format_valid));
  assert(model.results.every(row=>row.latency_ms===75));
 }
 assert.equal(JSON.stringify(result).includes("light.demo_desk"),false);
 assert.equal(calls,MAX_REQUESTS_PER_BATCH);
});
test("rate limit is a stop not an evaluated task",async()=>{
 let attempts=0;
 const result=await runSyntheticRoleBatch({batch:0,providerFetch:async url=>{
   if(url.endsWith("/models"))return{status:200,async json(){return{data:[{id:"openai/gpt-oss-20b"}]}}};
   attempts++;return{status:429,async json(){return{message:"do not expose"};}};
 }});
 assert.equal(result.status,"rate_limited");
 assert.equal(result.calls,2);
 assert.equal(attempts,1);
 assert.equal(result.results[0].results[0].http_status,429);
 assert.equal(result.results[0].results[0].passed,false);
 assert.equal(JSON.stringify(result).includes("do not expose"),false);
});
test("unsupported batch and malformed catalog fail closed",async()=>{
 await assert.rejects(()=>runSyntheticRoleBatch({batch:100,providerFetch:async()=>{}}),/invalid_batch/);
 await assert.rejects(()=>runSyntheticRoleBatch({batch:"0",providerFetch:async()=>{}}),/invalid_batch/);
 assert.deepEqual(sanitizeModelCatalog([{id:"broken"},{id:"nvidia/test"},{id:"nvidia/test"}]),["nvidia/test"]);
});
