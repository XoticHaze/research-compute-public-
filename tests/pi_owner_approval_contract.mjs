import assert from 'node:assert/strict';
import {createHash, createPublicKey, verify as cryptoVerify} from 'node:crypto';
import {
  canonicalPiJson, validatePiOwnerApproval, PiOwnerApprovalState,
} from '../cloudflare/operator-console/src/pi_owner_approval.js';

const base = (c, n) => c.repeat(n);
const hex40 = base('a',40), hex64 = base('b',64);
const iso = (n) => new Date(n).toISOString();
const body = (doc) => new Request('https://pi-owner.internal/path',{
  method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(doc),
});
class Storage {
  constructor() {this.map=new Map();}
  async get(key) {return this.map.get(key);}
  async put(key,value) {this.map.set(key,value);}
  async transaction(fn) {return fn(this);}
}
const sha = (text) => createHash('sha256').update(text).digest('hex');
const now = Date.now();
const activation = 'operator-entered-independent-test-secret-32bytes';
const env = {
  PI_OWNER_INIT_CODE_SHA256:sha(activation),
  PI_OWNER_SIGNER_ALLOWED_EMAILS:'human@example.test',
  PI_OWNER_SIGNER_ENABLED:'0',
  PI_OWNER_QUEUE_GITHUB_TOKEN:'synthetic-not-a-real-github-token',
};
const state = new PiOwnerApprovalState({storage:new Storage()},env);
const operator = {email:'human@example.test',sub:'access-sub-123'};
async function call(path,payload) {
  const response=await state.fetch(new Request('https://pi-owner.internal'+path,{
    method:'POST',headers:{'content-type':'application/json'},
    body:JSON.stringify({...payload,operator}),
  }));
  return {status:response.status,body:await response.json()};
}
function releaseBootstrap() {
  const req = {
    schema:'commandcenter.pi.bot_owner_bootstrap_request.v1',
    node_id:'cc-pi4',request_id:'synthetic-bootstrap-123456',
    action:'pi.bot.owner_bootstrap',source_sha:hex40,
    image_ref:'ghcr.io/example/pinned@sha256:'+hex64,
    expected_release:'r'+base('c',12),
    created_at:iso(now-1000),expires_at:iso(now+85000),
  };
  const approval = {
    schema:'commandcenter.pi.bot_owner_bootstrap_approval.v1',
    node_id:'cc-pi4',request_id:req.request_id,
    request_sha256:sha(canonicalPiJson(req)),
    source_sha:req.source_sha,image_ref:req.image_ref,
    expires_at:req.expires_at,snapshot_sha256:hex64,
    expected_account_sha256:hex64,
    canonical_start_receipt_sha256:hex64,
    writer_lease_receipt_sha256:hex64,
    review_epoch_utc:iso(now-2000),
    no_pi_live_orders_before_epoch_verified:true,
    exclusive_writer_lease_reviewed:true,
    selected_strategy_pins_sha256:hex64,
    approve_new_pi_owned_zero_only:true,
  };
  return {kind:'bootstrap',request:req,approval,approve_exact_release:true};
}
function releaseReplace() {
  const req = {
    schema:'commandcenter.pi.bot_release_request.v1',
    node_id:'cc-pi4',request_id:'synthetic-replace-567890',
    action:'pi.bot.replace_existing',source_repo:'XoticHaze/mm-IBKR',
    source_sha:hex40,image_ref:'ghcr.io/example/new@sha256:'+hex64,
    client_id:43081,inspect_client_id:43082,
    artifact_manifest_blob_sha:base('d',40),
    expected_release:'r'+base('c',12),
    created_at:iso(now-1000),expires_at:iso(now+280000),
    expected_active_source_sha:base('e',40),
    expected_active_image_ref:'ghcr.io/example/old@sha256:'+base('f',64),
    runtime_mode:'PRESERVE_EXISTING_LIVE',
  };
  const approval = {
    schema:'commandcenter.pi.bot_replace_approval.v1',
    request_id:req.request_id,source_sha:req.source_sha,
    image_ref:req.image_ref,
    expected_active_source_sha:req.expected_active_source_sha,
    expected_active_image_ref:req.expected_active_image_ref,
    artifact_manifest_blob_sha:req.artifact_manifest_blob_sha,
    client_id:req.client_id,inspect_client_id:req.inspect_client_id,
    expected_release:req.expected_release,
    runtime_mode:'PRESERVE_EXISTING_LIVE',
    acknowledge_existing_live_mode_preserved:true,
    expires_at:req.expires_at,
  };
  return {kind:'replace',request:req,approval,approve_exact_release:true};
}

