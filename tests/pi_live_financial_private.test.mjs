import test from 'node:test';
import assert from 'node:assert/strict';
import { webcrypto } from 'node:crypto';
import { FINANCE_DOMAIN, FINANCE_SCHEMA, ACCOUNT_SCHEMA,
  canonicalPrivateJson, verifyPrivateFinancial,
  storePrivateFinancial, readPrivateFinancial } from '../cloudflare/operator-console/src/pi_live_financial_private.js';

globalThis.crypto ||= webcrypto;
const now = Date.parse('2026-11-13T23:15:00Z');
const env = {PI_LIVE_FINANCE_HMAC_KEY:'ab'.repeat(32), PI_LIVE_EXPECTED_ACCOUNT_SHA256:'cd'.repeat(32)};
const accountFields = ['net_liquidation','cash','buying_power','available_funds','excess_liquidity',
  'initial_margin','maintenance_margin','equity_with_loan_value','day_pnl','realized_pnl','unrealized_pnl'];
const unknown = () => ({value:null,currency:null,status:'UNVERIFIED'});
function snapshot() {
  const account = Object.fromEntries(accountFields.map(k=>[k, unknown()]));
  account.net_liquidation = {value:'12345.67',currency:'USD',status:'OBSERVED'};
  return {schema:ACCOUNT_SCHEMA,mode:'live',account,
    positions:{status:'UNVERIFIED',count:null,rows:[]},
    open_orders:{status:'UNVERIFIED',count:null,rows:[]},
    bot:{ownership_state:'UNVERIFIED',runtimes:[]},
    risk:{min_remaining_cushion_pct:30, observed_remaining_cushion_pct:null,
      pending_order_reservations_verified:false,effective_writer_and_fill_commit_verified:false,
      new_exposure_admitted:false}, presentation_only:true,broker_mutation_authority:false};
}
async function sign(doc) {
  const key=await crypto.subtle.importKey('raw',Uint8Array.from(env.PI_LIVE_FINANCE_HMAC_KEY.match(/../g),x=>parseInt(x,16)),
    {name:'HMAC',hash:'SHA-256'},false,['sign']);
  const canonical=canonicalPrivateJson({source:doc.source,snapshot:doc.snapshot});
  const bytes=await crypto.subtle.sign('HMAC',key,new TextEncoder().encode(FINANCE_DOMAIN+canonical));
  return {...doc,mac_hex:Buffer.from(bytes).toString('hex')};
}
async function fixture(when=now, cycle='piobs-20261113231500') {
  return sign({schema:FINANCE_SCHEMA,
    source:{node_id:'cc-pi4',account_sha256:env.PI_LIVE_EXPECTED_ACCOUNT_SHA256,
      observed_at_utc:new Date(when).toISOString(),cycle_id:cycle,
      transport:'authenticated_private_pi_delivery',account_scope_verified:true},
    snapshot:snapshot()});
}
class Storage {
  constructor() {this.map=new Map();}
  async get(key) {return this.map.get(key);}
  async put(key, value) {this.map.set(key, value);}
  async transaction(cb) {return cb(this);}
}

test('signed exact Pi account money is visible without a broker permission',async()=>{
  const doc=await fixture();
  await verifyPrivateFinancial(doc,env,now);
  const s=new Storage();
  const first=await storePrivateFinancial(s,doc,env,now);
  assert.equal(first.accepted,true);
  const read=await readPrivateFinancial(s,env,now);
  assert.equal(read.status,'VERIFIED_FRESH');
  assert.equal(read.account.net_liquidation.value,'12345.67');
  assert.equal(read.account.cash.status,'UNVERIFIED');
  assert.equal(read.risk.pending_order_reservations_verified,false);
  assert.equal(read.broker_mutation_authority,false);
  assert.equal('mac_hex' in read,false);
  assert.equal('account_sha256' in read.source,false);
  assert.equal((await storePrivateFinancial(s,doc,env,now)).accepted,false);
});

test('stale data and future data are denied, not relabeled as zero',async()=>{
  for(const ms of [now-421000,now+61000]) {
    await assert.rejects(verifyPrivateFinancial(await fixture(ms),env,now),/stale/);
  }
  const s=new Storage();
  await storePrivateFinancial(s,await fixture(),env,now);
  await assert.rejects(readPrivateFinancial(s,env,now+421000),/stale/);
});

test('unconfigured trust cannot ingest or release money',async()=>{
  const doc=await fixture();
  await assert.rejects(verifyPrivateFinancial(doc,{},now),/trust_unconfigured/);
  await assert.rejects(readPrivateFinancial(new Storage(),env,now),/not_installed/);
});

test('tampering with a signed money value fails HMAC, even when shape remains valid',async()=>{
  const doc=await fixture();
  doc.snapshot.account.net_liquidation.value='999999.00';
  await assert.rejects(verifyPrivateFinancial(doc,env,now),/mac_invalid/);
});

test('wrong account scope and forged broker execution authority cannot be signed as finance',async()=>{
  for(const mutate of [
    d=>{d.source.account_sha256='ff'.repeat(32);},
    d=>{d.source.node_id='other-node';},
    d=>{d.source.account_scope_verified=false;},
    d=>{d.snapshot.broker_mutation_authority=true;},
    d=>{d.snapshot.risk.new_exposure_admitted=true;},
    d=>{d.snapshot.risk.pending_order_reservations_verified=true;},
    d=>{d.snapshot.risk.min_remaining_cushion_pct=20;},
    d=>{d.snapshot.mode='paper';},
    d=>{d.snapshot.positions={status:'OBSERVED',count:0,rows:[]};d.snapshot.positions.count=1;},
    d=>{d.snapshot.account.cash={value:'0',currency:'USD',status:'UNVERIFIED'};},
    d=>{d.snapshot.account.net_liquidation.value='NaN';},
    d=>{d.snapshot.account.extra_money=unknown();},
  ]){
    const d=await fixture(); mutate(d);
    // Sign the mutated envelope using the *test-only* key to ensure shape
    // validation, not just a mismatched MAC, rejects false producer assertions.
    const forged=await sign(d);
    await assert.rejects(verifyPrivateFinancial(forged,env,now));
  }
});

