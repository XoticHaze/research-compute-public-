import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {build} from '../scripts/prepare.mjs';
const account='ab'.repeat(16), id='12345678-1234-1234-1234-123456789abc', aud='d'.repeat(64);
const owner='owner@example.invalid', bearer='test-access-bearer-not-real';
const app={id,type:'self_hosted',aud,destinations:[{type:'all_workers'}]};
const factory={id:'22345678-1234-1234-1234-123456789abc',aud:'e'.repeat(64),destinations:[{type:'worker'}]};
async function fixture(fn){
 const dir=mkdtempSync(join(tmpdir(),'cc-access-runtime-'));
 try{build(account,{outDir:dir});const mod=await import(pathToFileURL(join(dir,'src','scratch_stage.js')).href);await fn(mod.verifyAccountAccess);}
 finally{rmSync(dir,{recursive:true,force:true});}
}
const env={FACTORY_ACCOUNT_ID:account,FACTORY_ACCESS_ADMIN:{get:async()=>bearer},FACTORY_ALLOWED_EMAILS:owner,FACTORY_ACCESS_AUD:factory.aud};
function transport({edge=302,policyEmail=owner,duplicate=false}={}){
 const calls=[];
 const fetcher=async(url,init)=>{
  calls.push({url,method:init.method});
  assert.equal(init.method,'GET');assert.equal(init.redirect,'manual');
  if(url.startsWith('https://api.cloudflare.com/')){
   assert.equal(init.headers.authorization,'Bearer '+bearer);
   let result;
   if(url.endsWith('/access/apps?page=1&per_page=100'))result=duplicate?[app,app,factory]:[app,factory];
   else if(url.endsWith('/policies?page=1&per_page=100'))result=[{decision:'allow',include:[{email:{email:policyEmail}}],exclude:[],require:[]}];
   else if(url.endsWith('/access/apps/'+id))result=app;
   else throw Error('unexpected_path');
   return new Response(JSON.stringify({success:true,result}),{status:200});
  }
  assert.ok(url.startsWith('https://cc-app-factory-proof.'));
  assert.equal(init.headers.authorization,undefined);
  return new Response(null,{status:edge,headers:edge===302?{location:'https://test.cloudflareaccess.com/cdn-cgi/access/login/test?opaque=secret'}:{}});
 };
 return {calls,fetcher};
}
test('exact Access policy plus anonymous challenge is read-only, no secret in receipt',()=>fixture(async fn=>{
 const {calls,fetcher}=transport();const r=await fn(env,fetcher);
 assert.equal(r.status,'access_account_policy_verified');assert.equal(r.anonymous_edge_verified,true);assert.equal(calls.length,5);
 assert.ok(!JSON.stringify(r).includes(bearer));assert.ok(!JSON.stringify(r).includes(owner));assert.ok(!JSON.stringify(r).includes('opaque'));
}));
test('generic application 403 never counts as edge authentication',()=>fixture(async fn=>{
 const {fetcher}=transport({edge:403});const r=await fn(env,fetcher);
 assert.equal(r.status,'access_account_policy_verified');assert.equal(r.anonymous_edge_verified,false);
}));
test('policy drift fails before anonymous probes',()=>fixture(async fn=>{
 const {calls,fetcher}=transport({policyEmail:'other@example.invalid'});const r=await fn(env,fetcher);
 assert.equal(r.status,'failed_or_indeterminate');assert.equal(calls.length,3);
}));
test('missing binding and duplicate default fail closed',()=>fixture(async fn=>{
 const {calls,fetcher}=transport({duplicate:true});const r=await fn({...env,FACTORY_ACCESS_ADMIN:undefined},fetcher);
 assert.equal(r.status,'failed_or_indeterminate');assert.equal(calls.length,0);
 const d=await fn(env,fetcher);assert.equal(d.status,'failed_or_indeterminate');assert.equal(calls.length,1);
}));
