import assert from 'node:assert/strict';
import {test} from 'node:test';
import {webcrypto} from 'node:crypto';
import {PiOwnerApprovalState} from '../src/pi_owner_approval.js';
globalThis.crypto ||= webcrypto;

const now=Date.now(), iso=t=>new Date(t).toISOString().replace(/\.\d{3}Z$/,'Z');
const manifest='d'.repeat(64), rid='ccpi2-'+manifest+'-'+'e'.repeat(16);
const permit={schema:'commandcenter.pi.scheduled_root_permit.v2',permit_id:'a'.repeat(32),request_id:rid,manifest_sha256:manifest,
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
function body(id=rid,overrides={}){
  const request={schema:'commandcenter.pi.release_request.v1',action:'pi.release.apply',node_id:'cc-pi4',
    source_repo:'XoticHaze/CommandCenter',source_sha:permit.source_sha,expected_release:permit.expected_release,
    request_id:id,created_at:iso(now-1000),expires_at:iso(now+300000),...overrides};
  const approval={schema:'commandcenter.pi.release_request_approval.v1',request_id:id,
    source_sha:request.source_sha,expected_release:request.expected_release,expires_at:request.expires_at};
  return {kind:'root_release',request,approval,permit_envelope:null};
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
    assert.equal((await invoke(instance,body(rid,changes))).status,403);
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
  assert.equal((await invoke(instance,body('ccpi2-'+'f'.repeat(64)+'-'+'e'.repeat(16)))).status,403);
  assert.equal(rows.get('pi_owner_scheduled_permit_v1/'+permit.permit_id).request_id,rid);
});
test('concurrent IDs cannot issue twice; owner HTTP signer still requires owner',async()=>{
  const {instance,rows}=fixture();
  const responses=await Promise.all([invoke(instance),invoke(instance,body('ccpi2-'+'f'.repeat(64)+'-'+'e'.repeat(16)))]);
  assert.equal(responses.filter(r=>r.status===201).length,1);
  assert.equal([...rows.keys()].filter(k=>k.startsWith('pi_owner_issued_v1/')).length,1);
  assert.equal((await invoke(instance,body(),'/sign')).status,403);
});

test('queue read includes explicit GitHub client identity and reports only categorical upstream status',async()=>{
  const {readPiRootReleaseReceipt}=await import('../src/pi_owner_approval.js');
  const id='synthetic-root-receipt';
  const receipt={schema:'commandcenter.pi.release_result.v1',node_id:'cc-pi4',
    request_id:id,action:'pi.release.apply',source_sha:'a'.repeat(40),status:'passed'};
  const raw=JSON.stringify(receipt),original=globalThis.fetch;
  const fakeEnv={PI_OWNER_QUEUE_GITHUB_TOKEN:'synthetic-only-not-a-real-token'};
  let status=200,reported=receipt;
  globalThis.fetch=async(url,opts)=>{
    assert.equal(url,'https://api.github.com/repos/XoticHaze/CommandCenter-gate-control/contents/pi-node/release-results/'+id+'.json?ref=pi-node-outbox');
    assert.equal(opts.headers['user-agent'],'commandcenter-pi-owner-authority-v1');
    assert.equal(opts.headers.authorization,'Bearer '+fakeEnv.PI_OWNER_QUEUE_GITHUB_TOKEN);
    assert.equal(opts.redirect,'manual');
    return {status,ok:status===200,json:async()=>({sha:'b'.repeat(40),encoding:'base64',
      content:Buffer.from(JSON.stringify(reported)).toString('base64'),size:Buffer.byteLength(raw)})};
  };
  try {
    assert.equal((await readPiRootReleaseReceipt(fakeEnv,id)).root_receipt_verified,true);
    status=403;await assert.rejects(readPiRootReleaseReceipt(fakeEnv,id),/pi_owner_root_release_receipt_http_403/);
    status=404;assert.equal((await readPiRootReleaseReceipt(fakeEnv,id)).status,'PENDING');
    status=200;reported={...receipt,request_id:'wrong-id'};
    await assert.rejects(readPiRootReleaseReceipt(fakeEnv,id),/pi_owner_root_release_receipt_identity_invalid/);
  } finally {globalThis.fetch=original;}
});

