// Fixed command for a separately admitted, protected release-review executor.
// Do not install on cc-pi4, public compute, or a Git-controlled runner.
import {constants,closeSync,fstatSync,fsyncSync,lstatSync,openSync,readFileSync,writeFileSync} from 'node:fs';
import {createHash,createPrivateKey} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {bindReviewedManifest,issueIndependentReleasePermit,issuerPublicIdentity} from './independent_release_issuer.mjs';
const ROOT='/var/lib/commandcenter/pi-release-issuer';
const REPO='repos/XoticHaze/CommandCenter-gate-control/contents/';
const INBOX='pi-node-inbox',OUTBOX='pi-node-outbox',ARTIFACT='pi-node-release-artifacts';
const PERMIT='pi-node/root-release-permit.json';
function need(ok,code){if(!ok)throw Error(code);}
function privateDir(path){const s=lstatSync(path);need(s.isDirectory()&&s.uid===process.getuid()&&(s.mode&0o077)===0,'protected_directory_required');}
function privateFile(path,max){const fd=openSync(path,constants.O_RDONLY|constants.O_NOFOLLOW);try{const s=fstatSync(fd);need(s.isFile()&&s.uid===process.getuid()&&(s.mode&0o077)===0&&s.nlink===1&&s.size>0&&s.size<=max,'protected_file_required');return readFileSync(fd);}finally{closeSync(fd);}}
function gh(path,put=null,allowMissing=false){
  const args=['api','-H','Accept: application/vnd.github+json',path];
  if(put)args.push('--method','PUT','--input','-');
  try{return JSON.parse(execFileSync('gh',args,{input:put?JSON.stringify(put):undefined,encoding:'utf8',stdio:['pipe','pipe','pipe'],timeout:30000,maxBuffer:2000000}));}
  catch(e){if(allowMissing&&e.status!==0&&/HTTP 404\b/.test(String(e.stderr)))return null;throw Error('github_transport_failed');}
}
function blob(path,branch,max,missing=false){const d=gh(REPO+path+'?ref='+branch,null,missing);if(!d)return null;
  need(d.encoding==='base64'&&typeof d.content==='string'&&Number.isInteger(d.size)&&d.size>0&&d.size<=max,'queue_blob_shape');
  const raw=Buffer.from(d.content.replace(/\s/g,''),'base64');
  need(raw.length===d.size&&createHash('sha1').update('blob '+raw.length+'\0').update(raw).digest('hex')===d.sha,'queue_blob_integrity');
  return {raw,sha:d.sha};}
function parse(file){return JSON.parse(file.raw.toString('utf8'));}
function canonical(doc){return JSON.stringify(doc)+'\n';}
// A review can bind to only one request, including across queue replacement or expiry.
// On uncertain publication, only the same request may resume; a partial journal fails closed.
function bindOnce(review,request){
  need(/^[a-f0-9]{32}$/.test(review.review_id),'review_id_invalid');
  const dir=ROOT+'/review-bindings';privateDir(dir);
  const path=dir+'/'+review.review_id+'.json';
  const request_sha256=createHash('sha256').update(canonical(Object.fromEntries(Object.keys(request).sort().map(k=>[k,request[k]])))).digest('hex');
  const raw=Buffer.from(canonical({review_id:review.review_id,request_id:request.request_id,manifest_sha256:review.manifest_sha256,request_sha256}));
  let fd;
  try{fd=openSync(path,constants.O_WRONLY|constants.O_CREAT|constants.O_EXCL|constants.O_NOFOLLOW,0o600);}
  catch(e){if(e.code!=='EEXIST')throw e;need(privateFile(path,4096).equals(raw),'review_already_bound');return;}
  try{writeFileSync(fd,raw);fsyncSync(fd);}finally{closeSync(fd);}
  const dfd=openSync(dir,constants.O_RDONLY|constants.O_DIRECTORY|constants.O_NOFOLLOW);
  try{fsyncSync(dfd);}finally{closeSync(dfd);}
  need(privateFile(path,4096).equals(raw),'review_binding_unverified');
}