assert.equal((await call('/initialize',{activation_code:'wrong'})).status,403);
assert.equal((await call('/initialize',{activation_code:activation})).status,201);
assert.equal((await call('/initialize',{activation_code:activation})).status,409);
let status=await state.fetch(new Request('https://pi-owner.internal/status'));
let info=await status.json();
assert.equal(info.initialized,true);
assert.equal(info.enrolled,false);
assert.match(info.public_key_pem,/BEGIN PUBLIC KEY/);
assert.match(info.public_key_sha256,/^[0-9a-f]{64}$/);
assert.equal((await call('/sign',releaseBootstrap())).status,403);
assert.equal((await call('/enroll',{
  activation_code:activation,pi_enrolled_public_key_sha256:hex64,
  confirm_independently_enrolled_on_pi:true,
})).status,403);
assert.equal((await call('/enroll',{
  activation_code:activation,pi_enrolled_public_key_sha256:info.public_key_sha256,
  confirm_independently_enrolled_on_pi:true,
})).status,201);
env.PI_OWNER_SIGNER_ENABLED='1';
env.PI_OWNER_ENROLLED_PUB_SHA256=hex64;
assert.equal((await call('/sign',releaseBootstrap())).status,403);
env.PI_OWNER_ENROLLED_PUB_SHA256=info.public_key_sha256;
const unsigned=releaseBootstrap();
await validatePiOwnerApproval('bootstrap',unsigned.approval,unsigned.request);
const issued=await call('/sign',unsigned);
assert.equal(issued.status,201);
const signed=issued.body.signed_grant;
assert.equal(signed.key_id,'ccpi-owner-bootstrap-ed25519-v1');
assert.equal(cryptoVerify(null,Buffer.concat([
  Buffer.from('commandcenter.pi.bot_owner_bootstrap_approval.v1\0'),
  Buffer.from(canonicalPiJson(unsigned.approval)),
]),createPublicKey(info.public_key_pem),Buffer.from(signed.signature_b64,'base64')),true);
assert.equal(cryptoVerify(null,Buffer.concat([
  Buffer.from('commandcenter.pi.bot_replace_approval.v1\0'),
  Buffer.from(canonicalPiJson(unsigned.approval)),
]),createPublicKey(info.public_key_pem),Buffer.from(signed.signature_b64,'base64')),false);
assert.equal((await call('/sign',unsigned)).body.recovered,true);
const changed=releaseBootstrap();
changed.approval.selected_strategy_pins_sha256=base('d',64);
assert.equal((await call('/sign',changed)).status,409);
assert.equal((await call('/sign',{...releaseReplace(),approve_exact_release:false})).status,403);
const replace=releaseReplace();
const rs=await call('/sign',replace);
assert.equal(rs.status,201);
assert.equal(cryptoVerify(null,Buffer.concat([
  Buffer.from('commandcenter.pi.bot_replace_approval.v1\0'),
  Buffer.from(canonicalPiJson(replace.approval)),
]),createPublicKey(info.public_key_pem),Buffer.from(rs.body.signed_grant.signature_b64,'base64')),true);
assert.equal((await call('/sign',{...replace,operator:{email:'wrong@example.test'}})).body.recovered,true,
  'internal signer uses verified operator from Cloudflare route, never caller-supplied body');
const replay={...releaseReplace(),request:{...releaseReplace().request,source_sha:base('9',40)}};
assert.equal((await call('/sign',replay)).status,403);
const invalid=releaseReplace();
invalid.approval.acknowledge_existing_live_mode_preserved=false;
await assert.rejects(()=>validatePiOwnerApproval('replace',invalid.approval,invalid.request));
const deniedEnv={...env,PI_OWNER_SIGNER_ALLOWED_EMAILS:'other@example.test'};
const denied=new PiOwnerApprovalState({storage:new Storage()},deniedEnv);
const d=await denied.fetch(new Request('https://pi-owner.internal/initialize',{
  method:'POST',body:JSON.stringify({activation_code:activation,operator}),
}));
assert.equal(d.status,403);
console.log('Pi owner Access signer: synthetic Ed25519/Python-domain, once-only issuance, scope/replay/activation checks PASSED');
