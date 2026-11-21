import test from 'node:test';
import assert from 'node:assert/strict';
import {MODEL,SCHEMA,oracle,admitStep,safeSource,requestFor,runStep,HEADER} from '../src/evidence_status_loop.js';
const candidate=HEADER+'    if queue == 1:\n        return 1\n    return 0\n';
const cases=[
 [[1,1,3,10,120,1],3],[[2,1,1,10,120,1],4],[[1,1,1,121,120,0],2],
 [[1,0,1,10,120,0],6],[[0,0,2,10,120,1],5],[[0,0,1,10,120,0],1],
 [[0,0,3,10,120,0],7],[[0,0,0,10,120,0],0],[[0,1,0,10,120,0],-1],
 [[0,0,1,10,0,0],-1],[[1,1,4,120,120,0],3]
];
test('independent fixed receipt and queue precedence oracle',()=>{
 for(const [x,expected] of cases)assert.equal(oracle(x),expected);
});
test('stage zero is exact fixed selector and rejects caller prompt',()=>{
 assert.deepEqual(admitStep({stage:0}),{stage:0,source:null,failedExamples:[]});
 assert.equal(admitStep({stage:0,prompt:'send secret'}),null);
});
test('stage one requires independently correct numeric feedback',()=>{
 const row={input:[1,1,3,10,120,1],expected:3};
 assert.equal(admitStep({stage:1,source:candidate,failed_examples:[row]}).failedExamples[0].expected,3);
 assert.equal(admitStep({stage:1,source:candidate,failed_examples:[{...row,expected:5}]}),null);
 assert.equal(admitStep({stage:1,source:candidate,failed_examples:[row,row]}),null);
});
test('model output source rejects imports and nonfixed code',()=>{
 assert.equal(safeSource(HEADER+'    import os\n    return 4\n'),null);
 assert.equal(safeSource('def arbitrary(x):\n    return 4\n'),null);
});
test('stage one prompt includes verified feedback but no tools',()=>{
 const p=requestFor(1,candidate,[{input:[1,1,3,10,120,1],expected:3}]);
 assert.equal(p.model,MODEL);assert.equal(p.messages.length,2);
 assert.match(p.messages[1].content,/expected=3/);
 assert.equal(p.tools,undefined);
});
test('provider output is preserved only as unexecuted candidate',async()=>{
 const v=await runStep({input:{stage:0},providerFetch:async()=>({status:200,json:async()=>({choices:[{message:{content:JSON.stringify({source:candidate})}}]})})});
 assert.equal(v.schema,SCHEMA);assert.equal(v.status,'candidate_unexecuted');
 assert.equal(v.provider_calls,1);assert.equal(v.production_admitted,false);assert.equal(v.model_code_executed,false);
});
test('rate limit stops without retry',async()=>{
 let requests=0;const v=await runStep({input:{stage:0},providerFetch:async()=>{requests++;return {status:429};}});
 assert.equal(v.status,'rate_limited');assert.equal(requests,1);
});
test('bad receipt fails closed',async()=>{
 const v=await runStep({input:{stage:0},providerFetch:async()=>({status:200,json:async()=>({choices:[{message:{content:'oops'}}]})})});
 assert.equal(v.status,'format_rejected');assert.equal(v.source,null);
});
