import test from 'node:test';
import assert from 'node:assert/strict';
import factory,{FactoryLedger} from '../src/index.js';
import {SCHEMA} from '../src/policy.js';

const now=()=>Math.floor(Date.now()/1000);
function owner(email='owner@example.com') {
  return {access:{aud:'owner-audience',getIdentity:async()=>({email})}};
}
function env(overrides={}) {
  return {FACTORY_ACCOUNT_ID:'ce43cd7b917d98a4bb4866d30eed99c0',
    FACTORY_ACCESS_AUD:'owner-audience',
    FACTORY_ALLOWED_EMAILS:'owner@example.com',
    FACTORY_EXECUTOR_ENABLED:'0',FACTORY_CREATE_ENABLED:'0',
    FACTORY_SCOPED_TOKEN_ENABLED:'0',...overrides};
}
const endpoint='https://example.workers.dev/v1/execute';
const request=()=>new Request(endpoint,{method:'POST',
  headers:{'content-type':'application/json','origin':'https://example.workers.dev',
    'sec-fetch-site':'same-origin'},
  body:JSON.stringify({schema:SCHEMA,operation:'ordinary_worker.create',
    request_id:'a'.repeat(32),worker_name:'ordinary-new-worker',
    expires_at:now()+120})});
test('no auth, wrong account and default disabled deny without side effects',async()=>{
  assert.equal((await factory.fetch(request(),env(),{})).status,403);
  assert.equal((await factory.fetch(request(),env(),owner('other@example.com'))).status,403);
  assert.equal((await factory.fetch(request(),env({FACTORY_ACCOUNT_ID:'a'.repeat(32)}),owner())).status,403);
  assert.equal((await factory.fetch(request(),env(),owner())).status,403);
});
test('read-only status does not disclose bearer or enable deployment',async()=>{
  const resp=await factory.fetch(new Request(
    'https://example.workers.dev/v1/status',{method:'GET'}),env(),owner());
  assert.equal(resp.status,200);
  const body=await resp.json();
  assert.equal(body.admitted,false);
  assert.equal(body.token_values_returned,false);
  assert.equal(JSON.stringify(body).includes('Bearer'),false);
});
test('exact existing Worker inspection performs GET-only, redacts credentials and refuses replay',async()=>{
  const id='b'.repeat(32), worker='ordinary-existing-worker';
  const receipts=new Map(), cfCalls=[];
  const durable={
    idFromName:key=>key,
    get:()=>({fetch:async request=>{
      const body=await request.json(), mode=new URL(request.url).pathname;
      if(mode==='/claim') {
        if(receipts.has(body.request_id)) return new Response('{}',{status:409});
        receipts.set(body.request_id,'claimed');
      } else if(mode==='/finish') {
        if(receipts.get(body.request_id)!=='claimed') return new Response('{}',{status:409});
        receipts.set(body.request_id,'finished');
      } else return new Response('{}',{status:404});
      return new Response('{}',{status:200});
    }})
  };
  const allow=env({FACTORY_EXECUTOR_ENABLED:'1',
    FACTORY_INSPECT_ENABLED:'1',FACTORY_PROPOSAL_ONLY:'0',
    FACTORY_WORKERS_ADMIN:{get:async()=> 'test-only-not-a-real-cloudflare-token'},
    FACTORY_LEDGER:durable});
  const inspect=(requestId, workerId=id)=>new Request(endpoint,{method:'POST',
    headers:{'content-type':'application/json','origin':'https://example.workers.dev',
      'sec-fetch-site':'same-origin'},
    body:JSON.stringify({schema:SCHEMA,operation:'existing_worker.inspect',
      request_id:requestId,worker_name:worker,
      worker_id:workerId,expires_at:now()+120})});
  const old=globalThis.fetch;
  globalThis.fetch=async (url,init)=>{
    cfCalls.push({url:String(url),method:init.method});
    return new Response(JSON.stringify({success:true,result:{id,name:worker}}),{
      status:200,headers:{'content-type':'application/json'}});
  };
  try {
    const rid='c'.repeat(32);
    const response=await factory.fetch(inspect(rid),allow,owner());
    assert.equal(response.status,200);
    const body=await response.json();
    assert.equal(body.status,'existing_worker_identity_verified');
    assert.equal(body.worker_id,id);
    assert.equal(body.cloudflare_mutations,0);
    assert.equal(body.service_deployment_verified,false);
    assert.equal(body.bearer_returned,false);
    assert.equal(cfCalls.length,1);
    assert.equal(cfCalls[0].method,'GET');
    assert.equal(cfCalls[0].url,'https://api.cloudflare.com/client/v4/accounts/'+
      'ce43cd7b917d98a4bb4866d30eed99c0/workers/workers/'+id);
    assert.equal((await factory.fetch(inspect(rid),allow,owner())).status,403);
    assert.equal(cfCalls.length,1);
    const wrongId=await factory.fetch(inspect('d'.repeat(32),'e'.repeat(32)),allow,owner());
    assert.equal(wrongId.status,409);
    assert.equal((await wrongId.json()).status,'failed_or_indeterminate');
    assert.equal(cfCalls.length,2);
    assert.equal(cfCalls.every(x=>x.method==='GET'),true);
    assert.equal(JSON.stringify(body).includes('not-a-real-cloudflare-token'),false);
  } finally {
    globalThis.fetch=old;
  }
});
test('inspection separately defaults to disabled, even when executor is on',async()=>{
  const e=env({FACTORY_EXECUTOR_ENABLED:'1',FACTORY_PROPOSAL_ONLY:'0',
    FACTORY_LEDGER:{idFromName:()=> 'id',get:()=>({fetch:async()=>new Response('{}',{status:200})})}});
  const req=new Request(endpoint,{method:'POST',
    headers:{'content-type':'application/json','origin':'https://example.workers.dev',
      'sec-fetch-site':'same-origin'},
    body:JSON.stringify({schema:SCHEMA,operation:'existing_worker.inspect',
      request_id:'f'.repeat(32),worker_name:'ordinary-existing-worker',
      worker_id:'b'.repeat(32),expires_at:now()+120})});
  const response=await factory.fetch(req,e,owner());
  assert.equal(response.status,409);
  assert.equal((await response.json()).status,'failed_or_indeterminate');
});
test('Durable Object refuses replay and unclaimed finish',async()=>{
  const db=new Map();
  const state={storage:{transaction:async(fn)=>{
    const txn={get:async k=>db.get(k),
      put:async(k,v)=>db.set(k,v)};
    return fn(txn);
  }}};
  const ledger=new FactoryLedger(state);
  const url='https://factory-ledger/claim';
  const cmd=()=>new Request(url,{method:'POST',headers:{'content-type':'application/json'},
    body:JSON.stringify({request_id:'b'.repeat(32),operation:'ordinary_worker.create'})});
  assert.equal((await ledger.fetch(cmd())).status,200);
  assert.equal((await ledger.fetch(cmd())).status,409);
  const differentId=new Request('https://factory-ledger/finish',{method:'POST',
    headers:{'content-type':'application/json'},
    body:JSON.stringify({request_id:'c'.repeat(32),result:{status:'passed'}})});
  assert.equal((await ledger.fetch(differentId)).status,409);
  const finish=()=>new Request('https://factory-ledger/finish',{method:'POST',
    headers:{'content-type':'application/json'},
    body:JSON.stringify({request_id:'b'.repeat(32),result:{status:'passed'}})});
  assert.equal((await ledger.fetch(finish())).status,200);
  assert.equal((await ledger.fetch(finish())).status,409);
});