test('monotonic writes and conflicting same-cycle money are rejected',async()=>{
  const s=new Storage();
  const first=await fixture(now-120000,'piobs-first');
  await storePrivateFinancial(s,first,env,now);
  await assert.rejects(storePrivateFinancial(s,await fixture(now-180000,'piobs-older'),env,now),/replay/);
  const conflict=await fixture(now-120000,'piobs-different');
  await assert.rejects(storePrivateFinancial(s,conflict,env,now),/conflict/);
  const newer=await fixture(now,'piobs-newer');
  await storePrivateFinancial(s,newer,env,now);
  assert.equal((await readPrivateFinancial(s,env,now)).source.cycle_id,'piobs-newer');
});

test('corrupted durable predecessor cannot be silently reset',async()=>{
  const s=new Storage();
  await storePrivateFinancial(s,await fixture(now-120000,'piobs-first'),env,now);
  const old=await s.get('pi_financial_latest');
  old.envelope.snapshot.account.net_liquidation.value='9';
  await assert.rejects(storePrivateFinancial(s,await fixture(now,'piobs-newer'),env,now),/mac_invalid/);
});

test('Python signed envelope canonical JSON shape has sorted ASCII keys',()=>{
  assert.equal(canonicalPrivateJson({b:[{z:'A',a:1}],a:false}),'{"a":false,"b":[{"a":1,"z":"A"}]}');
  assert.throws(()=>canonicalPrivateJson({a:Infinity}),/shape_invalid/);
});

import { requireFinancePublisherAdmission, requireFinanceServiceClaims } from '../cloudflare/operator-console/src/pi_live_financial_private.js';

test('finance route defaults off even if HMAC trust exists',()=>{
  assert.throws(()=>requireFinancePublisherAdmission(env),/not_admitted/);
  const configured={...env,PI_LIVE_FINANCE_INGEST_ENABLED:'1',
    PI_LIVE_FINANCE_ORIGIN_ADMITTED:'1',
    PI_LIVE_FINANCE_ACCESS_AUD:'a'.repeat(32),
    PI_LIVE_FINANCE_SERVICE_CLIENT_ID:'e'.repeat(40)+'.access'};
  assert.doesNotThrow(()=>requireFinancePublisherAdmission(configured));
  assert.throws(()=>requireFinancePublisherAdmission({...configured,PI_LIVE_FINANCE_ORIGIN_ADMITTED:'0'}),/not_admitted/);
  assert.throws(()=>requireFinancePublisherAdmission({...configured,PI_LIVE_FINANCE_SERVICE_CLIENT_ID:''}),/unconfigured/);
});

test('only the cryptographically verified pinned service Access principal can publish',()=>{
  const expectedIssuer='https://example.cloudflareaccess.com';
  const config={PI_LIVE_FINANCE_ACCESS_AUD:'f'.repeat(32),PI_LIVE_FINANCE_SERVICE_CLIENT_ID:'abcde'.repeat(8)+'.access'};
  const signed={type:'app',iss:expectedIssuer,aud:[config.PI_LIVE_FINANCE_ACCESS_AUD],
    common_name:config.PI_LIVE_FINANCE_SERVICE_CLIENT_ID,sub:''};
  assert.equal(requireFinanceServiceClaims(signed,config,expectedIssuer),true);
  for(const patch of [{email:'person@example.org'},{sub:'person'},{type:'org'},
    {aud:['g'.repeat(32)]},{common_name:'other.access'},{iss:'https://attacker.example'}]) {
    assert.throws(()=>requireFinanceServiceClaims({...signed,...patch},config,expectedIssuer),/principal_rejected/);
  }
});

test('a count-only / BASE-only cycle with no denominated money cannot claim live finance',async()=>{
  const doc=await fixture();
  doc.snapshot.account.net_liquidation={value:null,currency:null,status:'UNVERIFIED'};
  const signed=await sign(doc);
  await assert.rejects(verifyPrivateFinancial(signed,env,now),/no_observed_money/);
});

test('account rows cannot claim strategy or external ownership without ledger reconciliation',async()=>{
  const row={symbol:'AMAT',local_symbol:'AMAT',security_type:'STK',contract_id:123,
    quantity:'1',avg_cost:'200.00',market_value:'210.00',unrealized_pnl:'10.00',
    currency:'USD',ownership:'UNVERIFIED'};
  const doc=await fixture();
  doc.snapshot.positions={status:'OBSERVED',count:1,rows:[row]};
  assert.doesNotReject(verifyPrivateFinancial(await sign(doc),env,now));
  for(const ownership of ['BOT_OWNED','EXTERNAL']) {
    doc.snapshot.positions.rows[0].ownership=ownership;
    await assert.rejects(verifyPrivateFinancial(await sign(doc),env,now),/row_identity/);
  }
  doc.snapshot.positions.rows[0].ownership='UNVERIFIED';
  doc.snapshot.bot.ownership_state='BOT_OWNED';
  await assert.rejects(verifyPrivateFinancial(await sign(doc),env,now),/bot_authority/);
});