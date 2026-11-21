import test from 'node:test';
import assert from 'node:assert/strict';
import {createEvidenceStatusCaller} from '../local-probe/src/evidence_status_caller.js';
import {HEADER,SCHEMA,MODEL} from '../src/evidence_status_loop.js';
import {V2_SCHEMA,CAPSULE,SCOPE} from '../src/evidence_status_feedback_v2.js';

const source=HEADER+'    return 0\n';
const post=(path,payload)=>{
 const b=JSON.stringify(payload);
 return new Request('http://127.0.0.1:8787'+path,{method:'POST',headers:{
  'content-type':'application/json','content-length':String(new TextEncoder().encode(b).length)
 },body:b});
};
const result=async(stage,schema)=>({
 schema,stage,model:MODEL,provider_calls:1,status:'candidate_unexecuted',http_status:200,
 elapsed_ms:200,source,source_valid_shape:true,private_input_used:false,
 model_code_executed:false,commands_executed:false,production_admitted:false,
 ...(schema===V2_SCHEMA?{source_hash_verified:true,provider_verified_actuals:false,
  feedback_protocol:'observed_vs_expected_v2'}:{})
});
const hash=async()=>{
 const d=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(source));
 return Array.from(new Uint8Array(d),x=>x.toString(16).padStart(2,'0')).join('');
};
test('one-use bound caller permits v1 draft then v2 revision only',async()=>{
 const destinations=[];
 const caller=createEvidenceStatusCaller();
 const env={NVIDIA_SERVICE:{fetch:async req=>{
  destinations.push(new URL(req.url).pathname);
  const body=await req.json();const schema=body.stage===0?SCHEMA:V2_SCHEMA;
  return new Response(JSON.stringify(await result(body.stage,schema)),{headers:{'content-type':'application/json'}});
 }}};
 const first=await caller.fetch(post('/evidence-status-step',{stage:0}),env);
 assert.equal(first.status,200);
 const f={schema:CAPSULE,scope:SCOPE,attempt:1,source_sha256:await hash(),
  failing_examples:[{input:[1,1,3,10,120,1],expected:3,actual:0,
   category:'VERIFIED_SUCCESS_PRECEDENCE',interpreter_rejected:false}],
  preserve_examples:[],rejected_strategy_ids:[]};
 const second=await caller.fetch(post('/evidence-status-step-v2',{stage:1,source,feedback:f}),env);
 assert.equal(second.status,200);
 assert.equal((await second.json()).source_hash_verified,true);
 assert.deepEqual(destinations,[
  '/internal/diagnostics/nvidia-evidence-status-step',
  '/internal/diagnostics/nvidia-evidence-status-v2'
 ]);
 const replay=await caller.fetch(post('/evidence-status-step-v2',{stage:1,source,feedback:f}),env);
 assert.equal(replay.status,409);
 assert.equal(destinations.length,2);
});
test('missing draft and invented prompt never reach the binding',async()=>{
 let calls=0;
 const env={NVIDIA_SERVICE:{fetch:async()=>{calls++;throw Error('forbidden');}}};
 const caller=createEvidenceStatusCaller();
 const malformed=post('/evidence-status-step-v2',{stage:1,source,prompt:'do stuff'});
 assert.equal((await caller.fetch(malformed,env)).status,400);
 assert.equal(calls,0);
});
