// Execute only in the independently admitted release-review custody, never a Git runner with a production key.
import {createHash, createPublicKey, sign} from 'node:crypto';
const HEX40=/^[a-f0-9]{40}$/;
const HEX64=/^[a-f0-9]{64}$/;
const GEN=/^r[a-f0-9]{12}$/;
const ID=/^[a-f0-9]{32}$/;
const RID=/^ccpi2-([a-f0-9]{64})-[a-f0-9]{16}$/;
const UTC=/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$/;
const schema='commandcenter.pi.independent_release_permit.v1';
const canonical=p=>JSON.stringify(Object.fromEntries(Object.keys(p).sort().map(k=>[k,p[k]])))+'\n';
const hash=b=>createHash('sha256').update(b).digest('hex');
function need(ok,code){if(!ok)throw Error(code);}
function exact(obj,fields){return obj&&typeof obj==='object'&&!Array.isArray(obj)&&Object.keys(obj).length===fields.length&&fields.every(k=>Object.hasOwn(obj,k));}
function timestamp(v){need(typeof v==='string'&&UTC.test(v),'timestamp_shape');const t=Date.parse(v);need(Number.isFinite(t)&&new Date(t).toISOString()===v.replace('Z','.000Z'),'timestamp_invalid');return t;}
// A protected reviewer may approve an exact immutable artifact before a fresh request exists.
// The same review ID is retained as the one-use permit ID; never infer approval from Git.
export function bindReviewedManifest(request,review,now=Date.now()){
  const r=request,a=review;
  need(exact(a,['schema','review_id','source_sha','manifest_sha256','expected_release','not_before','expires_at'])&&a.schema==='commandcenter.pi.independent_manifest_review.v1'&&typeof a.review_id==='string'&&ID.test(a.review_id)&&typeof a.manifest_sha256==='string'&&HEX64.test(a.manifest_sha256)&&typeof a.source_sha==='string'&&HEX40.test(a.source_sha)&&typeof a.expected_release==='string'&&GEN.test(a.expected_release),'manifest_review_invalid');
  need(exact(r,['schema','node_id','request_id','action','source_repo','source_sha','expected_release','created_at','expires_at'])&&r.schema==='commandcenter.pi.release_request.v1'&&r.node_id==='cc-pi4'&&r.action==='pi.release.apply'&&r.source_repo==='XoticHaze/CommandCenter'&&typeof r.request_id==='string'&&RID.test(r.request_id)&&RID.exec(r.request_id)[1]===a.manifest_sha256&&r.source_sha===a.source_sha&&r.expected_release===a.expected_release,'manifest_review_mismatch');
  const start=timestamp(r.created_at),end=timestamp(r.expires_at),aStart=timestamp(a.not_before),aEnd=timestamp(a.expires_at);
  need(start<=now&&end>now&&end>start&&end-start<=600000&&aStart<=now&&aEnd>now&&end<=aEnd&&aEnd-aStart<=86400000,'manifest_review_not_fresh');
  return {schema:'commandcenter.pi.independent_release_review.v1',review_id:a.review_id,request_id:r.request_id,source_sha:a.source_sha,manifest_sha256:a.manifest_sha256,expected_release:a.expected_release,not_before:a.not_before,expires_at:a.expires_at};
}
export function issuerPublicIdentity(key){
  need(key?.type==='private'&&key.asymmetricKeyType==='ed25519','issuer_key_invalid');
  const spki=createPublicKey(key).export({format:'der',type:'spki'});
  return {spki_b64:spki.toString('base64'),sha256:hash(spki)};
}
export function issueIndependentReleasePermit({request,review,manifestBytes,priorRequest,priorReceipt,key,rootFingerprint},now=Date.now()){
  const r=request, a=review;
  need(exact(r,['schema','node_id','request_id','action','source_repo','source_sha','expected_release','created_at','expires_at'])&&r.schema==='commandcenter.pi.release_request.v1'&&r.node_id==='cc-pi4'&&r.action==='pi.release.apply'&&r.source_repo==='XoticHaze/CommandCenter'&&HEX40.test(r.source_sha)&&GEN.test(r.expected_release)&&RID.test(r.request_id),'proposal_invalid');
  const start=timestamp(r.created_at),end=timestamp(r.expires_at);
  need(start<=now&&end>now&&end>start&&end-start<=600000,'proposal_not_fresh');
  // Review MUST come from the protected independent reviewer, never a Git proposal or caller-supplied assertion.
  need(exact(a,['schema','review_id','request_id','source_sha','manifest_sha256','expected_release','not_before','expires_at'])&&a.schema==='commandcenter.pi.independent_release_review.v1'&&ID.test(a.review_id)&&HEX64.test(a.manifest_sha256)&&a.request_id===r.request_id&&a.source_sha===r.source_sha&&a.expected_release===r.expected_release&&RID.exec(r.request_id)[1]===a.manifest_sha256,'review_mismatch');
  const aStart=timestamp(a.not_before),aEnd=timestamp(a.expires_at);
  need(aStart<=now&&aEnd>now&&end<=aEnd&&aEnd-aStart<=86400000,'review_not_fresh');
  need(Buffer.isBuffer(manifestBytes)&&manifestBytes.length>0&&manifestBytes.length<=20000&&hash(manifestBytes)===a.manifest_sha256,'manifest_digest_mismatch');
  const m=JSON.parse(manifestBytes.toString('utf8'));
  need(exact(m,['schema','source_repo','source_sha','source_ref','expected_release','file_count','files'])&&m.schema==='commandcenter.pi.release_artifact.v1'&&m.source_repo===r.source_repo&&m.source_sha===r.source_sha&&m.source_ref==='main'&&m.expected_release===r.expected_release&&m.files&&typeof m.files==='object'&&!Array.isArray(m.files)&&m.file_count===Object.keys(m.files).length&&m.file_count>=23&&m.file_count<=80&&Object.values(m.files).every(x=>typeof x==='string'&&HEX40.test(x)),'manifest_identity_mismatch');
  const p=priorReceipt, q=priorRequest;
  need(q?.schema==='commandcenter.pi.release_request.v1'&&q.node_id==='cc-pi4'&&q.action==='pi.release.apply'&&q.source_repo===r.source_repo&&HEX40.test(q.source_sha)&&GEN.test(q.expected_release)&&q.request_id!==r.request_id&&p?.schema==='commandcenter.pi.release_result.v1'&&p.node_id==='cc-pi4'&&p.action==='pi.release.apply'&&p.request_id===q.request_id&&p.source_sha===q.source_sha&&p.predecessor===q.expected_release&&p.status==='passed'&&p.replay_allowed===false&&p.message==='exact main source accepted; new generation '+r.expected_release,'prior_terminal_unverified');
  const identity=issuerPublicIdentity(key);
  need(HEX64.test(rootFingerprint)&&identity.sha256!==rootFingerprint,'issuer_must_be_distinct');
  // The review ID is the one-use permit ID. The signer atomically consumes it.
  const permit={schema:'commandcenter.pi.scheduled_root_permit.v2',permit_id:a.review_id,request_id:r.request_id,manifest_sha256:a.manifest_sha256,source_sha:r.source_sha,expected_release:r.expected_release,not_before:a.not_before,expires_at:r.expires_at};
  const signature=sign(null,Buffer.from(schema+'\0'+canonical(permit)),key).toString('base64');
  return {schema,permit,signature_b64:signature};
}
