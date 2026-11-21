import test from 'node:test';
import assert from 'node:assert/strict';
import {createEvidenceStatusCaller} from '../local-probe/src/evidence_status_caller.js';
import {SCHEMA,MODEL,HEADER} from '../src/evidence_status_loop.js';
const source=HEADER+'    if queue == 1:\n        return 1\n    return 0\n';
const req=(body,url='http://127.0.0.1:8787/evidence-status-step')=>new Request(url,{method:'POST',headers:{'Content-Type':'application/json','Content-Length':String(Buffer.byteLength(JSON.stringify(body)))},body:JSON.stringify(body)});
const env={NVIDIA_SERVICE:{async fetch(r){const body=await r.json();return new Response(JSON.stringify({schema:SCHEMA,stage:body.stage,model:MODEL,provider_calls:1,http_status:200,status:'candidate_unexecuted',elapsed_ms:7,source,source_valid_shape:true,private_input_used:false,model_code_executed:false,commands_executed:false,production_admitted:false}),{headers:{'Content-Type':'application/json'}});}}};
test('draft then exact-revision is one-use and bound to original',async()=>{
 const c=createEvidenceStatusCaller();const one=await c.fetch(req({stage:0}),env);
 assert.equal(one.status,200);assert.equal((await one.json()).source,source);
 assert.equal((await c.fetch(req({stage:0}),env)).status,409);
 assert.equal((await c.fetch(req({stage:1,source,failed_examples:[{input:[1,1,1,10,120,0],expected:3}]}),env)).status,200);
 assert.equal((await c.fetch(req({stage:1,source,failed_examples:[{input:[1,1,1,10,120,0],expected:3}]}),env)).status,409);
});
test('caller rejects forged source, protected tool and malformed expected answer',async()=>{
 const c=createEvidenceStatusCaller();await c.fetch(req({stage:0}),env);
 assert.equal((await c.fetch(req({stage:1,source:'garbage',failed_examples:[{input:[1,1,1,10,120,0],expected:3}]}),env)).status,400);
 assert.equal((await c.fetch(req({stage:1,source,failed_examples:[{input:[1,1,1,10,120,0],expected:5}]}),env)).status,400);
 assert.equal((await c.fetch(req({stage:1,source,failed_examples:[{input:[1,1,1,10,120,0],expected:3}],tool:'root'}),env)).status,400);
});
test('does not disclose worker path through arbitrary URL',async()=>{
 const c=createEvidenceStatusCaller();assert.equal((await c.fetch(req({stage:0},'https://host.example/evidence-status-step'),env)).status,404);
});
test('binding absent returns unavailable, not simulated success',async()=>{
 const c=createEvidenceStatusCaller();const res=await c.fetch(req({stage:0}),{});assert.equal(res.status,503);assert.equal((await res.json()).error,'binding_unavailable');
});
