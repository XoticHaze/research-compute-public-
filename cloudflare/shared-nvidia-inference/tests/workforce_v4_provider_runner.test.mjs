import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import {V4_HOLDOUT_CASES} from "../src/workforce_v4_holdout.js";
import {runV4SourceOnlyCase as run} from "../src/workforce_v4_provider_runner.js";
const MODEL="poolside/laguna-xs-2.1";
const response=(status,content)=>({status,json:async()=>content});
function mock({catalogStatus=200,postStatus=200,toolCall=false,wrong=false}={}){
  const calls=[];
  const providerFetch=async (url,opts)=>{
    calls.push({url,method:opts?.method,body:opts?.body});
    if(url.endsWith("/models"))return response(catalogStatus,{data:[{id:MODEL}]});
    const c=V4_HOLDOUT_CASES[0],expected=c.expected;
    const body={
      state:wrong?"unverified":expected.state,
      next_action:expected.next_action,
      evidence_refs:expected.evidence_refs,
      uncertainty:expected.uncertainty,
      rationale:"SENSITIVE_MODEL_ONLY_SENTINEL: the independently cited record establishes this limited result.",
      proposed_only:true,
    };
    return response(postStatus,{choices:[{finish_reason:"stop",message:{
      content:JSON.stringify(body),tool_calls:toolCall?[{id:"forbidden_tool",type:"function"}]:[]
    }}],usage:{prompt_tokens:500,completion_tokens:100}});
  };
  return {calls,providerFetch};
}
test("metadata-only v4 adapter never exports rationale or promotes model quality",async()=>{
  const x=mock(),receipt=await run({modelIndex:0,caseIndex:0,providerFetch:x.providerFetch});
  assert.equal(x.calls.length,2);
  assert(x.calls[0].url.endsWith("/models"));
  assert(x.calls[1].url.endsWith("/chat/completions"));
  const request=JSON.parse(x.calls[1].body);
  assert.equal(request.model,MODEL);
  assert.equal(request.stream,false);
  assert.equal(request.messages.length,2);
  assert.equal(receipt.status,"human_review_required");
  assert.equal(receipt.objective_label_pass,true);
  assert.equal(receipt.first_pass,false);
  assert.equal(receipt.full_task_accepted,false);
  assert.equal(receipt.production_admitted,false);
  assert.equal(receipt.private_input_used,false);
  assert.equal(receipt.raw_response_exported,false);
  assert(!JSON.stringify(receipt).includes("SENSITIVE_MODEL_ONLY_SENTINEL"));
  assert(!Object.hasOwn(receipt,"messages"));
  assert(!Object.hasOwn(receipt,"answer"));
});
test("tool proposals, incorrect labels and provider holds are never treated as success",async()=>{
  const t=mock({toolCall:true}),r=await run({modelIndex:0,caseIndex:0,providerFetch:t.providerFetch});
  assert.equal(r.status,"tool_attempt_rejected");
  assert.equal(r.critical_authority_violation,true);
  assert.equal(r.tools_executed,false);
  assert.equal(r.objective_label_pass,false);
  const wrong=mock({wrong:true});
  const f=await run({modelIndex:0,caseIndex:0,providerFetch:wrong.providerFetch});
  assert.equal(f.status,"human_review_required");
  assert.equal(f.objective_label_pass,false);
  const h=mock({catalogStatus:429}),held=await run({modelIndex:0,caseIndex:0,providerFetch:h.providerFetch});
  assert.equal(held.status,"provider_rate_limited");
  assert.equal(held.provider_calls,1);
  assert.equal(h.calls.length,1);
  const unavailable=mock({postStatus:404});
  const err=await run({modelIndex:0,caseIndex:0,providerFetch:unavailable.providerFetch});
  assert.equal(err.status,"model_http_unavailable");
  assert.equal(err.first_pass,false);
});
test("catalog only, fixed selectors and unexposed routes",async()=>{
  const f=mock();
  const notFound=await run({modelIndex:1,caseIndex:0,providerFetch:f.providerFetch});
  assert.equal(notFound.status,"model_index_not_in_authenticated_catalog");
  assert.equal(notFound.provider_calls,1);
  await assert.rejects(run({modelIndex:-1,caseIndex:0,providerFetch:()=>{}}),/invalid_fixed_v4_selector/);
  await assert.rejects(run({modelIndex:0,caseIndex:60,providerFetch:()=>{}}),/invalid_fixed_v4_selector/);
  await assert.rejects(run({modelIndex:0,caseIndex:0,providerFetch:null}),/invalid_fixed_v4_selector/);
});

test("v4 candidate is not connected to deployed Worker, loopback caller or public ingress",()=>{
  const worker=fs.readFileSync(new URL("../src/index.js",import.meta.url),"utf8");
  const caller=fs.readFileSync(new URL("../local-probe/src/index.js",import.meta.url),"utf8");
  assert(!worker.includes("workforce_v4_provider_runner"));
  assert(!caller.includes("workforce_v4_provider_runner"));
  assert(!worker.includes("runV4SourceOnlyCase"));
  assert(!caller.includes("/v4-case"));
});
