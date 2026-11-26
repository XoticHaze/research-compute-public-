import test from 'node:test';
import assert from 'node:assert/strict';
import { webcrypto } from 'node:crypto';
import ownerWorker from '../src/index.js';
import {
  validatePiHistoryStorageConsent, readPiStorageConsentReceipt,
  canonicalPiJson, PiOwnerApprovalState,
} from '../src/pi_owner_approval.js';

// Offline contract tests. No Cloudflare account, token, Git fetch or private key.
globalThis.crypto ??= webcrypto;
const HELPER='d83c712b657a2e1b40c1a829ced48ab49de4da8f';
function sample(now=Date.now()){
  const req={
    schema:'commandcenter.pi.history_storage_request.v1', node_id:'cc-pi4',
    request_id:'history-consent-test-20261126',
    action:'pi.storage.maintenance_consent.apply',
    expected_release:'rf20bfd283e35', helper_git_blob:HELPER,
    scope:'LOSSLESS_IDENTICAL_27A_27B_ONLY',
    created_at:new Date(now-10000).toISOString(),
    expires_at:new Date(now+10*60000).toISOString(),
  };
  const grant={
    schema:'commandcenter.pi.history_storage_grant.v1', node_id:'cc-pi4',
    request_id:req.request_id,action:req.action,created_at:req.created_at,
    expected_release:req.expected_release,
    helper_git_blob:req.helper_git_blob, scope:req.scope,expires_at:req.expires_at,
  };
  return [req,grant];
}
test('fixed history grant and exact request match',async()=>{
  const [req,grant]=sample();
  const ok=await validatePiHistoryStorageConsent(grant,req);
  assert.equal(ok.request_id,req.request_id);
  assert.match(ok.approval_hash,/^[0-9a-f]{64}$/);
  assert.ok(canonicalPiJson(grant).endsWith('\n'));
});
test('all cross-scope and arbitrary execution fields fail closed',async()=>{
  for(const [side,key,value] of [
    ['req','node_id','pve7'],['req','action','pi.exec'],
    ['req','scope','ALL_FILES'],['req','helper_git_blob','a'.repeat(40)],
    ['req','path','/etc/passwd'],['req','command','docker prune'],
    ['grant','scope','ARBITRARY'],['grant','request_id','other-id'],
    ['grant','source_sha','a'.repeat(40)],
  ]){
    const [req,grant]=sample();
    (side==='req'?req:grant)[key]=value;
    await assert.rejects(validatePiHistoryStorageConsent(grant,req),Error);
  }
});
test('expiry, future and overlong windows fail closed',async()=>{
  const now=Date.now();
  for(const overrides of [
    {created_at:new Date(now+3*60000).toISOString()},
    {expires_at:new Date(now-5000).toISOString()},
    {expires_at:new Date(now+2*3600000).toISOString()},
    {expires_at:'not-a-time'},
  ]){
    const [req,grant]=sample(now);
    Object.assign(req,overrides);
    grant.expires_at=req.expires_at;
    await assert.rejects(validatePiHistoryStorageConsent(grant,req,now),Error);
  }
});
test('history signer defaults disabled, cannot be activated by Git body',async()=>{
  const state=new PiOwnerApprovalState({
    storage:{get:async()=>null,transaction:async()=>{throw Error('unexpected')}}
  },{PI_OWNER_SIGNER_ENABLED:'1',PI_OWNER_QUEUE_GITHUB_TOKEN:'not-a-real-secret',
    PI_OWNER_SIGNER_ALLOWED_EMAILS:'owner@example.invalid'});
  const [req,approval]=sample();
  const answer=await state.fetch(new Request('https://pi-owner.internal/sign',{
    method:'POST',headers:{'content-type':'application/json'},
    body:JSON.stringify({
      kind:'history_storage',request:req,approval,
      approve_exact_storage_consent:true,
      operator:{email:'owner@example.invalid',sub:'cf-access-authenticated:owner@example.invalid'},
    }),
  }));
  assert.equal(answer.status,403);
  const result=await answer.json();
  assert.equal(result.error,'pi_owner_protected_activation_incomplete');
});
test('root_release and rejoin signatures cannot masquerade as history storage',async()=>{
  const [req,grant]=sample();
  for(const mutation of [
    {schema:'commandcenter.pi.release_request_approval.v1'},
    {schema:'commandcenter.pi.bot_rejoin_approval.v1'},
    {request_id:'unrelated'},
  ]){
    await assert.rejects(validatePiHistoryStorageConsent({...grant,...mutation},req),Error);
  }
});

test('owner-signed revocation is distinct and cannot authorize application',async()=>{
  const [req,grant]=sample();
  req.action='pi.storage.maintenance_consent.revoke';
  grant.action=req.action;
  const authorized=await validatePiHistoryStorageConsent(grant,req);
  assert.equal(authorized.request_id,req.request_id);
  const changed={...req,action:'pi.storage.maintenance_consent.apply'};
  await assert.rejects(validatePiHistoryStorageConsent(grant,changed),Error);
  const changedGrant={...grant,action:'pi.storage.maintenance_consent.apply'};
  await assert.rejects(validatePiHistoryStorageConsent(changedGrant,req),Error);
});

