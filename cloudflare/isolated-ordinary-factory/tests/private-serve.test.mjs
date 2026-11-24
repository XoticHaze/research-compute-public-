import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {build} from '../scripts/prepare.mjs';
const account='ab'.repeat(16), workerId='1'.repeat(32), factoryId='2'.repeat(32);
const version='12345678-1234-1234-1234-123456789abc', deployment='22345678-1234-1234-1234-123456789abc', appId='32345678-1234-1234-1234-123456789abc';
const owner='owner@example.invalid', access='test-access-secret-not-real', workers='test-workers-secret-not-real';
const name='cc-app-example', url='https://'+name+'.cc-ordinary-deployments.workers.dev';
const source=Buffer.from('export default {fetch(){return new Response("fixture");}};');
const req={operation:'existing_worker.ordinary_version.serve_private',worker_name:name,worker_id:workerId,version_id:version,source_commit:'a'.repeat(40),source_sha256:createHash('sha256').update(source).digest('hex')};
const env={FACTORY_ACCOUNT_ID:account,FACTORY_SCRATCH_RELEASE_ENABLED:'1',FACTORY_WORKERS_ADMIN:workers,FACTORY_ACCESS_ADMIN:{get:async()=>access},FACTORY_ALLOWED_EMAILS:owner,FACTORY_ACCESS_AUD:'e'.repeat(64)};
const app={id:appId,type:'self_hosted',aud:'d'.repeat(64),destinations:[{type:'all_workers'}]};
const factory={id:'42345678-1234-1234-1234-123456789abc',aud:env.FACTORY_ACCESS_AUD,destinations:[{type:'worker',worker_id:factoryId}]};
async function fixture(fn){
 const dir=mkdtempSync(join(tmpdir(),'cc-private-serve-'));
 try{build(account,{outDir:dir});const mod=await import(pathToFileURL(join(dir,'src','scratch_stage.js')).href);const policy=await import(pathToFileURL(join(dir,'src','policy.js')).href);await fn(mod.servePrivateVersion,policy);}
 finally{rmSync(dir,{recursive:true,force:true});}
}
function mock({edge=302,override=false,already=false}={}){
 let enabled=already;
 const calls=[];
 const fetcher=async(target,init)=>{
  const method=init.method, path=target.replace('https://api.cloudflare.com/client/v4/accounts/'+account,'');
  calls.push({path,method,body:init.body});
  assert.equal(init.redirect,'manual');
  if(target.startsWith(url)){
   assert.equal(init.headers.authorization,undefined);
   return new Response(null,{status:edge,headers:edge===302?{location:'https://test.cloudflareaccess.com/cdn-cgi/access/login/test?opaque=secret'}:{}});
  }
  const isAccess=path.startsWith('/access/');
  assert.equal(init.headers.authorization,'Bearer '+(isAccess?access:workers));
  let result;
  if(path==='/workers/workers/'+workerId){
   if(method==='PATCH'){
    const body=JSON.parse(init.body);
    assert.equal(body.subdomain.previews_enabled,false);
    enabled=body.subdomain.enabled;
   }
   result={id:workerId,name,tags:['cc-ordinary-factory-managed-v1'],subdomain:{url,enabled,previews_enabled:false}};
  }else if(path==='/workers/workers/'+workerId+'/versions/'+version+'?include=modules'){
   result={id:version,main_module:'worker.mjs',compatibility_date:'2026-11-18',bindings:[],env:{},modules:[{name:'worker.mjs',content_type:'application/javascript+module',content_base64:source.toString('base64')}]};
  }else if(path==='/workers/scripts/'+name+'/deployments'){
   result={deployments:[{id:deployment,created_on:'2026-11-24T00:00:00Z',versions:[{version_id:version,percentage:100}]}]};
  }else if(path==='/access/apps?page=1&per_page=100'){
   result=override?[app,factory,{id:'52345678-1234-1234-1234-123456789abc',destinations:[{type:'worker',worker_id:workerId}]}]:[app,factory];
  }else if(path==='/access/apps/'+appId){result=app;}
  else if(path==='/access/apps/'+appId+'/policies?page=1&per_page=100'){result=[{decision:'allow',include:[{email:{email:owner}}],exclude:[],require:[]}];}
  else throw Error('unexpected_request');
  return Response.json({success:true,result});
 };
 return {calls,fetcher,enabled:()=>enabled};
}
test('private publication checks exact Access policy, activates and proves edge, without credentials on app requests',()=>fixture(async fn=>{
 const m=mock();const r=await fn(env,req,m.fetcher);
 assert.equal(r.status,'private_ingress_verified');assert.equal(r.anonymous_edge_verified,true);
 assert.equal(r.authorized_browser_positive_verified,false);assert.equal(m.enabled(),true);
 assert.equal(m.calls.filter(c=>c.method==='PATCH').length,1);
 assert.ok(!JSON.stringify(r).includes(owner));assert.ok(!JSON.stringify(r).includes(access));assert.ok(!JSON.stringify(r).includes('opaque'));
}));
test('more-specific target override denies without opening ingress',()=>fixture(async fn=>{
 const m=mock({override:true});const r=await fn(env,req,m.fetcher);
 assert.equal(r.status,'failed_or_indeterminate');assert.equal(r.diagnostic.category,'private_access_override_requires_review');
 assert.equal(m.calls.filter(c=>c.method==='PATCH').length,0);assert.equal(m.enabled(),false);
}));
test('generic 403 after newly enabled ingress restores closed state',()=>fixture(async fn=>{
 const m=mock({edge:403});const r=await fn(env,req,m.fetcher);
 assert.equal(r.status,'failed_or_indeterminate');assert.equal(r.ingress_closed_verified,true);
 assert.equal(m.calls.filter(c=>c.method==='PATCH').length,2);assert.equal(m.enabled(),false);
}));
test('already enabled authenticated ingress verifies without mutation',()=>fixture(async fn=>{
 const m=mock({already:true});const r=await fn(env,req,m.fetcher);
 assert.equal(r.status,'private_ingress_verified');assert.equal(r.cloudflare_mutations,0);
 assert.equal(m.calls.filter(c=>c.method==='PATCH').length,0);
}));
