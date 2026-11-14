/** Contract exercise of the REAL incumbent Worker routes, not just helper functions.
 * Only synthetic portfolio values and ephemeral RSA keys are used.
 * No network, Cloudflare token, Pi node, broker, public Git money or deployment.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { webcrypto, generateKeyPairSync, sign } from 'node:crypto';
import worker, { OperatorState } from '../cloudflare/operator-console/src/index.js';
import { canonicalPrivateJson, FINANCE_DOMAIN } from '../cloudflare/operator-console/src/pi_live_financial_private.js';

globalThis.crypto ||= webcrypto;
const machineAudience = 'f'.repeat(64);
const humanAudience = 'e'.repeat(64);
const machineId = 'a'.repeat(32) + '.access';
const issuer = 'https://fixture.cloudflareaccess.com';
const synthetic = JSON.parse(readFileSync(new URL('./fixtures/pi_live_financial_synthetic_python_v1.json', import.meta.url),'utf8'));
const { publicKey, privateKey } = generateKeyPairSync('rsa',{modulusLength:2048});
const publicJwk = { ...publicKey.export({ format:'jwk' }), kid:'fixture-kid', alg:'RS256', use:'sig' };
const b64url = obj => Buffer.from(JSON.stringify(obj)).toString('base64url');
function signedJwt(fields) {
  const now = Math.floor(Date.now()/1000);
  const unsigned = b64url({alg:'RS256',kid:'fixture-kid',typ:'JWT'})+'.'+
    b64url({iss:issuer,iat:now-10,nbf:now-10,exp:now+1800,...fields});
  return unsigned+'.'+sign('RSA-SHA256',Buffer.from(unsigned),privateKey).toString('base64url');
}
async function signEnvelope(doc) {
  const key=await crypto.subtle.importKey('raw',Buffer.from('ab'.repeat(32),'hex'),
    {name:'HMAC',hash:'SHA-256'},false,['sign']);
  const canonical=canonicalPrivateJson({source:doc.source,snapshot:doc.snapshot});
  const mac=await crypto.subtle.sign('HMAC',key,new TextEncoder().encode(FINANCE_DOMAIN+canonical));
  return {...doc,mac_hex:Buffer.from(mac).toString('hex')};
}
class LocalDurableStorage {
  constructor(){this.state=new Map();}
  async transaction(fn){return fn(this);}
  async get(k){return this.state.get(k);}
  async put(k,v){this.state.set(k,v);}
}
function fixtureEnv() {
  const env={ACCESS_TEAM_DOMAIN:issuer,ACCESS_AUD:humanAudience,
    ACCESS_ALLOWED_EMAILS:'operator@example.org',
    PI_LIVE_FINANCE_INGEST_ENABLED:'1',PI_LIVE_FINANCE_ORIGIN_ADMITTED:'1',
    PI_LIVE_FINANCE_ACCESS_AUD:machineAudience,
    PI_LIVE_FINANCE_SERVICE_CLIENT_ID:machineId,
    PI_LIVE_FINANCE_HMAC_KEY:'ab'.repeat(32),
    PI_LIVE_EXPECTED_ACCOUNT_SHA256:synthetic.source.account_sha256};
  const internal=new OperatorState({storage:new LocalDurableStorage()},env);
  env.OPERATOR_STATE={idFromName:()=> 'global',get:()=> ({fetch: req=>internal.fetch(req)})};
  return env;
}
function request(path,method='GET', body, jwt) {
  const headers={};
  if(body!==undefined)headers['Content-Type']='application/json';
  if(jwt)headers['Cf-Access-Jwt-Assertion']=jwt;
  return new Request('https://mmibkr-operator-console.slenderiq.workers.dev'+path,{method,headers,
    ...(body!==undefined?{body:JSON.stringify(body)}:{})});
}

test('real Worker machine POST and signed-human GET enforce origin, HMAC and freshness',async()=>{
  const originalFetch=globalThis.fetch;
  globalThis.fetch=async url=> {
    if (String(url)!==issuer+'/cdn-cgi/access/certs') throw Error('unexpected network request');
    return new Response(JSON.stringify({keys:[publicJwk]}),{status:200,headers:{'content-type':'application/json'}});
  };
  try {
    const env=fixtureEnv();
    const doc=structuredClone(synthetic);
    doc.source.observed_at_utc=new Date().toISOString();
    doc.source.cycle_id='piobs-'+Date.now();
    const envelope=await signEnvelope(doc);
    const machine=signedJwt({aud:[machineAudience],type:'app',common_name:machineId,sub:''});
    const human=signedJwt({aud:[humanAudience],type:'app',email:'operator@example.org',sub:'operator-test-sub'});
    const hostile=signedJwt({aud:[humanAudience],type:'app',email:'intruder@example.org',sub:'intruder-sub'});

    assert.equal((await worker.fetch(request('/v1/pi-live-financial','POST',envelope),env)).status,403,
      'missing Access service JWT is not authorized even with real HMAC');
    const wrongMachine=signedJwt({aud:[machineAudience],type:'app',common_name:'wrong.access',sub:''});
    assert.equal((await worker.fetch(request('/v1/pi-live-financial','POST',envelope,wrongMachine),env)).status,403);

    const accepted=await worker.fetch(request('/v1/pi-live-financial','POST',envelope,machine),env);
    assert.equal(accepted.status,202,'service-authenticated direct Worker ingest should be 202');
    const acceptedBody=await accepted.json();
    assert.equal(acceptedBody.durable_readback_verified,true);
    assert.equal(acceptedBody.broker_mutation_authority,false);

    const forbidden=await worker.fetch(request('/api/operator/live-account','GET',undefined,hostile),env);
    assert.equal(forbidden.status,403);
    const read=await worker.fetch(request('/api/operator/live-account','GET',undefined,human),env);
    assert.equal(read.status,200);
    const actual=await read.json();
    assert.equal(actual.account.net_liquidation.value,'12000.25');
    assert.equal(actual.account.available_funds.value,'5000.00');
    assert.equal(actual.broker_mutation_authority,false);
    assert.equal(actual.risk.pending_order_reservations_verified,false);
    assert.equal(Object.hasOwn(actual,'mac_hex'),false);
    assert.equal(Object.hasOwn(actual.source,'account_sha256'),false);
    // The dedicated Access-locked Worker must not claim a full V4 app simply
    // because the same financial API is present. Explicit serving approval
    // and actual static assets are separate release gates.
    assert.equal((await worker.fetch(request('/api/operator/live-account','GET',undefined,machine),env)).status,403);
    assert.equal((await worker.fetch(request('/markets','GET',undefined,human),env)).status,404);
    assert.equal((await worker.fetch(request('/portfolio','GET',undefined,human),env)).status,404);
    assert.equal((await worker.fetch(request('/portfolio/positions','GET',undefined,human),env)).status,404);
    env.MMIBKR_FULL_V4_ROUTES_ADMITTED='1';
    assert.equal((await worker.fetch(request('/markets','GET',undefined,human),env)).status,503,
      'a route flag without selected V4 assets must remain unavailable');
    delete env.MMIBKR_FULL_V4_ROUTES_ADMITTED;

    const tampered=structuredClone(envelope);
    tampered.snapshot.account.net_liquidation.value='9999.99';
    assert.equal((await worker.fetch(request('/v1/pi-live-financial','POST',tampered,machine),env)).status,400);
    const again=await worker.fetch(request('/v1/pi-live-financial','POST',envelope,machine),env);
    assert.equal(again.status,202);
    assert.equal((await again.json()).accepted,false);
    // The actual DO sees the same updated binding after a protected release.
    env.PI_LIVE_FINANCE_ORIGIN_ADMITTED='0';
    assert.equal((await worker.fetch(request('/api/operator/live-account','GET',undefined,human),env)).status,503);
  } finally {
    globalThis.fetch=originalFetch;
  }
});