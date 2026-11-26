import test from 'node:test';
import assert from 'node:assert/strict';
import { webcrypto, createPublicKey, verify, createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
  PVE7_DOMAIN, PVE7_SOURCE, PVE7_SCOPE, PVE7_SCHEMA, PVE7_FILES,
  PVE7_ENVELOPE, PVE7_SIG_FORMAT, canonicalPve7, pve7Payload,
  buildOwnerApprovedPve7Grant,validatePve7SigningRequest,validatePve7Grant
} from '../src/pve7-grant.mjs';
const now=Date.parse('2026-11-26T12:00:00.000Z');
const env={PVE7_RELEASE_SIGNING_ENABLED:'1',PVE7_APPROVED_SOURCE_SHA:PVE7_SOURCE,
  PVE7_OWNER_APPROVAL_SHA256:'f'.repeat(64),PVE7_EXPECTED_AUTHORITY_KEY_ID:'sha256:'+'a'.repeat(64),
  PVE7_RELEASE_ID:'synthetic-release',PVE7_REQUEST_ID:'synthetic-request',
  PVE7_NOT_BEFORE:'2026-11-26T11:59:00.000Z',PVE7_EXPIRES_AT:'2026-11-26T12:05:00.000Z'};
const request=()=>buildOwnerApprovedPve7Grant(env,now);
const denied=cb=>assert.throws(cb);
test('disabled by default',()=>denied(()=>buildOwnerApprovedPve7Grant({},now)));
test('exact owner-approved PVE7-only grant',()=>{
  const {grant,signer_key_id}=request();
  assert.equal(grant.schema,PVE7_SCHEMA);
  assert.equal(grant.node_id,'pve7');
  assert.equal(grant.operation,PVE7_SCOPE);
  assert.equal(grant.source_sha,PVE7_SOURCE);
  assert.equal(signer_key_id,env.PVE7_EXPECTED_AUTHORITY_KEY_ID);
  assert.deepEqual(validatePve7SigningRequest(request(),env,now).grant,request().grant, 'deep validation performed');
});
test('signing request with caller changed grant denied',()=>{
  const r=request();r.grant.request_id='foreign-request';
  denied(()=>validatePve7SigningRequest(r,env,now));
});
test('unknown target denied',()=>{const r=request();r.grant.node_id='pve9';denied(()=>validatePve7Grant(r.grant,now))});
test('shell operation denied',()=>{const r=request();r.grant.operation='pve7.exec.v1';denied(()=>validatePve7Grant(r.grant,now))});
test('replaced source denied',()=>{const r=request();r.grant.source_sha='0'.repeat(40);denied(()=>validatePve7Grant(r.grant,now))});
test('extra source file denied',()=>{const r=request();r.grant.files['arbitrary.sh']={...PVE7_FILES['pve-host-rescue-executor.py']};denied(()=>validatePve7Grant(r.grant,now))});
test('candidate hash tamper denied',()=>{const r=request();r.grant.files['pve-host-rescue-mailbox.py'].sha256='0'.repeat(64);denied(()=>validatePve7Grant(r.grant,now))});
test('predecessor hash tamper denied',()=>{const r=request();r.grant.files['pve-host-rescue-mailbox.py'].predecessor_sha256='0'.repeat(64);denied(()=>validatePve7Grant(r.grant,now))});
test('missing independent review digest denied',()=>{denied(()=>buildOwnerApprovedPve7Grant({...env,PVE7_OWNER_APPROVAL_SHA256:''},now))});
test('wrong pinned authority identity denied',()=>{denied(()=>buildOwnerApprovedPve7Grant({...env,PVE7_EXPECTED_AUTHORITY_KEY_ID:'wrong'},now))});
test('unapproved source configuration denied',()=>{denied(()=>buildOwnerApprovedPve7Grant({...env,PVE7_APPROVED_SOURCE_SHA:'0'.repeat(40)},now))});
test('stale approval denied',()=>{denied(()=>buildOwnerApprovedPve7Grant({...env,PVE7_NOT_BEFORE:'2026-11-25T12:00:00Z'},now))});
test('future not-before denied',()=>{denied(()=>buildOwnerApprovedPve7Grant({...env,PVE7_NOT_BEFORE:'2026-11-26T12:01:00Z'},now))});
test('expired approval denied',()=>{denied(()=>buildOwnerApprovedPve7Grant({...env,PVE7_EXPIRES_AT:'2026-11-26T11:59:00Z'},now))});
test('overlong grant denied',()=>{denied(()=>buildOwnerApprovedPve7Grant({...env,PVE7_EXPIRES_AT:'2026-11-26T12:30:00Z'},now))});
test('caller cannot add fields',()=>{const r=request();r.extra='yes';denied(()=>validatePve7SigningRequest(r,env,now))});
test('canonical grant order stable',()=>{
  const g=request().grant;
  assert.equal(canonicalPve7(g),canonicalPve7(Object.fromEntries(Object.entries(g).reverse())));
});
test('pure signed payload matches openssl native ECDSA SHA256',async()=>{
  const pair=await webcrypto.subtle.generateKey({name:'ECDSA',namedCurve:'P-256'},true,['sign','verify']);
  const raw=Buffer.from(await webcrypto.subtle.exportKey('raw',pair.publicKey));
  const fingerprint='sha256:'+createHash('sha256').update(raw).digest('hex');
  assert.match(fingerprint,/^sha256:[a-f0-9]{64}$/);
  const grant=request().grant;
  const message=Buffer.from(pve7Payload(grant,now));
  assert.equal(message.toString(),PVE7_DOMAIN+canonicalPve7(grant));
  const sig=Buffer.from(await webcrypto.subtle.sign({name:'ECDSA',hash:'SHA-256'},pair.privateKey,message));
  assert.equal(sig.length,64);
  const prefix=Buffer.from('3059301306072a8648ce3d020106082a8648ce3d030107034200','hex');
  const publicKey=createPublicKey({key:Buffer.concat([prefix,raw]),format:'der',type:'spki'});
  assert.ok(verify('sha256',message,{key:publicKey,dsaEncoding:'ieee-p1363'},sig));
  function derInt(x){let i=0;while(i<x.length-1&&x[i]===0)i++;let y=x.subarray(i);if(y[0]&128)y=Buffer.concat([Buffer.from([0]),y]);return Buffer.concat([Buffer.from([2,y.length]),y])}
  const inner=Buffer.concat([derInt(sig.subarray(0,32)),derInt(sig.subarray(32))]);
  const der=Buffer.concat([Buffer.from([48,inner.length]),inner]);
  const dir=mkdtempSync(join(tmpdir(),'pve7-p256-'));
  try{
    writeFileSync(join(dir,'message'),message);
    writeFileSync(join(dir,'public.pem'),publicKey.export({format:'pem',type:'spki'}));
    writeFileSync(join(dir,'sig.der'),der);
    const args=['dgst','-sha256','-verify',join(dir,'public.pem'),'-signature',join(dir,'sig.der'),join(dir,'message')];
    assert.equal(spawnSync('openssl',args).status,0);
    assert.equal(PVE7_ENVELOPE,'commandcenter.pve7.existing_authority_envelope.v1');
    assert.equal(PVE7_SIG_FORMAT,'ecdsa-p256-sha256-p1363');
  }finally{rmSync(dir,{recursive:true,force:true})}
});
