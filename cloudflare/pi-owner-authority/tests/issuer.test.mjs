import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash,generateKeyPairSync} from 'node:crypto';
import {issueIndependentReleasePermit,issuerPublicIdentity} from '../src/independent_release_issuer.mjs';
import {scheduledRootPermit} from '../src/scheduled_root_permit.js';
const {privateKey:key}=generateKeyPairSync('ed25519');
const {privateKey:root}=generateKeyPairSync('ed25519');
const identity=issuerPublicIdentity(key), rootFingerprint=issuerPublicIdentity(root).sha256;
const env={PI_OWNER_SCHEDULED_ROOT_ENABLED:'1',PI_OWNER_SIGNER_ENABLED:'1',PI_OWNER_NORMAL_RELEASE_ENABLED:'1',PI_OWNER_RELEASE_ISSUER_SPKI_B64:identity.spki_b64,PI_OWNER_RELEASE_ISSUER_SHA256:identity.sha256,PI_OWNER_ENROLLED_PUB_SHA256:rootFingerprint};
const now=Date.now(), iso=t=>new Date(t).toISOString().replace(/\.\d{3}Z$/,'Z');
function fixture(n='1',gen='r'+'a'.repeat(12)){
  const source=n.repeat(40), priorSource='b'.repeat(40), predecessor='r'+'c'.repeat(12);
  const manifestBytes=Buffer.from(JSON.stringify({schema:'commandcenter.pi.release_artifact.v1',source_repo:'XoticHaze/CommandCenter',source_sha:source,source_ref:'main',expected_release:gen,file_count:23,files:Object.fromEntries(Array.from({length:23},(_,i)=>['file'+i,'d'.repeat(40)]))}));
  const digest=createHash('sha256').update(manifestBytes).digest('hex'),request_id='ccpi2-'+digest+'-'+n.repeat(16);
  const request={schema:'commandcenter.pi.release_request.v1',node_id:'cc-pi4',action:'pi.release.apply',source_repo:'XoticHaze/CommandCenter',source_sha:source,expected_release:gen,request_id,created_at:iso(now-2000),expires_at:iso(now+300000)};
  const review={schema:'commandcenter.pi.independent_release_review.v1',review_id:n.repeat(32),request_id,source_sha:source,manifest_sha256:digest,expected_release:gen,not_before:iso(now-3000),expires_at:iso(now+600000)};
  const priorRequest={schema:request.schema,node_id:'cc-pi4',action:request.action,source_repo:request.source_repo,request_id:'prior-request-'+n,source_sha:priorSource,expected_release:predecessor};
  const priorReceipt={schema:'commandcenter.pi.release_result.v1',node_id:'cc-pi4',action:request.action,request_id:priorRequest.request_id,source_sha:priorSource,predecessor,status:'passed',replay_allowed:false,message:'exact main source accepted; new generation '+gen};
  return {request,review,manifestBytes,priorRequest,priorReceipt,key,rootFingerprint};
}
test('two distinct reviews signed and verified by exact Worker source, same issuer configuration',async()=>{for(const n of ['1','2']){const a=fixture(n);const e=issueIndependentReleasePermit(a,now);assert.deepEqual(await scheduledRootPermit(env,a.request,e,now),e.permit);assert.deepEqual(issueIndependentReleasePermit(a,now),e);}});
test('missing review, tampered digest, expired review, wrong predecessor, wrong key all fail closed',()=>{const a=fixture();for(const patch of [{review:null},{manifestBytes:Buffer.from('changed')},{review:{...a.review,expires_at:iso(now-1)}},{priorReceipt:{...a.priorReceipt,status:'indeterminate'}},{priorReceipt:{...a.priorReceipt,message:'exact main source accepted; new generation r000000000000'}},{rootFingerprint:identity.sha256}])assert.throws(()=>issueIndependentReleasePermit({...a,...patch},now));});
test('Worker denies forged envelope, cross-request reuse, disabled service and root-key confusion',async()=>{const a=fixture(),b=fixture('2'),e=issueIndependentReleasePermit(a,now);for(const [v,r,p] of [[env,a.request,{...e,signature_b64:Buffer.alloc(64).toString('base64')}],[env,b.request,e],[{...env,PI_OWNER_SCHEDULED_ROOT_ENABLED:'0'},a.request,e],[{...env,PI_OWNER_ENROLLED_PUB_SHA256:identity.sha256},a.request,e]])await assert.rejects(scheduledRootPermit(v,r,p,now));});
