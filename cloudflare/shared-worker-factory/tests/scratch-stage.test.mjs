import test from 'node:test';
import assert from 'node:assert/strict';
import {validateRequest} from '../src/policy.js';
import {stageScratchVersion} from '../src/scratch_stage.js';

const account='ce43cd7b917d98a4bb4866d30eed99c0';
const id='a'.repeat(32);
const commit='b'.repeat(40);
const name='cc-scratch-first';
const version='d9c7ca0a-e519-4e5c-9239-4b33a19bfe27';
const source='export default { async fetch(request) { return new Response("bounded test"); } };';
const digest=async(text)=>Array.from(new Uint8Array(await crypto.subtle.digest(
  'SHA-256',new TextEncoder().encode(text))),b=>b.toString(16).padStart(2,'0')).join('');
const env={FACTORY_ACCOUNT_ID:account,FACTORY_STAGE_VERSION_ENABLED:'1',
  FACTORY_WORKERS_ADMIN:{get:async()=> 'synthetic-locally-verified-placeholder'}};
const contract=async()=>({
 schema:'commandcenter.cloudflare.factory_request.v1',
 operation:'existing_worker.scratch_version.stage',request_id:'e'.repeat(32),
 worker_name:name,worker_id:id,expires_at:Math.floor(Date.now()/1000)+100,
 source_commit:commit,source_sha256:await digest(source)
});
function mockCall(sourceText=source) {
 const calls=[];
 const fetcher=async(url,opts)=>{
   const u=String(url);calls.push({url:u,opts});
   if(u.endsWith('/workers/workers/'+id)) {
     assert.equal(opts.method,'GET');
     return new Response(JSON.stringify({success:true,result:{id,name}}),{
       status:200,headers:{'content-type':'application/json'}});
   }
   if(u==='https://raw.githubusercontent.com/XoticHaze/research-compute-public-/'+commit+
     '/cloudflare/ordinary-scratch-releases/'+name+'/worker.mjs') {
     assert.equal(opts.method,'GET');
     assert.equal(opts.redirect,'error');
     return new Response(sourceText,{status:200});
   }
   if(u.endsWith('/workers/scripts/'+name+'/versions')) {
     assert.equal(opts.method,'POST');
     assert.equal(opts.redirect,'error');
     assert.ok(opts.body instanceof FormData);
     const metadata=JSON.parse(opts.body.get('metadata'));
     assert.deepEqual(metadata,{main_module:'worker.mjs',
       compatibility_date:'2026-11-18',bindings:[]});
     assert.equal(await opts.body.get('worker.mjs').text(),sourceText);
     assert.equal(opts.body.get('worker.mjs').type,'application/javascript+module');
     return new Response(JSON.stringify({success:true,result:{id:version}}),{
       status:201,headers:{'content-type':'application/json'}});
   }
   throw Error('unexpected_network_access '+u);
 };
 return {calls,fetcher};
}
test('validated exact scratch version stage uploads single pinned module off-traffic',async()=>{
 const r=await contract();
 assert.equal(validateRequest(r),r);
 const {calls,fetcher}=mockCall();
 const receipt=await stageScratchVersion(env,r,fetcher);
 assert.equal(receipt.status,'staged_off_traffic');
 assert.equal(receipt.version_id,version);
 assert.equal(receipt.source_sha256,r.source_sha256);
 assert.equal(receipt.active_deployment_unchanged_by_api,true);
 assert.equal(receipt.live_serving_verified,false);
 assert.equal(receipt.cloudflare_mutations,1);
 assert.equal(receipt.secret_included,false);
 assert.equal(calls.length,3);
 assert.equal(calls.filter(x=>/\/deployments/.test(x.url)).length,0);
 assert.equal(calls.filter(x=>x.opts.method==='POST').length,1);
});
test('source digest mismatch denies prior to any Cloudflare upload',async()=>{
 const r=await contract();
 const {calls,fetcher}=mockCall(source+' suspicious edit');
 await assert.rejects(stageScratchVersion(env,r,fetcher),/source_digest_rejected/);
 assert.equal(calls.length,2);
 assert.equal(calls.filter(x=>x.opts.method==='POST').length,0);
});
test('rejects staging protected or production Worker even when ordinary inspect works',async()=>{
 for(const v of ['waterboys-fantasy-broker','shared-compute-worker-factory',
                  'reference-release-broker-v1','cc-shared-nvidia-inference',
                  'cc-scratch--bad','cc-scratch-x/../evil']){
   const r={...await contract(),worker_name:v};
   assert.throws(()=>validateRequest(r));
   const {calls,fetcher}=mockCall();
   await assert.rejects(stageScratchVersion(env,r,fetcher));
   assert.equal(calls.length,0);
 }
});
test('rejects malformed source pin and unknown source attributes',async()=>{
 const base=await contract();
 for(const changes of [
   {worker_id:'bad'},{source_sha256:'f'.repeat(63)},
   {source_commit:'a'.repeat(39)},{source_path:'../../broker'},
   {expires_at:Math.floor(Date.now()/1000)+3600}
 ]){
   assert.throws(()=>validateRequest({...base,...changes}));
 }
});
test('separate stage flag and account fence fail without accessing credentials',async()=>{
 const r=await contract();
 for(const e of [
   {...env,FACTORY_STAGE_VERSION_ENABLED:'0'},
   {...env,FACTORY_ACCOUNT_ID:'b'.repeat(32)},
   {...env,FACTORY_WORKERS_ADMIN:null}
 ]){
   const {calls,fetcher}=mockCall();
   await assert.rejects(stageScratchVersion(e,r,fetcher));
   assert.equal(calls.length,0);
 }
});
test('identity mismatch blocks source fetch and upload',async()=>{
 const r=await contract();
 const calls=[];
 const fetcher=async(url,opts)=>{
   calls.push(String(url));
   return new Response(JSON.stringify({success:true,
     result:{id, name:'cc-scratch-other'}}),{status:200});
 };
 await assert.rejects(stageScratchVersion(env,r,fetcher),/worker_identity_rejected/);
 assert.equal(calls.length,1);
});
test('unexpected source redirect or failed upstream cannot upload',async()=>{
 const r=await contract();
 let calls=0;
 const fetcher=async(url,opts)=>{
   calls++;
   if(calls===1)return new Response(JSON.stringify({
     success:true,result:{id,name}}),{status:200});
   return new Response('not found',{status:404});
 };
 await assert.rejects(stageScratchVersion(env,r,fetcher),/source_unavailable/);
 assert.equal(calls,2);
});
test('Cloudflare stage result without UUID is indeterminate, never promoted',async()=>{
 const r=await contract();
 const {calls,fetcher}=mockCall();
 const bad=async (url,opts)=>{
   const response=await fetcher(url,opts);
   if(opts.method==='POST')
     return new Response(JSON.stringify({success:true,result:{id:'bad'}}),{status:200});
   return response;
 };
 await assert.rejects(stageScratchVersion(env,r,bad),/version_stage_indeterminate/);
 assert.equal(calls.filter(x=>/\/deployments/.test(x.url)).length,0);
});
