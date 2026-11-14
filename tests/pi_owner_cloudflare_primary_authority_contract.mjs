import assert from 'node:assert/strict';
import { createHash, createPublicKey, verify as verifySignature, webcrypto } from 'node:crypto';
import worker from '../cloudflare/pi-owner-authority/src/index.js';
import { PiOwnerApprovalState, canonicalPiJson } from '../cloudflare/operator-console/src/pi_owner_approval.js';
globalThis.crypto ??= webcrypto;

const origin='https://ccpi-owner.local.test';
const url=path=>origin+path;
const sha256=text=>createHash('sha256').update(text).digest('hex');
const sha1=text=>createHash('sha1').update(text).digest('hex');
const activation='independent-owner-activation-32chars-TEST';
const issuer='owner@example.test';
const env={
  PI_OWNER_ACCESS_AUD:'isolated-cloudflare-access-application-aud',
  PI_OWNER_SIGNER_ALLOWED_EMAILS:issuer,
  PI_OWNER_INIT_CODE_SHA256:sha256(activation),
  PI_OWNER_FIRST_ISSUE_ENABLED:'0',
  PI_OWNER_FIRST_ENROLL_ENABLED:'0',
  PI_OWNER_NORMAL_RELEASE_ENABLED:'0',
  PI_OWNER_SIGNER_ENABLED:'0',
  PI_OWNER_QUEUE_GITHUB_TOKEN:'synthetic-repo-scoped-token-for-networkless-test',
};
class Storage {
  constructor(){this.map=new Map();}
  async get(k){return this.map.get(k);}
  async put(k,v){this.map.set(k,v);}
  async transaction(fn){return fn(this);}
}
const protectedDO=new PiOwnerApprovalState({storage:new Storage()},env);
env.PI_OWNER_APPROVER={
  idFromName:n=>{assert.equal(n,'cc-pi4-owner-v1');return n;},
  get:n=>{assert.equal(n,'cc-pi4-owner-v1');return {fetch:req=>protectedDO.fetch(req)};}
};
const ctx={access:{aud:env.PI_OWNER_ACCESS_AUD,
  getIdentity:async()=>({email:issuer})}};
async function invoke(path, data, c=ctx, overrideOrigin=origin){
  const headers=data===undefined?{}:{
    origin:overrideOrigin,'content-type':'application/json',
    'sec-fetch-site':'same-origin',
  };
  const request=new Request(url(path),{method:data===undefined?'GET':'POST',
    headers,body:data===undefined?undefined:JSON.stringify(data)});
  const res=await worker.fetch(request,env,c);
  return {status:res.status,body:await(res.headers.get('content-type')?.includes('json')?
    res.json():res.text())};
}
assert.equal((await invoke('/api/status',undefined,{})).status,403,
  'no ctx.access, including service binding, must fail');
assert.equal((await invoke('/api/status',undefined,
  {access:{aud:'untrusted-aud',getIdentity:async()=>({email:issuer})}})).status,403);
assert.equal((await invoke('/api/status',undefined,
  {access:{aud:env.PI_OWNER_ACCESS_AUD,getIdentity:async()=>({email:'other@example.test'})}})).status,403);
assert.equal((await invoke('/api/status')).body.initialized,false);
assert.equal((await invoke('/api/initialize',{
  activation_code:activation,confirm_first_issue:true,
})).status,403,'no first issuance until independent Cloudflare admin permits');
env.PI_OWNER_FIRST_ISSUE_ENABLED='1';
assert.equal((await invoke('/api/initialize',{
  activation_code:activation,confirm_first_issue:true,
},ctx,'https://evil.example')).status,403,'strict origin');
assert.equal((await invoke('/api/initialize',{
  activation_code:'wrong',confirm_first_issue:true,
})).status,403,'activation required');
const issued=await invoke('/api/initialize',{
  activation_code:activation,confirm_first_issue:true,
});
assert.equal(issued.status,201);
assert.match(issued.body.public_key_sha256,/^[0-9a-f]{64}$/);
assert.match(issued.body.public_key_pem,/BEGIN PUBLIC KEY/);
assert.equal((await invoke('/api/status')).body.initialized,true);
assert.equal((await invoke('/api/initialize',{
  activation_code:activation,confirm_first_issue:true,
})).status,403,'never silently rotate a minted key');
env.PI_OWNER_FIRST_ISSUE_ENABLED='0';
const now=Date.now(),iso=n=>new Date(n).toISOString();
const req={
  schema:'commandcenter.pi.release_request.v1',node_id:'cc-pi4',
  request_id:'cloudflare-primary-synthetic-123456',
  action:'pi.release.apply',source_repo:'XoticHaze/CommandCenter',
  source_sha:'a'.repeat(40),expected_release:'r'+'b'.repeat(12),
  created_at:iso(now-1000),expires_at:iso(now+250000),
};
assert.equal((await invoke('/api/approve-root',{
  request:req,approve_exact_release:true,
})).status,403,'signing disabled by default');
env.PI_OWNER_NORMAL_RELEASE_ENABLED='1';
env.PI_OWNER_SIGNER_ENABLED='1';
assert.equal((await invoke('/api/approve-root',{
  request:req,approve_exact_release:true,
})).status,403,'must enroll root verifier');
assert.equal((await invoke('/api/enroll',{
  activation_code:activation,pi_enrolled_public_key_sha256:issued.body.public_key_sha256,
  confirm_independently_enrolled_on_pi:true,
})).status,403,'root-side enrollment flag required');
env.PI_OWNER_FIRST_ENROLL_ENABLED='1';
env.PI_OWNER_ENROLLED_PUB_SHA256='f'.repeat(64);
assert.equal((await invoke('/api/enroll',{
  activation_code:activation,pi_enrolled_public_key_sha256:issued.body.public_key_sha256,
  confirm_independently_enrolled_on_pi:true,
})).status,403,'wrong root fingerprint must fail');
env.PI_OWNER_ENROLLED_PUB_SHA256=issued.body.public_key_sha256;
assert.equal((await invoke('/api/enroll',{
  activation_code:activation,pi_enrolled_public_key_sha256:issued.body.public_key_sha256,
  confirm_independently_enrolled_on_pi:true,
})).status,201);
env.PI_OWNER_FIRST_ENROLL_ENABLED='0';

