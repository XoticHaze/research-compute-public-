// Synthetic endpoint integration: run the exact broker fetch()/Durable Object
// modules locally on the public Actions host. No Cloudflare keys, OIDC token,
// deployment rights, PHI, or real private inputs are used or printed.
import assert from 'node:assert/strict';
import { createHash, webcrypto } from 'node:crypto';
import broker, { GrantLedger } from '../cloudflare/reference-release-broker/src/index.js';
import { callerPolicySha256 } from '../cloudflare/reference-release-broker/src/ticket.js';

if (!globalThis.crypto) globalThis.crypto = webcrypto;
const wc = globalThis.crypto.subtle;
const now = Math.floor(Date.now() / 1000);
const harness = '477b76085c06f77fee72b57771225a66545aa43f';
const workflow = 'XoticHaze/research-compute-public-/.github/workflows/secure-compute-harness-v1.yml@' + harness;
const issuer = 'https://token.actions.githubusercontent.com';
const jwks = 'https://token.actions.githubusercontent.com/.well-known/jwks';
const worker = 'sha256:' + 'b'.repeat(64);
const grantId = 'synthetic_grant_0123456789abcdef';
const encode = bytes => Buffer.from(bytes).toString('base64');
const url = bytes => Buffer.from(bytes).toString('base64url');
const canonical = obj => JSON.stringify(Object.fromEntries(Object.entries(obj).sort(([a],[b]) => a.localeCompare(b))));
const sha = bytes => createHash('sha256').update(bytes).digest('hex');

const oidcKey = await wc.generateKey(
  { name: 'RSASSA-PKCS1-v1_5', modulusLength: 2048,
    publicExponent: new Uint8Array([1,0,1]), hash: 'SHA-256' }, true, ['sign','verify']
);
const oidcPublic = await wc.exportKey('jwk', oidcKey.publicKey);
oidcPublic.kid = 'synthetic-oidc-rsa-1';
const brokerKey = await wc.generateKey({ name:'ECDSA', namedCurve:'P-256' }, true, ['sign','verify']);
const privateJwk = await wc.exportKey('jwk', brokerKey.privateKey);
const brokerPublicRaw = new Uint8Array(await wc.exportKey('raw', brokerKey.publicKey));
const brokerId = 'sha256:' + sha(brokerPublicRaw);
const authority = await wc.generateKey({ name:'ECDSA', namedCurve:'P-256' }, true, ['sign','verify']);
const authorityPublicRaw = new Uint8Array(await wc.exportKey('raw', authority.publicKey));
const claims = {
  iss: issuer, aud: 'secure-compute-reference-v1', repository_id: '1416551057',
  repository_owner_id: '152584286', repository_visibility:'public',
  ref: 'refs/heads/main', event_name:'workflow_dispatch',
  job_workflow_ref: workflow, job_workflow_sha: harness,
  run_id: '38628015317', run_attempt:'1', runner_environment:'github-hosted',
  iat: now - 10, nbf: now - 10, exp: now + 300,
};

