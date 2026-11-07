import test from 'node:test';
import assert from 'node:assert/strict';
import { webcrypto } from 'node:crypto';
import { BrokerSignerVault } from '../cloudflare/reference-release-broker/src/signer_vault.js';
import broker from '../cloudflare/reference-release-broker/src/index.js';

globalThis.crypto = webcrypto;

function storage() {
  const values = new Map();
  return {
    values,
    async get(key) { return values.get(key); },
    async transaction(work) {
      return work({
        async get(key) { return values.get(key); },
        async put(key, value) { values.set(key, value); },
      });
    },
  };
}
const now = () => Math.floor(Date.now() / 1000);
const approved = 'cc809-' + 'a'.repeat(32);
const otherApproval = 'cc809-' + 'b'.repeat(32);
const post = (path, body) => new Request('https://signer-vault'+path, {
  method:'POST', headers:{'content-type':'application/json'},
  body:JSON.stringify(body),
});
function freshVault() {
  const backing = storage();
  return {vault:new BrokerSignerVault({storage:backing}), backing};
}
async function create(vault) {
  return vault.fetch(post('/initial-seal',{approval_id:approved,not_after:now()+3600}));
}
function checkPublic(node) {
  assert.deepEqual(Object.keys(node).sort(),['key_id','public_b64']);
  assert.match(node.key_id, /^sha256:[a-f0-9]{64}$/);
  const raw = Buffer.from(node.public_b64,'base64');
  assert.equal(raw.length,65);
  assert.equal(raw[0],4);
  return raw;
}
test('no key before explicit first-issue, invalid approval fails closed', async () => {
  const {vault,backing}=freshVault();
  const pre=await vault.fetch('https://signer-vault/public-key');
  assert.equal(pre.status,503);
  assert.equal((await vault.fetch(post('/initial-seal',{
    approval_id:'unapproved', not_after:now()+1000,
  }))).status,400);
  assert.equal((await vault.fetch(post('/initial-seal',{
    approval_id:approved, not_after:now()-1,
  }))).status,400);
  assert.equal(backing.values.size,0);
  assert.equal((await vault.fetch('https://signer-vault/private-key')).status,404);
});
test('first issue persists one key; replay returns same ID, changed approval refuses rotation', async () => {
  const {vault,backing}=freshVault();
  const result=await create(vault);
  assert.equal(result.status,200);
  const first=await result.json();
  assert.equal(first.ok,true);
  assert.equal(first.created,true);
  assert.deepEqual(Object.keys(first).sort(),['created','key_id','ok']);
  const publicKey=await (await vault.fetch('https://signer-vault/public-key')).json();
  checkPublic(publicKey);
  assert.equal(first.key_id,publicKey.key_id);
  const replay=await (await create(vault)).json();
  assert.equal(replay.created,false);
  assert.equal(replay.key_id,publicKey.key_id);
  const rotated=await vault.fetch(post('/initial-seal',{
    approval_id:otherApproval,not_after:now()+3600,
  }));
  assert.equal(rotated.status,409);
  assert.equal((await (await vault.fetch('https://signer-vault/public-key')).json()).key_id,
    publicKey.key_id);
  assert.equal(backing.values.size,1);
});
test('fixed claim signing uses vault key without exposing private bytes or signing arbitrary data', async () => {
  const {vault}=freshVault();
  await create(vault);
  const identity=await (await vault.fetch('https://signer-vault/public-key')).json();
  const claims={
    grant_id:'grant_0123456789abcdef',
    run_id:'37629210001',run_attempt:'1',harness_sha:'c'.repeat(40),
    worker_key_id:'sha256:'+'f'.repeat(64),admission_not_after:now()+180,
  };
  const response=await vault.fetch(post('/sign-ticket',{
    expected_key_id:identity.key_id,claims,
  }));
  assert.equal(response.status,200);
  const node=await response.json();
  assert.deepEqual(Object.keys(node).sort(),['ok','ticket']);
  assert.equal(node.ticket.signer_key_id,identity.key_id);
  const raw=checkPublic(identity);
  const publicKey=await crypto.subtle.importKey('raw',raw,
    {name:'ECDSA',namedCurve:'P-256'},false,['verify']);
  const payload=Buffer.from(node.ticket.payload_b64,'base64');
  const signature=Buffer.from(node.ticket.signature_b64,'base64');
  assert.equal(signature.length,64);
  assert.equal(await crypto.subtle.verify({name:'ECDSA',hash:'SHA-256'},
    publicKey, signature, payload),true);
  const body=JSON.stringify(node);
  assert.ok(!body.includes('private_jwk'));
  assert.ok(!body.includes('approval_id'));
  for (const bad of [
    {expected_key_id:'sha256:'+'0'.repeat(64),claims},
    {expected_key_id:identity.key_id,claims:{...claims,authority:'sensitive'}},
    {expected_key_id:identity.key_id,claims:{...claims,admission_not_after:now()+99999}},
  ]) {
    assert.equal((await vault.fetch(post('/sign-ticket',bad))).status,400);
  }
});
test('broker cron is inert without neutral Cloudflare owner approval', async () => {
  const {vault,backing}=freshVault();
  const pair=await crypto.subtle.generateKey(
    {name:'ECDSA',namedCurve:'P-256'},true,['sign','verify']);
  const publicRaw=new Uint8Array(await crypto.subtle.exportKey('raw',pair.publicKey));
  const env={
    BROKER_SIGNER_MODE:'vault-v1',
    BROKER_SIGNER_VAULT:{idFromName:s=>s,get:()=>vault},
    GRANT_LEDGER:{idFromName:s=>s,get:()=>({})},
    AUTHORITY_PUBLIC_B64:Buffer.from(publicRaw).toString('base64'),
    ALLOWED_JOB_WORKFLOW_REF:'XoticHaze/research-compute-public-/.github/workflows/secure-compute-harness-v1.yml@'+'a'.repeat(40),
    ALLOWED_JOB_WORKFLOW_SHA:'a'.repeat(40),
    MAX_ADMISSION_SECONDS:'300',
  };
  await broker.scheduled(null,env);
  assert.equal(backing.values.size,0);
  env.BROKER_FIRST_SEAL_APPROVAL_ID=approved;
  env.BROKER_FIRST_SEAL_APPROVAL_NOT_AFTER=String(now()+3600);
  await broker.scheduled(null,env);
  assert.equal(backing.values.size,1);
  const response=await broker.fetch(new Request('https://example.invalid/v1/public-key'),env);
  assert.equal(response.status,200);
  const publicNode=await response.json();
  checkPublic(publicNode);
  const health=await broker.fetch(new Request('https://example.invalid/healthz'),env);
  assert.equal(health.status,200);
  delete env.BROKER_FIRST_SEAL_APPROVAL_ID;
  await broker.scheduled(null,env);
  assert.equal(backing.values.size,1);
});
