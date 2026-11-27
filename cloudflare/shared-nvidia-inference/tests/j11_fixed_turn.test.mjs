import test from "node:test";
import assert from "node:assert/strict";
import {FIXTURE_BLOB,MODEL,admitSelector,promptFor,candidateAction,runFixedJ11Turn} from "../src/j11_fixed_turn.js";
const selector={fixture_blob:FIXTURE_BLOB,task_id:"E",observed_routes:["edge"]};
test("fixed selector does not admit caller prompts or unknown route",()=>{
 assert.ok(admitSelector(selector));assert.equal(admitSelector({...selector,prompt:"arbitrary"}),null);assert.equal(admitSelector({...selector,observed_routes:["unknown"]}),null);
 assert.equal(JSON.stringify(promptFor(selector)).includes("E-app"),false);
});
test("candidate cannot claim unread evidence or duplicate route",()=>{
 assert.equal(candidateAction(selector,JSON.stringify({kind:"submit",state:"unhealthy",evidence:["E-app"]})),null);
 assert.equal(candidateAction(selector,JSON.stringify({kind:"read",route:"edge"})),null);
});
test("one fixed candidate inference call, no action execution",async()=>{
 let calls=0;
 const r=await runFixedJ11Turn({selector,providerFetch:async(url,opts)=>{
  calls++;const body=JSON.parse(opts.body);assert.equal(url,"https://integrate.api.nvidia.com/v1/chat/completions");assert.equal(opts.redirect,"manual");assert.equal(body.model,MODEL);assert.equal(body.max_tokens,512);
  return {status:200,json:async()=>({choices:[{message:{content:'{"kind":"read","route":"application"}'}}],usage:{prompt_tokens:111,completion_tokens:12}})};
 }});
 assert.equal(calls,1);assert.equal(r.status,"candidate_unexecuted");assert.equal(r.model_action_executed,false);assert.equal(r.action.route,"application");
});
test("429 stops without retry",async()=>{
 let calls=0;const r=await runFixedJ11Turn({selector,providerFetch:async()=>{calls++;return {status:429};}});
 assert.equal(calls,1);assert.equal(r.status,"rate_limited");assert.equal(r.action,null);
});
