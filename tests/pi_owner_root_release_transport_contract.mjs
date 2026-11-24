import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {canonicalPiJson,publishPiRootReleaseGrant,readPiRootReleaseReceipt} from '../cloudflare/operator-console/src/pi_owner_approval.js';

const now=Date.now(),date=t=>new Date(t).toISOString();
const request={
 schema:'commandcenter.pi.release_request.v1',node_id:'cc-pi4',
 request_id:'root-device-transport-test-1234',
 action:'pi.release.apply',source_repo:'XoticHaze/CommandCenter',
 source_sha:'a'.repeat(40),expected_release:'r'+'b'.repeat(12),
 created_at:date(now-1000),expires_at:date(now+260000)
};
const grant={
 schema:'commandcenter.pi.release_request_approval.v1',
 request_id:request.request_id,source_sha:request.source_sha,
 expected_release:request.expected_release,expires_at:request.expires_at,
 key_id:'ccpi-owner-bootstrap-ed25519-v1',
 signature_b64:'A'.repeat(86)+'=='
};
const sha=raw=>createHash('sha1').update(raw).digest('hex');
const saved=new Map(),writes=[],env={PI_OWNER_QUEUE_GITHUB_TOKEN:'synthetic-private-repo-token-12345'};
const original=globalThis.fetch;
globalThis.fetch=async (url,options={})=>{
 const u=new URL(url),path=u.pathname.replace('/repos/XoticHaze/CommandCenter-gate-control/contents/','');
 assert.ok(u.hostname==='api.github.com');
 if(options.method==='PUT'){
  const doc=JSON.parse(options.body),text=Buffer.from(doc.content,'base64').toString('utf8');
  assert.equal(doc.branch,'pi-node-inbox');
  assert.equal(text,canonicalPiJson(JSON.parse(text)));
  const old=saved.get(path);
  if(old)assert.equal(doc.sha,old.sha);
  else assert.equal(doc.sha,undefined);
  const file={sha:sha(text),text};
  saved.set(path,file);writes.push(path);
  return new Response(JSON.stringify({content:{sha:file.sha}}),{status:201});
 }
 const data=saved.get(path);
 if(!data)return new Response('{}',{status:404});
 return new Response(JSON.stringify({
  sha:data.sha,encoding:'base64',size:Buffer.byteLength(data.text),
  content:Buffer.from(data.text).toString('base64')
 }),{status:200});
};
try{
 const out=await publishPiRootReleaseGrant(env,request,grant);
 assert.equal(out.action,'pi.release.apply');
 assert.equal(out.root_receipt_verified,false);
 assert.deepEqual(writes,[
  'pi-node/release-signed-approval.json',
  'pi-node/release-request.json'
 ]);
 const retry=await publishPiRootReleaseGrant(env,request,grant);
 assert.equal(retry.recovered_exact_same_id,true);
 assert.equal(writes.length,2);
 const conflict={...grant,source_sha:'c'.repeat(40)};
 await assert.rejects(()=>publishPiRootReleaseGrant(env,request,conflict),
   /pi_owner_root_release_queue_occupied_or_replay/);
 const pending=await readPiRootReleaseReceipt(env,request.request_id);
 assert.equal(pending.status,'PENDING');
 const receipt={
  schema:'commandcenter.pi.release_result.v1',node_id:'cc-pi4',
  request_id:request.request_id,action:'pi.release.apply',
  status:'passed',source_sha:request.source_sha,predecessor:request.expected_release,
  finished_at:date(now+2000)
 };
 const name='pi-node/release-results/'+request.request_id+'.json';
 const text=canonicalPiJson(receipt);saved.set(name,{sha:sha(text),text});
 const result=await readPiRootReleaseReceipt(env,request.request_id);
 assert.equal(result.status,'passed');
 assert.equal(result.root_receipt_verified,true);
 assert.equal(result.active_generation_readback_verified,false);
}finally{globalThis.fetch=original}
console.log('Pi root-release signed-grant-first private queue transport and receipt projection PASS');