function main(){
  need(process.argv.length===3&&['--public-identity','--poll'].includes(process.argv[2]),'fixed_command_required');
  need(!process.env.GITHUB_ACTIONS&&!process.env.CI&&process.platform==='linux'&&typeof process.getuid==='function','independent_executor_required');
  privateDir(ROOT);
  const key=createPrivateKey(privateFile(ROOT+'/issuer-key.pem',8192));
  const identity=issuerPublicIdentity(key);
  const rootFingerprint=privateFile(ROOT+'/pi-root-fingerprint',256).toString('ascii').trim();
  need(/^[a-f0-9]{64}$/.test(rootFingerprint)&&rootFingerprint!==identity.sha256,'distinct_root_fingerprint_required');
  if(process.argv[2]==='--public-identity'){console.log(JSON.stringify({schema:'commandcenter.pi.independent_issuer_public_identity.v1',...identity}));return;}
  privateDir(ROOT+'/reviews');
  const proposal=blob('pi-node/root-release-proposal.json',INBOX,4096,true);
  if(!proposal){console.log('NO_PROPOSAL');return;}
  const request=parse(proposal);
  need(/^ccpi2-[a-f0-9]{64}-[a-f0-9]{16}$/.test(request.request_id)&&/^[a-f0-9]{40}$/.test(request.source_sha),'proposal_identity');
  // The local file is produced by the independently admitted reviewer, not from Git.
  let review;
  try{review=JSON.parse(privateFile(ROOT+'/reviews/'+request.request_id+'.json',4096));}
  catch(e){
    if(e.code!=='ENOENT')throw e;
    // Only a protected local exact-manifest review can substitute for a per-request review.
    const digest=request.request_id.slice(6,70);
    try{privateDir(ROOT+'/manifest-reviews');review=bindReviewedManifest(request,JSON.parse(privateFile(ROOT+'/manifest-reviews/'+digest+'.json',4096)));}
    catch(m){if(m.code==='ENOENT'){console.log('NO_INDEPENDENT_REVIEW');return;}throw m;}
  }
  const prior=blob('pi-node/release-request.json',INBOX,4096),priorRequest=parse(prior);
  if(priorRequest.request_id===request.request_id){console.log('ALREADY_DISPATCHED_NO_REPLAY');return;}
  need(/^[A-Za-z0-9._:-]{6,100}$/.test(priorRequest.request_id),'prior_identity');
  const priorReceipt=parse(blob('pi-node/release-results/'+priorRequest.request_id+'.json',OUTBOX,8192));
  const manifest=blob('pi-node/artifacts/ccpi-update-'+request.source_sha.slice(0,12)+'/manifest.json',ARTIFACT,20000);
  const envelope=issueIndependentReleasePermit({request,review,manifestBytes:manifest.raw,priorRequest,priorReceipt,key,rootFingerprint});
  const old=blob(PERMIT,INBOX,2048,true);
  if(old){const existing=parse(old);if(canonical(existing)===canonical(envelope)){bindOnce(review,request);console.log('EXACT_PERMIT_ALREADY_PUBLISHED');return;}
    need(existing.schema===envelope.schema&&existing.permit?.request_id!==request.request_id&&existing.permit?.permit_id!==envelope.permit.permit_id&&Number.isFinite(Date.parse(existing.permit?.expires_at))&&Date.parse(existing.permit.expires_at)<=Date.now()-120000,'permit_slot_occupied_or_replay');}
  // Recheck the proposal and prior request immediately before CAS. No executable request is written here.
  need(blob('pi-node/root-release-proposal.json',INBOX,4096).sha===proposal.sha&&blob('pi-node/release-request.json',INBOX,4096).sha===prior.sha,'queue_changed');
  bindOnce(review,request);
  const raw=Buffer.from(canonical(envelope));
  const put={branch:INBOX,message:'Independent exact Pi release permit [skip ci]',content:raw.toString('base64')};if(old)put.sha=old.sha;
  const result=gh(REPO+PERMIT,put),observed=blob(PERMIT,INBOX,2048);
  need(result.content?.sha===observed.sha&&observed.raw.equals(raw),'permit_publish_unverified');
  console.log(JSON.stringify({schema:'commandcenter.pi.independent_permit_publish_receipt.v1',request_id:request.request_id,permit_id:envelope.permit.permit_id,permit_blob:observed.sha,issuer_sha256:identity.sha256,root_dispatch_claimed:false}));
}
try{main();}catch(e){const m=String(e.message||'');console.error('ISSUER_HELD='+(/^[a-z_]{1,100}$/.test(m)?m:'protected_operation_failed'));process.exitCode=1;}