test('persistent independently signed permits: two fresh IDs, no Worker reconfiguration, forged and replayed grants denied',async()=>{
  const issuer=await crypto.subtle.generateKey('Ed25519',true,['sign','verify']);
  const spki=Buffer.from(await crypto.subtle.exportKey('spki',issuer.publicKey));
  const fp=Buffer.from(await crypto.subtle.digest('SHA-256',spki)).toString('hex');
  const {instance,rows}=fixture({PI_OWNER_SCHEDULED_ROOT_PERMIT:undefined,
    PI_OWNER_RELEASE_ISSUER_SPKI_B64:spki.toString('base64'),PI_OWNER_RELEASE_ISSUER_SHA256:fp});
  const make=async(p)=>{
    const canonical=JSON.stringify(Object.fromEntries(Object.entries(p).sort(([a],[b])=>a<b?-1:a>b?1:0)))+'\n';
    const sig=await crypto.subtle.sign('Ed25519',issuer.privateKey,new TextEncoder().encode('commandcenter.pi.independent_release_permit.v1\0'+canonical));
    return {schema:'commandcenter.pi.independent_release_permit.v1',permit:p,signature_b64:Buffer.from(sig).toString('base64')};
  };
  const a=body();a.permit_envelope=await make(permit);
  const forged=structuredClone(a);forged.permit_envelope.signature_b64=Buffer.alloc(64).toString('base64');
  assert.equal((await invoke(instance,forged)).status,403);
  const unsigned=body();assert.equal((await invoke(instance,unsigned)).status,403);
  assert.equal((await invoke(instance,a)).status,201);
  assert.equal((await invoke(instance,a)).status,200);
  const next={...permit,permit_id:'1'.repeat(32),request_id:'ccpi2-'+'f'.repeat(64)+'-'+'2'.repeat(16),
    manifest_sha256:'f'.repeat(64),source_sha:'3'.repeat(40),expected_release:'r'+'4'.repeat(12)};
  const b=body(next.request_id,{source_sha:next.source_sha,expected_release:next.expected_release});
  b.permit_envelope=await make(next);
  const reused=structuredClone(b);reused.permit_envelope=await make({...next,permit_id:permit.permit_id});
  assert.equal((await invoke(instance,reused)).status,403);
  assert.equal((await invoke(instance,b)).status,201);
  assert.equal([...rows.keys()].filter(k=>k.startsWith('pi_owner_issued_v1/')).length,2);
  const sameRoot=fixture({PI_OWNER_SCHEDULED_ROOT_PERMIT:undefined,
    PI_OWNER_RELEASE_ISSUER_SPKI_B64:Buffer.from(der).toString('base64'),PI_OWNER_RELEASE_ISSUER_SHA256:fingerprint});
  assert.equal((await invoke(sameRoot.instance,a)).status,403);
});

test('dispatcher recovers only fresh exact reviewed successor of a terminal failure',async()=>{
  const {publishPiRootReleaseGrant}=await import('../src/pi_owner_approval.js');
  const request=body().request;
  const previous={...request,request_id:'ccpi2-'+'a'.repeat(64)+'-'+'b'.repeat(16),
    source_sha:'a'.repeat(40),created_at:iso(now-900000),expires_at:iso(now-180000)};
  const base={schema:'commandcenter.pi.release_result.v1',node_id:'cc-pi4',action:request.action,
    request_id:previous.request_id,source_sha:previous.source_sha,predecessor:previous.expected_release,
    status:'failed',replay_allowed:false,message:'fixed command failed'};
  const original=globalThis.fetch;
  let receipt=base,writes=[];
  const file=doc=>({sha:'b'.repeat(40),encoding:'base64',content:Buffer.from(JSON.stringify(doc)).toString('base64'),size:Buffer.byteLength(JSON.stringify(doc))});
  globalThis.fetch=async(url,opts)=>{
    if(opts.method==='PUT'){writes.push(url);return {ok:true,status:200,json:async()=>({content:{sha:'c'.repeat(40)}})};}
    if(url.includes('/release-results/'))return {ok:true,status:200,json:async()=>file(receipt)};
    if(url.includes('/release-request.json'))return {ok:true,status:200,json:async()=>file(previous)};
    if(url.includes('/release-signed-approval.json'))return {ok:true,status:200,json:async()=>file(previous)};
    throw Error('unexpected synthetic URL');
  };
  try {
    for(const value of [{...base,status:'indeterminate'},{...base,replay_allowed:true},
        {...base,predecessor:'r'+'f'.repeat(12)},{...base,source_sha:'f'.repeat(40)}]){
      receipt=value;await assert.rejects(publishPiRootReleaseGrant(env,request,{request_id:request.request_id},true));
      assert.equal(writes.length,0);
    }
    receipt=base;
    await assert.rejects(publishPiRootReleaseGrant(env,{...request,expected_release:'r'+'f'.repeat(12)},{request_id:request.request_id},true));
    assert.equal(writes.length,0);
    const result=await publishPiRootReleaseGrant(env,request,{request_id:request.request_id},true);
    assert.equal(result.root_receipt_verified,false);
    assert.equal(writes.length,2);
  } finally {globalThis.fetch=original;}
});
