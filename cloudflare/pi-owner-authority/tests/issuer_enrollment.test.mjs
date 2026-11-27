import {test} from 'node:test';
import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
import {PiOwnerApprovalState} from '../src/pi_owner_approval.js';
import worker from '../src/index.js';
globalThis.crypto ||= webcrypto;
const keys=await crypto.subtle.generateKey('Ed25519',true,['sign','verify']);
const issuer=await crypto.subtle.generateKey('Ed25519',true,['sign','verify']);
const other=await crypto.subtle.generateKey('Ed25519',true,['sign','verify']);
const identity=async key=>{const der=Buffer.from(await crypto.subtle.exportKey('spki',key));return {spki_b64:der.toString('base64'),sha256:Buffer.from(await crypto.subtle.digest('SHA-256',der)).toString('hex')}};
const root=await identity(keys.publicKey),pub=await identity(issuer.publicKey),alt=await identity(other.publicKey);
const email='owner@example.invalid',operator={email,sub:'cf-access-authenticated:'+email},origin='https://synthetic.invalid';
function fixture(extra={}){
  const rows=new Map([['pi_owner_key_v1',{public_key_sha256:root.sha256,private_pkcs8_b64:Buffer.from([]).toString('base64')}],['pi_owner_enrollment_v1',{key_sha256:root.sha256}]]);
  let tail=Promise.resolve();
  const storage={get:async k=>rows.get(k),put:async(k,v)=>rows.set(k,v),
    transaction:fn=>{const work=tail.then(()=>fn(storage));tail=work.catch(()=>{});return work;}};
  const env={PI_OWNER_SIGNER_ALLOWED_EMAILS:email,PI_OWNER_ACCESS_AUD:'fixture-aud',PI_OWNER_ENROLLED_PUB_SHA256:root.sha256,
    PI_OWNER_SIGNER_ENABLED:'1',PI_OWNER_NORMAL_RELEASE_ENABLED:'1',PI_OWNER_SCHEDULED_ROOT_ENABLED:'1',
    PI_OWNER_ISSUER_OWNER_ENROLL_ENABLED:'1',PI_OWNER_QUEUE_GITHUB_TOKEN:'synthetic-token-for-unit-test-only',...extra};
  const instance=new PiOwnerApprovalState({storage},env);
  env.PI_OWNER_APPROVER={idFromName:id=>id,get:()=>instance};
  const ctx={access:{aud:'fixture-aud',getIdentity:async()=>({email})}};
  const call=(route,doc,auth=ctx,requestOrigin=origin)=>worker.fetch(new Request(origin+'/api/'+route,{method:'POST',headers:{origin:requestOrigin,'content-type':'application/json'},body:JSON.stringify(doc)}),env,auth);
  return {rows,env,instance,ctx,call};
}
const admission={...pub,confirm_independent_custody:true};
const state='pi_owner_independent_release_issuer_v1';
test('only direct authorized owner can admit a distinct issuer, and explicit revocation is required before replacement',async()=>{
  const f=fixture();
  assert.equal((await f.call('admit-issuer',admission,{})).status,403);
  assert.equal((await f.call('admit-issuer',admission,f.ctx,'https://wrong.invalid')).status,403);
  assert.equal((await f.call('admit-issuer',{...root,confirm_independent_custody:true})).status,403);
  assert.equal((await f.call('admit-issuer',{...admission,sha256:'0'.repeat(64)})).status,403);
  assert.equal((await f.call('admit-issuer',{...admission,confirm_independent_custody:false})).status,403);
  assert.equal((await f.call('admit-issuer',admission)).status,200);
  const first=f.rows.get(state);assert.equal(first.revision,1);assert.equal(first.sha256,pub.sha256);
  assert.equal((await f.call('admit-issuer',admission)).status,200);assert.deepEqual(f.rows.get(state),first);
  assert.equal((await f.call('admit-issuer',{...alt,confirm_independent_custody:true})).status,403);
  assert.equal((await f.call('revoke-issuer',{sha256:alt.sha256,confirm_revoke:true})).status,403);
  assert.equal((await f.call('revoke-issuer',{sha256:pub.sha256,confirm_revoke:true})).status,200);
  assert.equal(f.rows.get(state).active,false);assert.equal(f.rows.get(state).revision,2);
  assert.equal((await f.call('admit-issuer',{...alt,confirm_independent_custody:true})).status,200);
  assert.equal(f.rows.get(state).revision,3);assert.equal(f.rows.get(state).sha256,alt.sha256);
});
test('static bootstrap, disabled enrollment, static pins and direct unauthenticated DO requests cannot mutate admission',async()=>{
  for(const env of [{PI_OWNER_ISSUER_OWNER_ENROLL_ENABLED:'0'},{PI_OWNER_SCHEDULED_ROOT_PERMIT:'{}'},{PI_OWNER_RELEASE_ISSUER_SPKI_B64:pub.spki_b64,PI_OWNER_RELEASE_ISSUER_SHA256:pub.sha256}]) {
    const f=fixture(env);
    assert.equal((await f.call('admit-issuer',admission)).status,403);assert.equal(f.rows.has(state),false);
  }
  const f=fixture();
  const res=await f.instance.fetch(new Request('https://internal.invalid/admit-issuer',{method:'POST',body:JSON.stringify(admission)}));
  assert.equal(res.status,403);assert.equal(f.rows.has(state),false);
});
test('enrolled issuer drives scheduled grants; revoked or wrong issuer cannot issue a subsequent grant',async()=>{
  const f=fixture();
  f.rows.get('pi_owner_key_v1').private_pkcs8_b64=Buffer.from(await crypto.subtle.exportKey('pkcs8',keys.privateKey)).toString('base64');
  const now=Date.now(),iso=t=>new Date(t).toISOString().replace(/\.\d{3}Z$/,'Z');
  async function grant(n){
    const digest=n.repeat(64),rid='ccpi2-'+digest+'-'+n.repeat(16);
    const request={schema:'commandcenter.pi.release_request.v1',node_id:'cc-pi4',action:'pi.release.apply',source_repo:'XoticHaze/CommandCenter',source_sha:'a'.repeat(40),expected_release:'r'+'b'.repeat(12),request_id:rid,created_at:iso(now-1000),expires_at:iso(now+300000)};
    const approval={schema:'commandcenter.pi.release_request_approval.v1',request_id:rid,source_sha:request.source_sha,expected_release:request.expected_release,expires_at:request.expires_at};
    const permit={schema:'commandcenter.pi.scheduled_root_permit.v2',permit_id:n.repeat(32),request_id:rid,manifest_sha256:digest,source_sha:request.source_sha,expected_release:request.expected_release,not_before:iso(now-2000),expires_at:iso(now+300000)};
    const canonical=JSON.stringify(Object.fromEntries(Object.entries(permit).sort(([a],[b])=>a<b?-1:a>b?1:0)))+'\n';
    const signature_b64=Buffer.from(await crypto.subtle.sign('Ed25519',issuer.privateKey,new TextEncoder().encode('commandcenter.pi.independent_release_permit.v1\0'+canonical))).toString('base64');
    return f.instance.fetch(new Request('https://internal.invalid/sign-scheduled-root',{method:'POST',body:JSON.stringify({kind:'root_release',request,approval,permit_envelope:{schema:'commandcenter.pi.independent_release_permit.v1',permit,signature_b64}})}));
  }
  assert.equal((await grant('1')).status,403);
  assert.equal((await f.call('admit-issuer',admission)).status,200);
  assert.equal((await grant('1')).status,201);
  assert.equal((await grant('1')).status,200);
  assert.equal((await f.call('revoke-issuer',{sha256:pub.sha256,confirm_revoke:true})).status,200);
  assert.equal((await grant('2')).status,403);
  assert.equal((await f.call('admit-issuer',{...alt,confirm_independent_custody:true})).status,200);
  assert.equal((await grant('2')).status,403);
});
