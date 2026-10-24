import test from 'node:test';
import assert from 'node:assert/strict';
import { applyCandidateSqliteTransition } from '../cloudflare/fleet-authority/src/live_owner_fence_sqlite_candidate_v1.mjs';

const account='a'.repeat(64), other='b'.repeat(64);
const host='c'.repeat(64), session='d'.repeat(64);
const proof={
  operatorAttested:true, predecessorGatewayTerminated:true,
  predecessorWriterQuiesced:true, brokerJournalReconciled:true,
  allBrokerWriteSessionsExcluded:true,
};
const req=(id=1,changes={})=>({
  operation:'acquire', accountDigest:account, ownerRunAttempt:String(40000000000+id)+':1',
  expectedEpoch:0, hostDigest:host, brokerSessionDigest:session,
  ttlMs:10_000,...changes,
});
const verified=(now=1000,ev=proof)=>({serverNowMs:now,verifiedEvidence:ev});
const apply=(store,request=req(),trusted=verified()) =>
  applyCandidateSqliteTransition({storage:store,request,trusted});

class FakeSynchronousSqlite {
  constructor(rows=new Map()) {
    this.rows=rows;
    this.transactions=0;
    this.failWrite=false;
    this.sql={exec:(query,...params)=>{
      if(query.startsWith('CREATE TABLE IF NOT EXISTS'))return {toArray:()=>[]};
      if(query.startsWith('SELECT state_json FROM')) {
        const value=this.rows.get(params[0]);
        return {toArray:()=>value === undefined ? []:[{state_json:value}]};
      }
      if(query.startsWith('INSERT INTO')) {
        this.rows.set(params[0],params[1]);
        if(this.failWrite){this.failWrite=false;throw new Error('synthetic sqlite disk fault');}
        return {toArray:()=>[]};
      }
      throw new Error('sql shape rejected');
    }};
  }
  transactionSync(fn) {
    this.transactions++;
    const rollback=new Map(this.rows);
    try { const result=fn(); if(result instanceof Promise)throw new Error('async not permitted'); return result; }
    catch(e) { this.rows=new Map(rollback);throw e; }
  }
}
test('candidate transaction commits one account-scoped epoch then rejects same-epoch contender',()=>{
  const store=new FakeSynchronousSqlite();
  const first=apply(store);
  assert.equal(first.ok,true);
  assert.equal(first.epoch,1);
  assert.equal(first.live_submit_authorized,false);
  assert.equal(first.broker_mutation_attempted,false);
  const loser=apply(store,req(2));
  assert.equal(loser.ok,false);
  assert.equal(loser.status,'stale_fencing_epoch');
  assert.equal(JSON.parse(store.rows.get(account)).holder,req().ownerRunAttempt);
});
test('a new Durable Object instance sees persisted row rather than reinitializing epoch',()=>{
  const rows=new Map();
  const first=new FakeSynchronousSqlite(rows);
  assert.equal(apply(first).ok,true);
  const restart=new FakeSynchronousSqlite(rows);
  assert.equal(apply(restart,req(2)).status,'stale_fencing_epoch');
  assert.equal(restart.rows.size,1);
});
test('an unsafe request-supplied clock or synthetic proof is rejected BEFORE any storage touch',()=>{
  const store=new FakeSynchronousSqlite();
  for(const bad of [
    req(1,{serverNowMs:10_000}),
    req(1,{verifiedEvidence:proof}),
    req(1,{accountDigest:'PRIVATE_ACCOUNT_NUMBER'}),
  ]){
    const r=apply(store,bad);
    assert.equal(r.ok,false);
  }
  assert.equal(store.transactions,0);
  assert.equal(store.rows.size,0);
});
test('missing trust context and unavailable SQLite are fail closed',()=>{
  const store=new FakeSynchronousSqlite();
  assert.equal(applyCandidateSqliteTransition({storage:store,request:req()}).status,
               'trusted_transition_context_required');
  assert.equal(applyCandidateSqliteTransition({request:req(),trusted:verified()}).status,
               'candidate_sqlite_transaction_unavailable');
  assert.equal(store.rows.size,0);
});
test('synthetic disk failure rolls back candidate and never returns success',()=>{
  const store=new FakeSynchronousSqlite();
  store.failWrite=true;
  const rejected=apply(store);
  assert.equal(rejected.status,'candidate_sqlite_transaction_failed');
  assert.equal(rejected.live_submit_authorized,false);
  assert.equal(store.rows.size,0);
  assert.equal(apply(store,req(2)).ok,true);
  assert.equal(JSON.parse(store.rows.get(account)).holder,req(2).ownerRunAttempt);
});
test('corrupted storage row prevents takeover, never silently resets epoch',()=>{
  const store=new FakeSynchronousSqlite();
  store.rows.set(account,'not json');
  const bad=apply(store);
  assert.equal(bad.ok,false);
  assert.equal(bad.status,'candidate_stored_state_invalid');
  assert.equal(store.rows.get(account),'not json');
  store.rows.set(account,JSON.stringify({schema:'corrupt',epoch:300}));
  assert.equal(apply(store).status,'invalid_persisted_state');
  assert.equal(store.rows.size,1);
});
test('account isolation retains independent epochs and no plaintext account',()=>{
  const store=new FakeSynchronousSqlite();
  assert.equal(apply(store).ok,true);
  assert.equal(apply(store,req(2,{accountDigest:other})).ok,true);
  assert.equal(store.rows.size,2);
  assert.equal(JSON.parse(store.rows.get(other)).accountDigest,other);
  assert.equal([...store.rows.keys()].every(x=>/^[a-f0-9]{64}$/.test(x)),true);
});
test('separate unshared DO stores can each grant a candidate: global routing remains required',()=>{
  const a=new FakeSynchronousSqlite(), b=new FakeSynchronousSqlite();
  assert.equal(apply(a,req(1)).ok,true);
  assert.equal(apply(b,req(2)).ok,true);
  // This proves why a unique authenticated account->DO ID route is required.
  assert.notEqual(JSON.parse(a.rows.get(account)).holder,JSON.parse(b.rows.get(account)).holder);
});