const queue=new Map(),writes=[];
const oldFetch=globalThis.fetch;
globalThis.fetch=async (address,opts={})=>{
  const u=new URL(address);
  assert.equal(u.hostname,'api.github.com');
  const item=u.pathname.replace('/repos/XoticHaze/CommandCenter-gate-control/contents/','');
  if(opts.method==='PUT'){
    const payload=JSON.parse(opts.body);
    assert.equal(payload.branch,'pi-node-inbox');
    const text=Buffer.from(payload.content,'base64').toString('utf8');
    assert.equal(text,canonicalPiJson(JSON.parse(text)));
    const stored={sha:sha1(text),text};
    queue.set(item,stored);writes.push(item);
    return Response.json({content:{sha:stored.sha}},{status:201});
  }
  const row=queue.get(item);
  if(!row)return Response.json({}, {status:404});
  return Response.json({sha:row.sha,encoding:'base64',
    size:Buffer.byteLength(row.text),
    content:Buffer.from(row.text).toString('base64')});
};
try {
  // The browser can load an exact current CC proposal without receiving the
  // private Git bearer. Loading never signs, submits, or mutates the queue.
  assert.equal((await invoke('/api/proposal')).status,403,
    'missing queue proposal must fail closed');
  const reviewPath='pi-node/release-request.json';
  const reviewText=canonicalPiJson(req);
  queue.set(reviewPath,{sha:sha1(reviewText),text:reviewText});
  assert.equal((await invoke('/api/proposal',undefined,{})).status,403,
    'proposal read must also require Cloudflare Access identity');
  const review=await invoke('/api/proposal');
  assert.equal(review.status,200);
  assert.equal(review.body.review_only,true);
  assert.equal(review.body.cloudflare_signature_issued,false);
  assert.deepEqual(review.body.request,req);
  assert.equal(writes.length,0,'loading never submits or signs a grant');
  const wrongText=canonicalPiJson({...req,source_repo:'XoticHaze/not-authorized'});
  queue.set(reviewPath,{sha:sha1(wrongText),text:wrongText});
  assert.equal((await invoke('/api/proposal')).status,403,
    'wrong repository proposal must not be presented as ready');
  queue.delete(reviewPath);
  assert.equal((await invoke('/api/approve-root',{
    request:{...req,source_repo:'XoticHaze/other'},
    approve_exact_release:true,
  })).status,403,'wrong source must not sign');
  const done=await invoke('/api/approve-root',{
    request:req,approve_exact_release:true,
  });
  assert.equal(done.status,202);
  assert.equal(done.body.cloudflare_signature_issued,true);
  assert.equal(done.body.root_execution_verified,false);
  assert.deepEqual(writes,['pi-node/release-signed-approval.json',
    'pi-node/release-request.json']);
  const signed=JSON.parse(queue.get(writes[0]).text);
  const unsigned={
    schema:'commandcenter.pi.release_request_approval.v1',
    request_id:req.request_id,source_sha:req.source_sha,
    expected_release:req.expected_release,expires_at:req.expires_at,
  };
  assert.equal(signed.key_id,'ccpi-owner-bootstrap-ed25519-v1');
  assert.equal(verifySignature(null,Buffer.concat([
    Buffer.from('commandcenter.pi.release_request_approval.v1\0'),
    Buffer.from(canonicalPiJson(unsigned)),
  ]),createPublicKey(issued.body.public_key_pem),
  Buffer.from(signed.signature_b64,'base64')),true);
  assert.equal(verifySignature(null,Buffer.concat([
    Buffer.from('commandcenter.pi.bot_replace_approval.v1\0'),
    Buffer.from(canonicalPiJson(unsigned)),
  ]),createPublicKey(issued.body.public_key_pem),
  Buffer.from(signed.signature_b64,'base64')),false,'domain isolation');
  const retry=await invoke('/api/approve-root',{
    request:req,approve_exact_release:true,
  });
  assert.equal(retry.status,202);
  assert.equal(retry.body.recovered_exact_same_id,true);
  assert.equal(writes.length,2,'same-ID replay must not republish');
} finally {
  globalThis.fetch=oldFetch;
}
console.log('Cloudflare isolated primary owner, Ed25519, root domain, deny-by-default, Git transport and emergency independence: PASS');