async function jwt(payload) {
  const a = url(JSON.stringify({alg:'RS256',kid:oidcPublic.kid,typ:'JWT'}));
  const b = url(JSON.stringify(payload));
  const message = a + '.' + b;
  const signature = await wc.sign('RSASSA-PKCS1-v1_5', oidcKey.privateKey,
                                  new TextEncoder().encode(message));
  return message + '.' + url(signature);
}
async function intentFor(jwtClaims, overrides={}) {
  const payload = {
    schema:'reference-release-intent-v1', issuer:'private-authority-v1',
    audience:'independent-release-broker-v1', grant_id:grantId,
    caller_policy_sha256:await callerPolicySha256(jwtClaims),
    harness_sha:harness, broker_key_id:brokerId,
    not_before:now-20, intent_not_after:now+600,
    ...overrides,
  };
  const bytes = new TextEncoder().encode(canonical(payload));
  const sig = new Uint8Array(await wc.sign({name:'ECDSA',hash:'SHA-256'},authority.privateKey,bytes));
  assert.equal(sig.length,64);
  return {payload_b64:encode(bytes),signature_b64:encode(sig),
    signer_key_id:'sha256:'+sha(authorityPublicRaw),signature_format:'ecdsa-p256-sha256-p1363'};
}
function createEnv() {
  const store = new Map();
  const ledger = new GrantLedger({storage:{
    transaction: async callback => callback({
      get: async key => store.get(key), put: async (key,value) => store.set(key,value),
    }),
  }});
  return {
    env: {
      GRANT_LEDGER: {idFromName: name => name, get: () => ledger},
      AUTHORITY_PUBLIC_B64:encode(authorityPublicRaw),
      BROKER_SIGNING_PRIVATE_JWK:JSON.stringify(privateJwk),
      ALLOWED_JOB_WORKFLOW_REF:workflow, ALLOWED_JOB_WORKFLOW_SHA:harness,
      MAX_ADMISSION_SECONDS:'300',MAX_INTENT_SECONDS:'86400',
    },store,
  };
}
globalThis.fetch=async (u) => {
  if (String(u)!==jwks) throw new Error('unexpected_external_network_request');
  return new Response(JSON.stringify({keys:[oidcPublic]}),{status:200,
    headers:{'content-type':'application/json'}});
};
const makeCall = async (env, jwtClaims=claims, intent=null, signedJwt=null) => {
  const request = new Request('https://synthetic.example/v1/release',{
    method:'POST',headers:{authorization:'Bearer '+(signedJwt||await jwt(jwtClaims)),
      'content-type':'application/json'},
    body:JSON.stringify({worker_key_id:worker,intent:intent||await intentFor(claims)}),
  });
  return broker.fetch(request,env);
};
let checked=0;
async function expectFailure(label, env, badClaims, bodyIntent, expectedStatus) {
  const response=await makeCall(env,badClaims,bodyIntent);
  assert.equal(response.status,expectedStatus,'negative failed '+label);
  checked++;
}
const {env,store}=createEnv();
// Positive must test actual broker index.js, JWT/JWKS, authority-signed
// intent, Durable Object single-consume, signed P256 ticket, not helper only.
const health=await broker.fetch(new Request('https://synthetic.example/healthz'),env);
assert.equal(health.status,200);
assert.equal((await health.json()).ok,true);
const keyResp=await broker.fetch(new Request('https://synthetic.example/v1/public-key'),env);
assert.equal(keyResp.status,200,'public-key endpoint must recognize standard private JWK');
const publicKey=await keyResp.json();
assert.equal(publicKey.key_id,brokerId);
assert.equal(publicKey.public_b64,encode(brokerPublicRaw));
const positive=await makeCall(env);
assert.equal(positive.status,200,'signed-release endpoint must allow exact one-time identity');
const doc=await positive.json();
assert.equal(doc.ok,true);
assert.equal(doc.ticket.signer_key_id,brokerId);
const ticketPayload=Buffer.from(doc.ticket.payload_b64,'base64');
assert.equal(doc.ticket.signature_format,'ecdsa-p256-sha256-p1363');
assert.equal(await wc.verify({name:'ECDSA',hash:'SHA-256'},brokerKey.publicKey,
  Buffer.from(doc.ticket.signature_b64,'base64'),ticketPayload),true);
const payload=JSON.parse(ticketPayload.toString('utf8'));
assert.equal(payload.run_id,claims.run_id);
assert.equal(payload.worker_key_id,worker);
assert.equal(payload.harness_sha,harness);
assert.equal(payload.grant_id,grantId);
assert.equal(store.size,1);
console.log('BROKER_ACTUAL_ENDPOINT_SYNTHETIC_SIGNED_RELEASE_PASS=1');
const again=await makeCall(env);
assert.equal(again.status,409,'signed intent must be one time');
checked++;
// Each negative starts with a fresh Durable Object instance and exact signed
// JWT whenever changing claims, so failures are policy/crypto not consumed.
// Never print request tokens or secrets on error.
{
  const bad={...claims,repository_id:'1358005162'};
  await expectFailure('legacy_repo_oidc_replay',createEnv().env,bad,null,400);
}
{
  const bad={...claims,job_workflow_sha:'0'.repeat(40)};
  await expectFailure('unpinned_harness',createEnv().env,bad,null,401);
}
{
  const bad={...claims,runner_environment:'self-hosted'};
  await expectFailure('untrusted_runner',createEnv().env,bad,null,401);
}
{
  const bad={...claims,repository_visibility:'private'};
  await expectFailure('nonpublic_repo',createEnv().env,bad,null,401);
}
{
  const bad={...claims,exp:now-60};
  await expectFailure('expired_oidc',createEnv().env,bad,null,401);
}
{
  const changed=await intentFor(claims,{caller_policy_sha256:'e'.repeat(64)});
  await expectFailure('different_independent_authority_policy',createEnv().env,claims,changed,400);
}
{
  const changed=await intentFor(claims,{broker_key_id:'sha256:'+'e'.repeat(64)});
  await expectFailure('different_broker_key_binding',createEnv().env,claims,changed,400);
}
{
  const changed=await intentFor(claims,{intent_not_after:now-1});
  await expectFailure('stale_signed_intent',createEnv().env,claims,changed,400);
}
{
  const wrapper=await intentFor(claims);
  wrapper.signature_b64=encode(Buffer.alloc(64));
  await expectFailure('tampered_private_intent_signature',createEnv().env,claims,wrapper,400);
}
{
  const {env:broken}=createEnv();
  delete broken.AUTHORITY_PUBLIC_B64;
  await expectFailure('missing_private_authority_verifier',broken,claims,null,503);
}
{
  const {env:broken}=createEnv();
  delete broken.BROKER_SIGNING_PRIVATE_JWK;
  await expectFailure('missing_live_broker_signer',broken,claims,null,503);
}
assert.equal(checked,12);
console.log('BROKER_ACTUAL_ENDPOINT_FAIL_CLOSED_NEGATIVES_PASS='+checked);
console.log('BROKER_CLOUD_TEST_ENV_SYNTHETIC_ONLY=1');
