import assert from 'node:assert/strict';
import {createHash, webcrypto} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {Script} from 'node:vm';
import {canonicalPiJson} from '../cloudflare/operator-console/src/pi_owner_approval.js';
import {verifyPiOwnerDeviceGrant} from '../cloudflare/operator-console/src/pi_owner_device_grant.js';

globalThis.crypto ??= webcrypto;
const encode=new TextEncoder();
const h=(value)=>createHash('sha256').update(value).digest('hex');
const a='a'.repeat(40),b='b'.repeat(64),c='c'.repeat(40),d='d'.repeat(64);
const now=Date.now(),iso=n=>new Date(n).toISOString();
const request={
 schema:'commandcenter.pi.bot_release_request.v1', node_id:'cc-pi4',
 request_id:'independent-device-test-123456',
 action:'pi.bot.replace_existing',source_repo:'XoticHaze/mm-IBKR',source_sha:a,
 image_ref:'ghcr.io/example/new@sha256:'+b,client_id:43081,inspect_client_id:43082,
 artifact_manifest_blob_sha:c,expected_release:'r'+'f'.repeat(12),
 created_at:iso(now-1000),expires_at:iso(now+260000),
 expected_active_source_sha:c,expected_active_image_ref:'ghcr.io/example/old@sha256:'+d,
 runtime_mode:'PRESERVE_EXISTING_LIVE'
};
const approval={
 schema:'commandcenter.pi.bot_replace_approval.v1',request_id:request.request_id,
 source_sha:request.source_sha,image_ref:request.image_ref,
 expected_active_source_sha:request.expected_active_source_sha,
 expected_active_image_ref:request.expected_active_image_ref,
 artifact_manifest_blob_sha:request.artifact_manifest_blob_sha,
 client_id:request.client_id,inspect_client_id:request.inspect_client_id,
 expected_release:request.expected_release,runtime_mode:'PRESERVE_EXISTING_LIVE',
 acknowledge_existing_live_mode_preserved:true,expires_at:request.expires_at
};
const keys=await crypto.subtle.generateKey('Ed25519',true,['sign','verify']);
const spki=new Uint8Array(await crypto.subtle.exportKey('spki',keys.publicKey));
const pem='-----BEGIN PUBLIC KEY-----\n'+Buffer.from(spki).toString('base64').match(/.{1,64}/g).join('\n')+'\n-----END PUBLIC KEY-----\n';
const sha=h(spki);
const env={
 PI_OWNER_SIGNER_ALLOWED_EMAILS:'human@example.test',
 PI_OWNER_ROOT_PUBLIC_KEY_PEM:pem,
 PI_OWNER_ENROLLED_PUB_SHA256:sha,
 PI_OWNER_SIGNER_ENABLED:'0'
};
const op={email:'human@example.test',sub:'access-email-sub'};
const domain='commandcenter.pi.bot_replace_approval.v1\0';
const signature=await crypto.subtle.sign('Ed25519',keys.privateKey,encode.encode(domain+canonicalPiJson(approval)));
const signed={...approval,key_id:'ccpi-owner-bootstrap-ed25519-v1',signature_b64:Buffer.from(signature).toString('base64')};
assert.equal(signed.signature_b64.length,88);
const valid=await verifyPiOwnerDeviceGrant(env,op,'replace',request,approval,signed);
assert.equal(valid.independent_device_signature_verified,true);
assert.equal(valid.key_sha256,sha);
async function rejects(msg,e=env,o=op,r=request,ap=approval,s=signed){
 await assert.rejects(()=>verifyPiOwnerDeviceGrant(e,o,'replace',r,ap,s),new RegExp(msg));
}
await rejects('pi_owner_operator_not_admitted',env,{email:'wrong@example.test',sub:'other'});
await rejects('pi_owner_operator_not_admitted',env,{email:'human@example.test'});
await rejects('pi_owner_root_key_enrollment_missing',{...env,PI_OWNER_ENROLLED_PUB_SHA256:''});
await rejects('pi_owner_root_public_key_fingerprint_mismatch',{...env,PI_OWNER_ENROLLED_PUB_SHA256:'f'.repeat(64)});
await rejects('pi_owner_legacy_signer_must_remain_disabled',{...env,PI_OWNER_SIGNER_ENABLED:'1'});
await rejects('pi_owner_signed_grant_unsigned_payload_drift',env,op,request,approval,{...signed,source_sha:c});
await rejects('pi_owner_signed_grant_shape_invalid',env,op,request,approval,{...signed,extra:true});
await rejects('pi_owner_device_signature_rejected',env,op,request,approval,{...signed,signature_b64:'A'.repeat(86)+'=='});
await rejects('pi_owner_request_not_fresh',env,op,{...request,expires_at:iso(now-2000)},{...approval,expires_at:iso(now-2000)},{...signed,expires_at:iso(now-2000)});
// A new root-agent update uses the same owner key but a DISTINCT domain,
// exact source/predecessor/expiry, and no blanket pi.release.apply permission.
const releaseReq={
  schema:'commandcenter.pi.release_request.v1',
  node_id:'cc-pi4',request_id:'independent-root-test-12345',
  action:'pi.release.apply',source_repo:'XoticHaze/CommandCenter',
  source_sha:a,expected_release:'r'+'b'.repeat(12),
  created_at:iso(now-1000),expires_at:iso(now+230000)
};
const releaseApproval={
  schema:'commandcenter.pi.release_request_approval.v1',
  request_id:releaseReq.request_id,source_sha:releaseReq.source_sha,
  expected_release:releaseReq.expected_release,expires_at:releaseReq.expires_at
};
const rootDomain='commandcenter.pi.release_request_approval.v1\0';
const releaseSig=await crypto.subtle.sign('Ed25519',keys.privateKey,
  encode.encode(rootDomain+canonicalPiJson(releaseApproval)));
