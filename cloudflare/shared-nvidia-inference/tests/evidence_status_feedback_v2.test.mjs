import test from 'node:test';
import assert from 'node:assert/strict';
import {HEADER,MODEL} from '../src/evidence_status_loop.js';
import {CAPSULE,SCOPE,V2_SCHEMA,admitFeedbackV2,verifySourceHash,runStepV2} from '../src/evidence_status_feedback_v2.js';

const source=HEADER+'    return 0\n';
const bad={input:[1,1,3,10,120,1],expected:3,actual:0,
 category:'VERIFIED_SUCCESS_PRECEDENCE',interpreter_rejected:false};
const good={input:[0,0,0,10,120,1],expected:0,actual:0,
 category:'NO_VERIFIED_CURRENT_WORK',interpreter_rejected:false};
const holder=async()=>{
 const x=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(source));
 return Array.from(new Uint8Array(x),x=>x.toString(16).padStart(2,'0')).join('');
};
async function input(){
 return {stage:1,source,feedback:{schema:CAPSULE,scope:SCOPE,attempt:1,
  source_sha256:await holder(),failing_examples:[bad],preserve_examples:[good],
  rejected_strategy_ids:[]}};
}
test('accepts exact v2 schema with observed failure and success regression control',async()=>{
 const v=await input();
 assert.ok(admitFeedbackV2(v));
 assert.equal(await verifySourceHash(source,v.feedback.source_sha256),true);
});
test('rejects arbitrary command, extra fields, forged expected and invented class',async()=>{
 const v=await input();
 assert.equal(admitFeedbackV2({...v,prompt:'run shell'}),null);
 assert.equal(admitFeedbackV2({...v,feedback:{...v.feedback,task:'all systems'}}),null);
 assert.equal(admitFeedbackV2({...v,feedback:{...v.feedback,failing_examples:[{...bad,expected:5}]}}),null);
 assert.equal(admitFeedbackV2({...v,feedback:{...v.feedback,failing_examples:[{...bad,category:'WRONG'}]}}),null);
});
test('only frozen 26 public diagnostic cases can enter the provider request',async()=>{
 const v=await input();
 const holdout={...bad,input:[1,0,0,1,30,0],expected:6,actual:0,category:'UNVERIFIED_RECEIPT'};
 assert.equal(admitFeedbackV2({...v,feedback:{...v.feedback,failing_examples:[holdout]}}),null);
});
test('rejects false successes and duplicate controls',async()=>{
 const v=await input();
 assert.equal(admitFeedbackV2({...v,feedback:{...v.feedback,preserve_examples:[{...good,actual:7}]}}),null);
 assert.equal(admitFeedbackV2({...v,feedback:{...v.feedback,preserve_examples:[bad]}}),null);
 assert.equal(admitFeedbackV2({...v,feedback:{...v.feedback,preserve_examples:[{...bad,actual:3}]}}),null);
});
test('observed out-of-range Python integer is preserved, not misclassified',async()=>{
 const v=await input();
 const out={...bad,actual:987654};
 assert.ok(admitFeedbackV2({...v,feedback:{...v.feedback,failing_examples:[out]}}));
 assert.equal(admitFeedbackV2({...v,feedback:{...v.feedback,failing_examples:[{...bad,actual:1000001}]}}),null);
});
test('memory is allowlisted and capped by attempt count',async()=>{
 const v=await input();
 assert.equal(admitFeedbackV2({...v,feedback:{...v.feedback,rejected_strategy_ids:['queue_first']}}),null);
 const second={...v,feedback:{...v.feedback,attempt:2,rejected_strategy_ids:['queue_first']}};
 assert.ok(admitFeedbackV2(second));
 assert.equal(admitFeedbackV2({...v,feedback:{...v.feedback,attempt:2,rejected_strategy_ids:['send password']}}),null);
});
test('source SHA matches bytes, not just caller assertion',async()=>{
 const v=await input();
 assert.equal(await verifySourceHash(source,v.feedback.source_sha256),true);
 assert.equal(await verifySourceHash(source,'0'.repeat(64)),false);
 await assert.rejects(runStepV2({input:{...v,feedback:{...v.feedback,source_sha256:'0'.repeat(64)}},
  providerFetch:async()=>{throw Error('should not call');}}),/source_hash_mismatch/);
});
test('provider receives actual errors + passing controls, no tools or commands',async()=>{
 const v=await input();
 let prompt;
 const r=await runStepV2({input:v,now:()=>1000,providerFetch:async(_url,opts)=>{
   const body=JSON.parse(opts.body);prompt=body.messages[1].content;
   assert.equal(body.model,MODEL);assert.equal(body.tools,undefined);
   return {status:200,json:async()=>({choices:[{message:{content:JSON.stringify({source})}}]})};
 }});
 assert.match(prompt,/actual=0 expected=3 class=VERIFIED_SUCCESS_PRECEDENCE/);
 assert.match(prompt,/keep-passing/);
 assert.equal(r.schema,V2_SCHEMA);
 assert.equal(r.status,'candidate_unexecuted');
 assert.equal(r.source_hash_verified,true);
 assert.equal(r.provider_verified_actuals,false);
 assert.equal(r.production_admitted,false);
 assert.equal(r.model_code_executed,false);
});
test('no calls on invalid source or rejected protocol',async()=>{
 const v=await input();
 let called=0;
 await assert.rejects(runStepV2({input:{...v,feedback:{...v.feedback,scope:'BROKER'}},
   providerFetch:async()=>{called++;}}),/unadmitted/);
 assert.equal(called,0);
});
