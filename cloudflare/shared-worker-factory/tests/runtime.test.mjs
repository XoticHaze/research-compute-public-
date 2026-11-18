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
