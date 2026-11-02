import test from "node:test";
import assert from "node:assert/strict";
import {requestFor,TASKS} from "../src/code_role_suite.js";
import {runCodeRoleCase} from "../src/code_role_suite_runner.js";
import {sanitizeCodeRoleReceipt} from "../local-probe/src/code_role_receipt.js";

test("only MiniMax fixed coding requests use documented larger output budget and recommended sampling",()=>{
  for(let i=0;i<TASKS.length;i++){
    const p=requestFor(0,i),m=requestFor(1,i);
    assert.equal(p.model,"poolside/laguna-xs-2.1");
    assert.equal(p.temperature,0);
    assert.equal(p.max_tokens,650);
    assert.equal("top_p" in p,false);
    assert.equal(m.model,"minimaxai/minimax-m3.1-flash");
    assert.equal(m.temperature,1.0);
    assert.equal(m.top_p,0.95);
    assert.equal(m.max_tokens,1800);
    assert.deepEqual(p.messages,m.messages);
  }
});
test("safe finish and reasoning-presence detection never copies raw model text into sanitized receipt",async()=>{
  const r=await runCodeRoleCase({modelIndex:1,taskIndex:2,providerFetch:async()=>({
    status:200,async json(){return {choices:[{finish_reason:"length",message:{
      content:"",reasoning_content:"PRIVATE_MODEL_REASONING_DO_NOT_EXPORT"
    }}]};}
  })});
  assert.equal(r.status,"format_rejected");
  assert.equal(r.final_content_present,false);
  assert.equal(r.reasoning_content_present,true);
  assert.equal(r.finish_reason,"length");
  const safe=sanitizeCodeRoleReceipt(r);
  assert(safe);
  assert.equal(safe.code,null);
  assert.equal(JSON.stringify(safe).includes("PRIVATE_MODEL_REASONING"),false);
});
test("documented tuned parameters preserve strict one-request 429 stop",async()=>{
  let calls=0;
  const r=await runCodeRoleCase({modelIndex:1,taskIndex:3,providerFetch:async(_u,o)=>{
    calls++;
    const req=JSON.parse(o.body);
    assert.equal(req.max_tokens,1800);
    return {status:429};
  }});
  assert.equal(calls,1);
  assert.equal(r.status,"provider_rate_limited");
  assert.equal(sanitizeCodeRoleReceipt(r).code,null);
});
