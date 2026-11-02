import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import {V4_HOLDOUT_CASES} from "../src/workforce_v4_holdout.js";
import {V4_MECHANISM_HOLDOUTS} from "../src/workforce_v4_mechanism_holdout.js";
import {runV4SourceOnlyCase as run} from "../src/workforce_v4_provider_runner.js";
const MODEL="poolside/laguna-xs-2.1";
const response=(status,content)=>({status,json:async()=>content});
function mock({catalogStatus=200,postStatus=200,toolCall=false,wrong=false,catalogModels=[MODEL]}={}){
  const calls=[];
  const providerFetch=async (url,opts)=>{
    calls.push({url,method:opts?.method,body:opts?.body});
    if(url.endsWith("/models"))return response(catalogStatus,{data:catalogModels.map(id=>({id}))});
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

test("v4 fixed-cohort route is private-only, disabled-by-default and bounded to evidence metadata",()=>{
 const worker=fs.readFileSync(new URL("../src/index.js",import.meta.url),"utf8");
 const caller=fs.readFileSync(new URL("../local-probe/src/index.js",import.meta.url),"utf8");
 const config=JSON.parse(fs.readFileSync(new URL("../wrangler.jsonc",import.meta.url),"utf8"));
 assert.equal(config.workers_dev,false);
 assert.equal(config.preview_urls,false);
 assert.equal(config.vars.CC_NVIDIA_DIAGNOSTIC_ENABLED,"0");
 assert(worker.includes('url.pathname==="/internal/diagnostics/nvidia-workforce-v4"'));
 assert(worker.includes('env.CC_NVIDIA_DIAGNOSTIC_ENABLED!=="1"'));
 assert(caller.includes('const WORKFORCE_V4_PATH = "/workforce-v4-case";'));
 assert(caller.includes("sanitizeV4MechanismReceipt(value)"));
 assert(!caller.includes("private_prompt_input"));
 assert(!config.routes);
 assert(!config.route);
});
test("catalog listing alone cannot admit an unreviewed v4 model",async()=>{
  const x=mock({catalogModels:["openai/gpt-oss-20b"]});
  const r=await run({modelIndex:0,caseIndex:0,providerFetch:x.providerFetch});
  assert.equal(r.status,"model_not_admitted_for_v4");
  assert.equal(r.model,"openai/gpt-oss-20b");
  assert.equal(r.provider_calls,1);
  assert.equal(x.calls.length,1);
  assert.equal(r.production_admitted,false);
});

test("new 60 mechanism cases use only exact source-owned prompts on the existing v4 mocked provider adapter",async()=>{
 for(let i=0;i<V4_MECHANISM_HOLDOUTS.length;i++){
  const c=V4_MECHANISM_HOLDOUTS[i],requests=[];
  const providerFetch=async(url,opts)=>{
   requests.push({url,opts});
   if(url.endsWith("/models"))return response(200,{data:[{id:MODEL}]});
   return response(200,{choices:[{finish_reason:"stop",message:{
    content:JSON.stringify({...c.expected,rationale:
     "These fixed evidence identifiers support the classification; a human must review the explanation.",
     proposed_only:true})}}],
    usage:{prompt_tokens:225,completion_tokens:90}});
  };
  const r=await run({modelIndex:0,caseIndex:i,providerFetch,cohort:"mechanism_v4"});
  assert.equal(requests.length,2,c.id);
  const prompt=JSON.parse(requests[1].opts.body);
  assert(prompt.messages[1].content.includes(c.records[1].id));
  assert(!prompt.messages[1].content.includes("production_admitted"));
  assert.equal(r.cohort,"mechanism_v4");
  assert.equal(r.mechanism_id,c.mechanism_id);
  assert.equal(r.case_id,c.id);
  assert.equal(r.objective_label_pass,true,c.id);
  assert.equal(r.first_pass,false,c.id);
  assert.equal(r.status,"human_review_required");
  assert.equal(r.production_admitted,false);
  assert.equal(r.answer_exported,false);
  assert.equal(r.raw_response_exported,false);
  assert(!Object.hasOwn(r,"rationale"));
 }
});
test("new cohort admits no caller-supplied input, invalid cohort, or catalog-unreviewed model",async()=>{
 const c=V4_MECHANISM_HOLDOUTS[0],s=mock();
 await assert.rejects(run({modelIndex:0,caseIndex:0,providerFetch:s.providerFetch,cohort:"arbitrary_user_text"}),/invalid_fixed_v4_selector/);
 const no=await run({modelIndex:0,caseIndex:0,providerFetch:mock({catalogModels:["openai/gpt-oss-20b"]}).providerFetch,cohort:"mechanism_v4"});
 assert.equal(no.status,"model_not_admitted_for_v4");
 assert.equal(no.provider_calls,1);
 assert.equal(no.production_admitted,false);
});
