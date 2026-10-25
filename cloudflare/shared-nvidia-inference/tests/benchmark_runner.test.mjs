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

test("model-specific 404 is recorded once and does not waste other synthetic tasks",async()=>{
 const requests=[];
 const result=await runSyntheticRoleBatch({batch:0,providerFetch:async(url,opts)=>{
  if(url.endsWith("/models"))return{status:200,async json(){return{data:[
   {id:"openai/gpt-oss-20b"},{id:"nvidia/nemotron-3.5-lightning-30b-a3b"}
  ]}}};
  const name=JSON.parse(opts.body).model;requests.push(name);
  if(name==="openai/gpt-oss-20b")return{status:404};
  return{status:200,async json(){return{choices:[{message:{content:"NO"}}]}}};
 }});
 assert.equal(result.status,"batch_complete");
 assert.equal(result.results.length,2);
 assert.equal(result.results.find(x=>x.model==="openai/gpt-oss-20b").results.length,1);
 assert.equal(requests.filter(x=>x==="openai/gpt-oss-20b").length,1);
 assert.equal(result.calls,6);
});

test("aborted provider request is retained and next model still receives a task",async()=>{
 const byModel=[];
 const result=await runSyntheticRoleBatch({batch:0,providerFetch:async(url,opts)=>{
  if(url.endsWith("/models"))return{status:200,async json(){return{data:[
   {id:"openai/gpt-oss-20b"},{id:"nvidia/nemotron-3.5-lightning-30b-a3b"}
  ]}}};
  const id=JSON.parse(opts.body).model;byModel.push(id);
  if(id==="openai/gpt-oss-20b")throw new DOMException("synthetic","AbortError");
  return{status:200,async json(){return{choices:[{message:{content:"NO"}}]}}};
 }});
 assert.equal(result.status,"batch_complete");
 assert.equal(result.results[0].results.length,1);
 assert.equal(result.results[0].results[0].error,"aborted");
 assert.equal(result.results[1].results.length,4);
 assert.equal(result.calls,6);
});

test("fixed vision batch sends generated red-left blue-right PNG, never household footage",async()=>{
 const models=["meta/llama-3.2-11b-vision-instruct","nvidia/nemotron-3.5-super-vl-120b-a12b"];
 let calls=0;
 const receipt=await runSyntheticRoleBatch({batch:-2,providerFetch:async(url,opts)=>{
  calls++;
  if(url.endsWith("/models")){
    return {status:200,async json(){return{data:models.map(id=>({id}))};}};
  }
  assert.equal(opts.redirect,"manual");
  const req=JSON.parse(opts.body);
  assert(models.includes(req.model));
  assert.equal(req.messages[0].content[1].type,"image_url");
  assert(req.messages[0].content[1].image_url.url.startsWith("data:image/png;base64,"));
  assert.equal(req.messages[0].content[0].type,"text");
  return {status:200,async json(){return{choices:[{message:{
    content:'{"left":"red","right":"blue"}'
  }}]}}};
 }});
 assert.equal(receipt.status,"batch_complete");
 assert.equal(receipt.calls,3);
 assert.equal(calls,3);
 assert.equal(receipt.results.length,2);
 assert(receipt.results.every(x=>x.results.length===1&&x.results[0].task==="vision"&&x.results[0].passed));
 assert.equal(JSON.stringify(receipt).includes("data:image"),false);
});