test('real Ed25519 domain-separated signature rejects sibling domains and action drift',async()=>{
  const [req,grant]=sample();
  await validatePiHistoryStorageConsent(grant,req);
  const keys=await crypto.subtle.generateKey('Ed25519',false,['sign','verify']);
  const encoder=new TextEncoder();
  const storageDomain='commandcenter.pi.history_storage_approval.v1\u0000';
  const rootReleaseDomain='commandcenter.pi.release_request_approval.v1\u0000';
  const storageMessage=encoder.encode(storageDomain+canonicalPiJson(grant));
  const signature=await crypto.subtle.sign('Ed25519',keys.privateKey,storageMessage);
  assert.equal(new Uint8Array(signature).length,64);
  assert.equal(await crypto.subtle.verify('Ed25519',keys.publicKey,signature,storageMessage),true);
  assert.equal(await crypto.subtle.verify('Ed25519',keys.publicKey,signature,
    encoder.encode(rootReleaseDomain+canonicalPiJson(grant))),false);
  const revoked={...grant,action:'pi.storage.maintenance_consent.revoke'};
  assert.equal(await crypto.subtle.verify('Ed25519',keys.publicKey,signature,
    encoder.encode(storageDomain+canonicalPiJson(revoked))),false);
});

test('root consent receipt projection rejects scope, hash and mutation drift',async()=>{
  const id='ccpi-history-receipt-fixture';
  const pristine={
    schema:'commandcenter.pi.history_storage_consent_result.v1',
    node_id:'cc-pi4',request_id:id,
    action:'pi.storage.maintenance_consent.apply',
    release_id:'rf20bfd283e35',helper_git_blob:HELPER,
    scope:'LOSSLESS_IDENTICAL_27A_27B_ONLY',
    expires_at:'2026-11-26T15:00:00+00:00',
    status:'passed',code:'CONSENT_ROOT_READBACK_VERIFIED',
    request_sha256:'a'.repeat(64),signed_grant_sha256:'b'.repeat(64),
    read_only:false,broker_mutation_attempted:false,
    gateway_mutation_attempted:false,unique_content_deleted:false,
    replay_allowed:false,started_at:'2026-11-26T14:10:00+00:00',
    finished_at:'2026-11-26T14:10:01+00:00',
  };
  const original=globalThis.fetch;
  let receipt=pristine;
  globalThis.fetch=async()=>new Response(JSON.stringify({
    sha:'c'.repeat(40),encoding:'base64',
    content:Buffer.from(JSON.stringify(receipt)).toString('base64'),
    size:Buffer.byteLength(JSON.stringify(receipt)),
  }),{status:200,headers:{'content-type':'application/json'}});
  try {
    const env={PI_OWNER_QUEUE_GITHUB_TOKEN:'x'.repeat(32)};
    const projected=await readPiStorageConsentReceipt(env,id);
    assert.equal(projected.status,'passed');
    assert.equal(projected.root_receipt_verified,true);
    assert.equal(projected.maintenance_batch_verified,false);
    for(const modification of [
      {scope:'ALL_FILES'},{helper_git_blob:'0'.repeat(40)},
      {request_sha256:null},{signed_grant_sha256:null},
      {status:'passed',code:'UNAUTHORIZED_ACTION'},
      {broker_mutation_attempted:true},{gateway_mutation_attempted:true},
      {unique_content_deleted:true},{replay_allowed:true},
      {read_only:true},{release_id:'other'},
    ]){
      receipt={...pristine,...modification};
      await assert.rejects(readPiStorageConsentReceipt(env,id),
        /pi_owner_history_storage_receipt_identity_invalid/);
    }
  } finally {
    globalThis.fetch=original;
  }
});

test('owner cannot sign a hand-edited storage request not matching staged CC proposal',async()=>{
  const [staged]=sample();
  const changed={...staged,request_id:'history-consent-other-20261126'};
  const raw=canonicalPiJson(staged);
  const prior=globalThis.fetch;
  let signerCalled=false;
  globalThis.fetch=async url=>{
    assert.match(String(url),/storage-consent-proposal\\.json/);
    return new Response(JSON.stringify({
      sha:'a'.repeat(40), encoding:'base64',
      content:Buffer.from(raw).toString('base64'), size:Buffer.byteLength(raw),
    }),{status:200});
  };
  const env={
    PI_OWNER_ACCESS_AUD:'owner-aud-test',
    PI_OWNER_SIGNER_ALLOWED_EMAILS:'owner@example.invalid',
    PI_OWNER_SIGNER_ENABLED:'1',PI_OWNER_HISTORY_STORAGE_ENABLED:'1',
    PI_OWNER_QUEUE_GITHUB_TOKEN:'x'.repeat(32),
    PI_OWNER_APPROVER:{get:()=>{signerCalled=true;throw Error('signer must not run');}},
  };
  const ctx={access:{aud:'owner-aud-test',getIdentity:async()=>({email:'owner@example.invalid'})}};
  try{
    const request=new Request('https://owner.test/api/approve-storage',{
      method:'POST',headers:{
        origin:'https://owner.test','content-type':'application/json',
        'sec-fetch-site':'same-origin',
      },body:JSON.stringify({
        request:changed,approve_exact_storage_consent:true,
      }),
    });
    const answer=await ownerWorker.fetch(request,env,ctx);
    assert.equal(answer.status,403);
    assert.deepEqual(await answer.json(),{error:'pi_owner_history_storage_proposal_mismatch'});
    assert.equal(signerCalled,false);
  }finally{
    globalThis.fetch=prior;
  }
});
