import assert from 'node:assert/strict';
import { webcrypto } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { verifySignedPlacementClaim, consumeSignedPlacementOnce } from '../cloudflare/reference-release-broker/src/placement.js';
if (!globalThis.crypto) globalThis.crypto = webcrypto;
const python = JSON.parse(readFileSync(new URL('./fixtures/placement_claim_signed_python.v1.json',import.meta.url),'utf8'));
const pythonProof=await verifySignedPlacementClaim(python.claim,python.policy,python.now_seconds);
assert.equal(pythonProof.signature_verified,true);
assert.equal(pythonProof.nonce_consumed,false);
assert.equal(pythonProof.external_launch_authorized,false);
const key = await crypto.subtle.generateKey('Ed25519',true,['sign','verify']);
const publicRaw = new Uint8Array(await crypto.subtle.exportKey('raw',key.publicKey));
const now = 1793682000; // fixed UTC epoch for synthetic test
const stamp = seconds => new Date(seconds*1000).toISOString().slice(0,19)+'Z';
const policy = {issuer_id:'neutral.issuer.v1',issuer_public_b64:Buffer.from(publicRaw).toString('base64'),
  registry_sha256:'a'.repeat(64),route_sha256:'b'.repeat(64),compute_id:'public_research_compute_current'};
const receipt = {schema:'commandcenter.job_submission_receipt.v1',job_id:'job-001',job_sha256:'c'.repeat(64),
  lane:'reference',workload:'synthetic',compute_id:policy.compute_id,
  executor:{kind:'github_actions_generic',repository:'XoticHaze/research-compute-public-'},
  trust_mode:'public_encrypted',state:'PLACED',load_ratio:0.25,
  issuer_proof:{issuer_id:policy.issuer_id,issued_at_utc:stamp(now-20),expires_at_utc:stamp(now+100),
    nonce:'d'.repeat(32),registry_sha256:policy.registry_sha256,route_sha256:policy.route_sha256}};
const canonical = v => Array.isArray(v)?'['+v.map(canonical).join(',')+']':v&&typeof v==='object'?
  '{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}':JSON.stringify(v);
const bytes = v => new TextEncoder().encode('COMMANDCENTER-PLACEMENT-ISSUANCE-V1\n'+canonical(v));
async function sign(v) {const payload=bytes(v); const signature=await crypto.subtle.sign('Ed25519',key.privateKey,payload);
  return {payload_b64:Buffer.from(payload).toString('base64'),signature_b64:Buffer.from(signature).toString('base64')};}
const ok=await sign(receipt);
const result=await verifySignedPlacementClaim(ok,policy,now);
assert.deepEqual([result.signature_verified,result.nonce_consumed,result.external_launch_authorized],[true,false,false]);
assert.equal(result.nonce,'d'.repeat(32));
assert.equal(result.trust_mode,'public_encrypted');
let rejects=0;
async function deny(p, pol=policy, at=now) {await assert.rejects(()=>verifySignedPlacementClaim(p,pol,at),/PLACEMENT_ISSUER_ATTESTATION_REJECTED/);rejects++;}
const mutations=[
 v=>v.issuer_proof.nonce='g'.repeat(32),
 v=>v.issuer_proof.registry_sha256='e'.repeat(64),
 v=>v.issuer_proof.route_sha256='e'.repeat(64),
 v=>v.issuer_proof.issuer_id='another',
 v=>v.issuer_proof.expires_at_utc=stamp(now-1),
 v=>v.issuer_proof.issued_at_utc=stamp(now+31),
 v=>v.issuer_proof.issued_at_utc=stamp(now-301),
 v=>v.issuer_proof.signature_b64='unexpected',
 v=>v.state='QUEUED',
 v=>v.trust_mode='local_safe',
 v=>v.compute_id='other',
 v=>v.job_sha256='f',
 v=>v.load_ratio=1.2,
 v=>v.executor.kind='shell',
];
for(const mutate of mutations){const next=structuredClone(receipt);mutate(next);await deny(await sign(next));}
await deny({...ok,signature_b64:Buffer.from(new Uint8Array(64)).toString('base64')});
await deny({...ok,payload_b64:Buffer.from(bytes({...receipt,nonce:'h'.repeat(32)})).toString('base64')});
await deny({...ok,unexpected:'1'});
await deny(ok,{...policy,compute_id:'other'});
await deny(ok,{...policy,issuer_public_b64:Buffer.from(new Uint8Array(32)).toString('base64')});
await deny(ok,{...policy,registry_sha256:'0'.repeat(64)});
await deny(ok,policy,now+101);
await deny(ok,policy,now-51);

// Verify the exact existing DO path is selected only AFTER a valid signature.
let calls=0, consumed=false, lastName=null;
const ledger={idFromName: name=>{lastName=name;return {name}},get: id=>({fetch:async (url,options)=>{
  calls++;assert.equal(url,'https://grant-ledger/consume-placement');
  assert.equal(options.method,'POST');
  assert.deepEqual(JSON.parse(options.body),{nonce:'d'.repeat(32),issuer_id:policy.issuer_id});
  if(id.name !== 'placement:'+'d'.repeat(32) || consumed) return new Response(JSON.stringify({error:'replay'}),{status:409});
  consumed=true; return new Response(JSON.stringify({ok:true}),{status:200});
}})};
const claimed=await consumeSignedPlacementOnce(ok,policy,ledger,now);
assert.equal(claimed.nonce_consumed,true);
assert.equal(claimed.external_launch_authorized,false);
assert.equal(lastName,'placement:'+'d'.repeat(32));
await assert.rejects(()=>consumeSignedPlacementOnce(ok,policy,ledger,now),/PLACEMENT_ISSUER_ATTESTATION_REJECTED/);
assert.equal(calls,2);
await assert.rejects(()=>consumeSignedPlacementOnce({...ok,signature_b64:'@@@@'},policy,ledger,now),/PLACEMENT_ISSUER_ATTESTATION_REJECTED/);
assert.equal(calls,2,'invalid signature must never reach DO');
await assert.rejects(()=>consumeSignedPlacementOnce(ok,policy,{idFromName:()=>({}),get:()=>({fetch:()=>{throw new Error('DO timeout')}})},now),/PLACEMENT_ISSUER_ATTESTATION_REJECTED/);
console.log(JSON.stringify({test:'signed-placement-verifier-and-internal-once-claim',positive:3,negative:rejects+3,status:'PASS'}));
