import assert from 'node:assert/strict';
import {test} from 'node:test';
import {webcrypto} from 'node:crypto';
import {PiOwnerApprovalState} from '../src/pi_owner_approval.js';
globalThis.crypto ||= webcrypto;

const now=Date.now(), iso=t=>new Date(t).toISOString().replace(/\.\d{3}Z$/,'Z');
const permit={schema:'commandcenter.pi.scheduled_root_permit.v1',permit_id:'a'.repeat(32),
  source_sha:'b'.repeat(40),expected_release:'r'+'c'.repeat(12),
  not_before:iso(now-60000),expires_at:iso(now+3600000)};
const keys=await crypto.subtle.generateKey('Ed25519',true,['sign','verify']);
const der=new Uint8Array(await crypto.subtle.exportKey('spki',keys.publicKey));
const fingerprint=Buffer.from(await crypto.subtle.digest('SHA-256',der)).toString('hex');
const private_pkcs8_b64=Buffer.from(await crypto.subtle.exportKey('pkcs8',keys.privateKey)).toString('base64');
const env={PI_OWNER_SCHEDULED_ROOT_ENABLED:'1',PI_OWNER_SIGNER_ENABLED:'1',
  PI_OWNER_NORMAL_RELEASE_ENABLED:'1',PI_OWNER_SCHEDULED_ROOT_PERMIT:JSON.stringify(permit),
  PI_OWNER_QUEUE_GITHUB_TOKEN:'synthetic-only-not-a-real-token',PI_OWNER_ENROLLED_PUB_SHA256:fingerprint,
  PI_OWNER_SIGNER_ALLOWED_EMAILS:'owner@example.invalid'};
function fixture(overrides={}, enrolled=true){
  const rows=new Map([['pi_owner_key_v1',{public_key_sha256:fingerprint,private_pkcs8_b64}]]);
  if(enrolled)rows.set('pi_owner_enrollment_v1',{key_sha256:fingerprint});
  let tail=Promise.resolve();
  const storage={get:async k=>rows.get(k),put:async(k,v)=>rows.set(k,v),
    transaction:fn=>{const work=tail.then(()=>fn(storage));tail=work.catch(()=>{});return work;}};
  return {instance:new PiOwnerApprovalState({storage},{...env,...overrides}),rows};
}
function body(id='test-root-123',overrides={}){
  const request={schema:'commandcenter.pi.release_request.v1',action:'pi.release.apply',node_id:'cc-pi4',
    source_repo:'XoticHaze/CommandCenter',source_sha:permit.source_sha,expected_release:permit.expected_release,
    request_id:id,created_at:iso(now-1000),expires_at:iso(now+300000),...overrides};
  const approval={schema:'commandcenter.pi.release_request_approval.v1',request_id:id,
    source_sha:request.source_sha,expected_release:request.expected_release,expires_at:request.expires_at};
  return {kind:'root_release',request,approval};
}
async function invoke(instance,payload=body(),path='/sign-scheduled-root'){
  return instance.fetch(new Request('https://test.invalid'+path,{method:'POST',body:JSON.stringify(payload)}));
}
test('disabled and missing enrollment deny scheduled signing',async()=>{
  assert.equal((await invoke(fixture({PI_OWNER_SCHEDULED_ROOT_ENABLED:'0'}).instance)).status,403);
  assert.equal((await invoke(fixture({},false).instance)).status,403);
  assert.equal((await invoke(fixture({PI_OWNER_ENROLLED_PUB_SHA256:'d'.repeat(64)}).instance)).status,403);
});
test('scope and expiry are exact',async()=>{
  const {instance}=fixture();
  for(const changes of [{source_sha:'d'.repeat(40)},{expected_release:'r'+'d'.repeat(12)},
    {expires_at:'invalid'},{action:'pi.bot.rejoin_existing'},{expires_at:iso(now+7200000)}])
    assert.equal((await invoke(instance,body('test-root-123',changes))).status,403);
});
test('one-use permit, same-ID recovery, actual Ed25519 verification',async()=>{
  const {instance,rows}=fixture();
  const first=await invoke(instance),again=await invoke(instance);
  assert.equal(first.status,201);assert.equal(again.status,200);
  const grant=(await first.json()).signed_grant,recovered=await again.json();
  assert.equal(recovered.recovered,true);assert.deepEqual(recovered.signed_grant,grant);
  const {signature_b64,key_id,...unsigned}=grant;
  const canonical=JSON.stringify(Object.fromEntries(Object.entries(unsigned).sort(([a],[b])=>a<b?-1:a>b?1:0)))+'\n';
  assert.equal(await crypto.subtle.verify('Ed25519',keys.publicKey,Buffer.from(signature_b64,'base64'),
    new TextEncoder().encode('commandcenter.pi.release_request_approval.v1\0'+canonical)),true);
  assert.equal((await invoke(instance,body('test-root-456'))).status,403);
  assert.equal(rows.get('pi_owner_scheduled_permit_v1/'+permit.permit_id).request_id,'test-root-123');
});
test('concurrent IDs cannot issue twice; owner HTTP signer still requires owner',async()=>{
  const {instance,rows}=fixture();
  const responses=await Promise.all([invoke(instance),invoke(instance,body('test-root-456'))]);
  assert.equal(responses.filter(r=>r.status===201).length,1);
  assert.equal([...rows.keys()].filter(k=>k.startsWith('pi_owner_issued_v1/')).length,1);
  assert.equal((await invoke(instance,body(),'/sign')).status,403);
});
