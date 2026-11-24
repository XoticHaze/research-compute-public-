import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {runStaticPrivateRelease,challengeIssuer} from '../src/native-static-stage.mjs';
const account='de1c728bdb163060d946122c857f3653',worker='cc-app-static-assets-proof',id='75d882ae4da84594817608332bb35405';
const host='https://cc-app-static-assets-proof.cc-ordinary-deployments.workers.dev',proof='https://cc-app-factory-proof.cc-ordinary-deployments.workers.dev',issuer='https://fixture.cloudflareaccess.com',aud='a'.repeat(64),appId='aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';
const baseId='11111111-2222-4333-8444-555555555555',repairId='22222222-3333-4444-8555-666666666666',depId='33333333-4444-4555-8666-777777777777';
const code=readFileSync(new URL('./fixtures/native-static-proof-worker.mjs',import.meta.url));
const sha=x=>createHash('sha256').update(x).digest('hex');
const manifest={schema:'commandcenter.cloudflare.static_assets_release.v1',worker_name:worker,module_sha256:'e3d9f27fe5f70f4e5e8bdf9ff417ba613203c4e5eee193fca274d451daf8b6e8',files:[{path:'/index.html',bytes:226,sha256:'eb1d76a47afa222af1df628c5e3a73a94dd4d7aa4b27545fc79a460edf93f5c4'},{path:'/proof.txt',bytes:37,sha256:'b2e585bd3125fe4596ce8d927991abad20b45a63867c59679d803978e4af1858'}]};
const manifestBytes=JSON.stringify(manifest,null,2)+'\n';
const req={operation:'existing_worker.static_version.serve_private',worker_name:worker,worker_id:id,source_commit:'700597fed7b0dc76810347948ae080c6f6b62079',source_sha256:'6465cdf1472217ae0deffc23d2e8b378ae54858db0908c1863f73df12d613fe5',version_id:baseId};
assert.equal(sha(code),manifest.module_sha256);assert.equal(sha(manifestBytes),req.source_sha256);
const admin='fixture-admin-not-real',github='fixture-github-not-real';
const env={FACTORY_ACCOUNT_ID:account,FACTORY_INSTALLATION_ROLE:'CC_ISOLATED_ORDINARY_ONLY',FACTORY_STAGE_VERSION_ENABLED:'1',FACTORY_SCRATCH_RELEASE_ENABLED:'1',FACTORY_WORKERS_ADMIN:{get:async()=>admin},FACTORY_QUEUE_GITHUB_TOKEN:{get:async()=>github},FACTORY_ALLOWED_EMAILS:'owner@example.test'};
const tag='cc-static-private-'+sha(JSON.stringify([req.source_sha256,appId,issuer,aud]));
const cf=(r,status=200)=>Response.json({success:true,result:r},{status});
const redirect=()=>new Response(null,{status:302,headers:{location:issuer+'/cdn-cgi/access/login/fixture'}});
const base={id:baseId,annotations:{'workers/tag':'cc-static-'+req.source_sha256},main_module:'worker.mjs',modules:[{name:'worker.mjs',content_type:'application/javascript+module',content_base64:code.toString('base64')}],bindings:[{type:'assets',name:'ASSETS'}],assets:{config:{run_worker_first:true,html_handling:'none',not_found_handling:'404-page'}}};
const repair={...base,id:repairId,annotations:{'workers/tag':tag},bindings:[...base.bindings,...['ACCESS_ISSUER','ACCESS_AUD','ACCESS_ALLOWED_EMAILS_JSON'].map(name=>({name,type:'secret_text'}))]};
function fake({already=false,edgeFails=false,wrongLatest=false,drift=false}={}){
 let made=already,active=already,opened=already,checks=0;const writes=[];
 const readAccess=async(_env,_fetcher,_d,_req)=>({id:drift&&++checks>2?'bbbbbbbb-cccc-4ddd-8eee-ffffffffffff':appId,aud});
 const fetcher=async(url,opt)=>{
  assert.equal(opt.redirect,'manual');
  if(url.startsWith('https://api.github.com/')){
   assert.equal(opt.headers.authorization,'Bearer '+github);
   assert.ok(url.endsWith('?ref='+req.source_commit));
   if(url.includes('/release.json?'))return new Response(manifestBytes);
   if(url.includes('/worker.mjs?'))return new Response(code);
   assert.fail('unexpected source '+url);
  }
  if(url.startsWith(proof)||url.startsWith(host)){
   assert.equal(opt.headers.authorization,undefined);
   return url.startsWith(host)&&edgeFails?new Response('unexpected',{status:200}):redirect();
  }
  assert.ok(url.startsWith('https://api.cloudflare.com/client/v4/accounts/'+account+'/'));
  assert.equal(opt.headers.authorization,'Bearer '+admin);
  if(opt.method!=='GET')writes.push({url,method:opt.method});
  const w={id,name:worker,tags:['cc-ordinary-factory-managed-v1'],subdomain:{url:host,enabled:opened,previews_enabled:false}};
  if(url.endsWith('/workers/workers/'+id)){
    if(opt.method==='PATCH'){opened=JSON.parse(opt.body).subdomain.enabled;return cf(w);}
    return cf(w);
  }
  if(url.endsWith('/deployments')){
    if(opt.method==='POST'){assert.equal(JSON.parse(opt.body).versions[0].version_id,repairId);active=true;return cf({id:depId},201);}
    return cf({deployments:active?[{id:depId,created_on:'2026-11-24T00:00:00Z',versions:[{version_id:repairId,percentage:100}]}]:[]});
  }
  if(url.endsWith('/versions?page=1&per_page=100'))return cf(made?[base,repair]:[base]);
  if(url.endsWith('/versions/latest?include=modules'))return cf(wrongLatest?repair:base);
  if(url.endsWith('/versions/latest')){
    assert.equal(opt.method,'PATCH');assert.equal(opt.headers['content-type'],'application/merge-patch+json');
    const body=JSON.parse(opt.body);assert.deepEqual(Object.keys(body).sort(),['annotations','env']);assert.equal(body.annotations['workers/tag'],tag);
    assert.equal(body.env.ACCESS_ISSUER.text,issuer);assert.equal(body.env.ACCESS_AUD.text,aud);
    made=true;return cf({id:repairId});
  }
  if(url.endsWith('/versions/'+baseId+'?include=modules'))return cf(base);
  if(url.endsWith('/versions/'+repairId+'?include=modules'))return cf(repair);
  assert.fail('unexpected provider path '+url);
 };
 return {fetcher,readAccess,writes,isOpened:()=>opened};
}
test('first private static release repairs bindings, promotes exact version, opens protected ingress',async()=>{
 const f=fake();const r=await runStaticPrivateRelease(env,req,f.readAccess,f.fetcher);
 assert.equal(r.status,'private_ingress_verified',JSON.stringify(r));assert.equal(r.version_id,repairId);
 assert.equal(r.anonymous_edge_verified,true);assert.equal(r.asset_bytes_served_verified,false);assert.equal(r.authorized_browser_positive_verified,false);
 assert.equal(f.writes.length,3);assert.equal(f.isOpened(),true);assert.equal(r.bearer_returned,false);
 assert.ok(!JSON.stringify(r).includes(admin));assert.ok(!JSON.stringify(r).includes('owner@example.test'));
});
test('exact repair and deployment reconcile without repeating writes',async()=>{
 const f=fake({already:true});const r=await runStaticPrivateRelease(env,req,f.readAccess,f.fetcher);
 assert.equal(r.status,'private_ingress_verified',JSON.stringify(r));assert.equal(f.writes.length,0);
});
test('failed anonymous edge check restores closed ingress',async()=>{
 const f=fake({edgeFails:true});const r=await runStaticPrivateRelease(env,req,f.readAccess,f.fetcher);
 assert.equal(r.status,'failed_or_indeterminate');assert.equal(r.ingress_closed_verified,true);assert.equal(f.isOpened(),false);
});
test('foreign target, latest drift and access drift fail before unsafe promotion',async()=>{
 for(const [q,opt] of [[{...req,worker_id:'f'.repeat(32)},{}],[req,{wrongLatest:true}],[req,{drift:true}]]){
  const f=fake(opt),r=await runStaticPrivateRelease(env,q,f.readAccess,f.fetcher);
  assert.equal(r.status,'failed_or_indeterminate');assert.equal(f.writes.some(x=>x.url.endsWith('/deployments')),false);assert.equal(f.isOpened(),false);
 }
});
test('only exact HTTPS Cloudflare Access challenge accepted',()=>{
 assert.equal(challengeIssuer(redirect()),issuer);
 for(const location of ['https://evil.example.test/cdn-cgi/access/login/fixture','http://fixture.cloudflareaccess.com/cdn-cgi/access/login/fixture','https://fixture.cloudflareaccess.com/other'])assert.throws(()=>challengeIssuer(new Response(null,{status:302,headers:{location}})));
});
