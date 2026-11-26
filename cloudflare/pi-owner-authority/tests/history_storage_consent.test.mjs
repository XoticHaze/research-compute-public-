import test from 'node:test';
import assert from 'node:assert/strict';
import { webcrypto } from 'node:crypto';
import {
  validatePiHistoryStorageConsent, canonicalPiJson, PiOwnerApprovalState,
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
