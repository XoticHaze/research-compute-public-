import test from "node:test";
import assert from "node:assert/strict";
import {MODEL,HEADER,safeSource,quoteOracle,admitStep,requestFor,runQuoteStep} from "../src/quote_artifact_loop.js";
import {createQuoteArtifactCaller} from "../local-probe/src/quote_artifact_caller.js";
const SOURCE=HEADER+
"    if minutes < 0 or hourly_cents < 0 or travel_cents < 0 or supplies_cents < 0 or overhead_bps < 0 or margin_bps < 0:\n"+
"        return None\n"+
"    return minutes + hourly_cents + travel_cents + supplies_cents + overhead_bps + margin_bps\n";
function provider(source=SOURCE){return async(url,options)=>{
 assert.equal(url,"https://integrate.api.nvidia.com/v1/chat/completions");
 assert.equal(options.redirect,"manual");
 const q=JSON.parse(options.body);
 assert.equal(q.model,MODEL);
 assert.equal(q.messages.length,2);
 return {status:200,json:async()=>({choices:[{message:{content:JSON.stringify({source})}}]})};
};}
test("business oracle distinguishes true margin from markup and does ceiling rounding",()=>{
 assert.equal(quoteOracle([90,3500,500,250,1000,2500]),8800);
 assert.equal(quoteOracle([1,100,0,0,0,0]),2);
 assert.equal(quoteOracle([0,0,0,0,0,1000]),null);
 assert.equal(quoteOracle([5,1000,0,0,0,10000]),null);
 assert.equal(quoteOracle([-1,1000,0,0,0,0]),null);
});
test("only fixed draft or bounded verified feedback admitted",()=>{
 assert.deepEqual(admitStep({stage:0}),{stage:0,source:null,failedExamples:[]});
 assert.equal(admitStep({stage:0,prompt:"secret"}),null);
 const f={stage:1,source:SOURCE,failed_examples:[{input:[90,3500,500,250,1000,2500],expected:8800}]};
 assert.deepEqual(admitStep(f).failedExamples,[{input:f.failed_examples[0].input,expected:8800}]);
 assert.equal(admitStep({...f,failed_examples:[{input:f.failed_examples[0].input,expected:8801}]}),null);
 assert.equal(admitStep({...f,model:"other"}),null);
 assert.equal(admitStep({...f,source:SOURCE+"import os"}),null);
});
test("model artifact is source-only and bounded, no code execution",async()=>{
 const r=await runQuoteStep({input:{stage:0},providerFetch:provider()});
 assert.equal(r.status,"candidate_unexecuted");assert.equal(r.source,SOURCE);
 assert.equal(r.provider_calls,1);assert.equal(r.model_code_executed,false);
 assert(!JSON.stringify(r).includes("NVIDIA_API_KEY"));
});
test("second provider request carries independent failing example, not arbitrary new task",async()=>{
 const input={stage:1,source:SOURCE,failed_examples:[{input:[90,3500,500,250,1000,2500],expected:8800}]};
 const r=await runQuoteStep({input,providerFetch:async(url,opts)=>{
   const req=JSON.parse(opts.body);
   assert(req.messages[1].content.includes("expected=8800"));
   assert(req.messages[1].content.includes(SOURCE));
   return provider()(url,opts);
 }});
 assert.equal(r.status,"candidate_unexecuted");
});
test("429 halts without fabricating a candidate",async()=>{
 const r=await runQuoteStep({input:{stage:0},providerFetch:async()=>({status:429})});
 assert.equal(r.status,"rate_limited");assert.equal(r.source,null);
});
test("caller binds revision to exact initial source and rejects replay",async()=>{
 const caller=createQuoteArtifactCaller();
 const mk=v=>{const body=JSON.stringify(v);return new Request("http://127.0.0.1:8787/quote-artifact-step",
 {method:"POST",headers:{"Content-Type":"application/json","Content-Length":String(Buffer.byteLength(body))},body});};
 let count=0;const env={NVIDIA_SERVICE:{fetch:async(req)=>{
  count++;const body=await req.json();
  const r=await runQuoteStep({input:body,providerFetch:provider()});
  return new Response(JSON.stringify(r),{status:200});
 }}};
 assert.equal((await caller.fetch(mk({stage:1,source:SOURCE,failed_examples:[{input:[90,3500,500,250,1000,2500],expected:8800}]}),env)).status,409);
 const first=await caller.fetch(mk({stage:0}),env);
 assert.equal(first.status,200);assert.equal((await first.json()).source,SOURCE);
 assert.equal((await caller.fetch(mk({stage:0}),env)).status,409);
 assert.equal((await caller.fetch(mk({stage:1,source:SOURCE+" ",failed_examples:[{input:[90,3500,500,250,1000,2500],expected:8800}]}),env)).status,409);
 const second=await caller.fetch(mk({stage:1,source:SOURCE,failed_examples:[{input:[90,3500,500,250,1000,2500],expected:8800}]}),env);
 assert.equal(second.status,200);assert.equal((await second.json()).source,SOURCE);
 assert.equal((await caller.fetch(mk({stage:1,source:SOURCE,failed_examples:[{input:[90,3500,500,250,1000,2500],expected:8800}]}),env)).status,409);
 assert.equal(count,2);
});
