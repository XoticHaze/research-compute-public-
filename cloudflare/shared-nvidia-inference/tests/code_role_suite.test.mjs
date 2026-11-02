import test from "node:test";
import assert from "node:assert/strict";
import {MODELS,TASKS,requestFor,sanitizeCandidate} from "../src/code_role_suite.js";
import {runCodeRoleCase} from "../src/code_role_suite_runner.js";
import {sanitizeCodeRoleReceipt} from "../local-probe/src/code_role_receipt.js";
const SOLUTIONS=[
 "def retry_delay_ms(attempt, max_attempts, base_ms, cap_ms):\n    if attempt <= 0 or max_attempts <= 0 or attempt >= max_attempts or base_ms <= 0 or cap_ms <= 0:\n        return None\n    return min(cap_ms, base_ms * (2 ** (attempt - 1)))\n",
 "def clamp_window(value, low, high, fallback):\n    if low > high:\n        return fallback\n    return max(low, min(high, value))\n",
 "def budget_remaining(limit, spent, reserved, floor):\n    if limit < 0 or spent < 0 or reserved < 0 or floor < 0:\n        return None\n    if limit - spent - reserved < floor:\n        return None\n    return limit - spent - reserved\n",
 "def allocation_limit(equity, risk_bps, cap_usd, minimum_usd):\n    if equity <= 0 or risk_bps <= 0 or risk_bps > 10000 or cap_usd <= 0 or minimum_usd <= 0 or cap_usd < minimum_usd:\n        return None\n    if min(cap_usd, (equity * risk_bps) // 10000) < minimum_usd:\n        return None\n    return min(cap_usd, (equity * risk_bps) // 10000)\n",
 "def staleness_status(now_ms, last_ms, warn_ms, expire_ms):\n    if now_ms < 0 or last_ms < 0 or now_ms < last_ms or warn_ms <= 0 or expire_ms <= warn_ms:\n        return -1\n    if now_ms - last_ms >= expire_ms:\n        return 2\n    if now_ms - last_ms >= warn_ms:\n        return 1\n    return 0\n",
];
test("documented model-native discovery profiles do not silently truncate reasoning",()=>{
 for(let i=0;i<MODELS.length;i++){
  const q=requestFor(i,2);
  assert.equal(q.model,MODELS[i]);
  assert.equal(q.temperature,1.0);
  assert.equal(q.top_p,0.95);
  assert.equal(q.max_tokens,8192);
  assert.equal(q.stream,false);
  assert.equal(q.messages.length,2);
  assert.equal(q.tools,undefined);
  assert.equal(q.chat_template_kwargs,undefined);
 }
 // This allowance is an experimental first-wave value for MiniMax, not
 // NVIDIA's maximum (65536), and cannot be overridden by input selection.
 for(let i=0;i<TASKS.length;i++)
  assert.equal(requestFor(1,i).max_tokens,8192);
});
test("five materially distinct fixed synthetic coding tasks each have exact model and function boundary",()=>{
 assert.equal(TASKS.length,5);
 assert.equal(new Set(TASKS.map(x=>x.id)).size,5);
 for(let i=0;i<TASKS.length;i++){
  assert.equal(TASKS[i].args.length,4);
  for(let model=0;model<2;model++){
   const req=requestFor(model,i);
   assert.equal(req.model,MODELS[model]);
   assert(req.messages[1].content.includes(TASKS[i].id)===false);
   assert(req.messages[1].content.includes(TASKS[i].requirements));
  }
  assert.equal(sanitizeCandidate(JSON.stringify({source:SOLUTIONS[i]}),i),SOLUTIONS[i]);
  for(const j of [0,1,2,3,4]){
   if(j!==i)assert.equal(sanitizeCandidate(JSON.stringify({source:SOLUTIONS[j]}),i),null);
  }
 }
 for(const x of [-1,5,"0",null])assert.throws(()=>requestFor(0,x),/invalid_synthetic_code_task_index/);
});
test("five independent one-call simulated provider responses generate only fixed synthetic source",async()=>{
 for(let i=0;i<TASKS.length;i++){
  const result=await runCodeRoleCase({modelIndex:0,taskIndex:i,providerFetch:async(_url,opts)=>{
   const body=JSON.parse(opts.body);
   assert.equal(body.model,MODELS[0]);
   return {status:200,async json(){return {choices:[{message:{content:JSON.stringify({source:SOLUTIONS[i]})}}]};}};
  }});
  assert.equal(result.status,"candidate_unexecuted");
  const receipt=sanitizeCodeRoleReceipt(result);
  assert(receipt);
  assert.equal(receipt.code,SOLUTIONS[i]);
  assert.equal(receipt.model_code_executed,false);
  assert.equal(receipt.private_data_exposed,false);
 }
});
test("first 429 has no retry and no model source",async()=>{
 let calls=0;
 const r=await runCodeRoleCase({modelIndex:1,taskIndex:4,providerFetch:async()=>{
  calls++;return{status:429};
 }});
 assert.equal(calls,1);
 assert.equal(r.status,"provider_rate_limited");
 assert.equal(sanitizeCodeRoleReceipt(r).code,null);
});
test("arbitrary imports, comments, strings, exfil paths and wrong case identity fail closed",()=>{
 const base=SOLUTIONS[1];
 const extra=[
  base+"import os\n",
  base+"# comment\n",
  base.replace("return fallback",'return "secret"'),
  base.replace("return fallback","return __import__(os)"),
  base.replace("return fallback","return open(token)"),
 ];
 for(const item of extra)assert.equal(sanitizeCandidate(JSON.stringify({source:item}),1),null);
 assert.equal(sanitizeCandidate(JSON.stringify({source:base,other:"injection"}),1),null);
 const receipt={schema:"commandcenter.nvidia_role_code_case.v1",model:MODELS[0],
  model_index:0,task_id:TASKS[1].id,task_index:1,status:"candidate_unexecuted",
  provider_calls:1,http_status:200,elapsed_ms:100,source:base,source_valid_shape:true};
 assert(sanitizeCodeRoleReceipt(receipt));
 assert.equal(sanitizeCodeRoleReceipt({...receipt,task_index:2}),null);
 assert.equal(sanitizeCodeRoleReceipt({...receipt,source:base+"import os"}),null);
});