const releaseGrant={...releaseApproval,
  key_id:'ccpi-owner-bootstrap-ed25519-v1',
  signature_b64:Buffer.from(releaseSig).toString('base64')};
const verifiedRelease=await verifyPiOwnerDeviceGrant(env,op,'root_release',
  releaseReq,releaseApproval,releaseGrant);
assert.equal(verifiedRelease.independent_device_signature_verified,true);
assert.equal(verifiedRelease.request_id,releaseReq.request_id);
await assert.rejects(()=>verifyPiOwnerDeviceGrant(env,op,'root_release',
  {...releaseReq,source_repo:'XoticHaze/other'},
  releaseApproval,releaseGrant),/pi_owner_root_release_identity_mismatch/);
await assert.rejects(()=>verifyPiOwnerDeviceGrant(env,op,'root_release',
  releaseReq,{...releaseApproval,source_sha:c},releaseGrant),
  /pi_owner_root_release_identity_mismatch/);
await assert.rejects(()=>verifyPiOwnerDeviceGrant(env,op,'root_release',
  releaseReq,releaseApproval,{...signed}),
  /pi_owner_signed_grant_shape_invalid/);
await assert.rejects(()=>verifyPiOwnerDeviceGrant(env,op,'root_release',
  {...releaseReq,expires_at:iso(now-2000)},
  {...releaseApproval,expires_at:iso(now-2000)},
  {...releaseGrant,expires_at:iso(now-2000)}),
  /pi_owner_root_release_not_fresh/);
await assert.rejects(()=>verifyPiOwnerDeviceGrant(env,op,'replace',
  request,approval,releaseGrant),/pi_owner_signed_grant_unsigned_payload_drift/);

const external=readFileSync('cloudflare/operator-console/owner-device-offline-signer.html','utf8');
assert.match(external,/connect-src 'none'/);
assert.match(external,/owner_device_encrypted_backup\.v1/);
assert.match(external,/AES-GCM/);
assert.match(external,/PBKDF2/);
assert.match(external,/commandcenter\.pi\.bot_replace_approval\.v1\\u0000/);
assert.doesNotMatch(external,/\b(?:fetch|XMLHttpRequest|WebSocket|sendBeacon)\s*\(/);
const scripts=[...external.matchAll(/<script>([\s\S]*?)<\/script>/g)];
assert.equal(scripts.length,1);
new Script(scripts[0][1],{filename:'offline-owner-device-signer.js'});
console.log('Pi owner detached-device Ed25519 verification, deny-by-default, and offline signed-source syntax PASS');
