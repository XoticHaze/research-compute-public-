import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {mkdtempSync,rmSync,readFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {build} from '../scripts/prepare.mjs';
import {runStaticVersion} from '../src/native-static-stage.mjs';
const ACCOUNT='de1c728bdb163060d946122c857f3653',TARGET='cc-app-static-assets-proof',ID='a'.repeat(32);
const version='11111111-2222-4333-8444-555555555555',commit='b'.repeat(40);
const admin='fixture-admin-not-a-real-token',github='fixture-github-not-a-real-token',jwt='fixture.completion.token';
const sha=b=>createHash('sha256').update(b).digest('hex'),encode=x=>new TextEncoder().encode(x);
const html=encode('<html>private static fixture</html>');
const code=encode('export default {fetch(){return new Response(null,{status:403})}}');
const manifest={schema:'commandcenter.cloudflare.static_assets_release.v1',worker_name:TARGET,module_sha256:sha(code),files:[{path:'/index.html',bytes:html.length,sha256:sha(html)}]};
const data=encode(JSON.stringify(manifest));
const req={schema:'commandcenter.cloudflare.factory_request.v1',operation:'existing_worker.static_version.stage',request_id:'c'.repeat(32),worker_name:TARGET,worker_id:ID,source_commit:commit,source_sha256:sha(data),expires_at:Math.floor(Date.now()/1000)+180};
const env={FACTORY_ACCOUNT_ID:ACCOUNT,FACTORY_INSTALLATION_ROLE:'CC_ISOLATED_ORDINARY_ONLY',FACTORY_STAGE_VERSION_ENABLED:'1',FACTORY_SCRATCH_RELEASE_ENABLED:'1',FACTORY_WORKERS_ADMIN:{get:async()=>admin},FACTORY_QUEUE_GITHUB_TOKEN:{get:async()=>github}};
const result=(r,status=200)=>new Response(JSON.stringify({success:true,result:r}),{status});
function fake({existing=false,ingress=false,badVersion=false,versionReadbackMissing=false,badManifest=false,duplicate=false}={}){
  const calls=[];let created=existing;
  const tag={'workers/tag':'cc-static-'+req.source_sha256};
  const fetcher=async(url,opt)=>{
    calls.push({url,method:opt.method});
    assert.equal(opt.redirect,'manual');
    if(url.startsWith('https://api.github.com/')){
      assert.equal(opt.headers.authorization,'Bearer '+github);assert.ok(url.endsWith('?ref='+commit));
      if(url.includes('/release.json?'))return new Response(badManifest?encode('{}'):data);
      if(url.includes('/worker.mjs?'))return new Response(code);
      if(url.includes('/assets/index.html?'))return new Response(html);
      assert.fail('unexpected GitHub source path');
    }
    assert.ok(url.startsWith('https://api.cloudflare.com/client/v4/accounts/'+ACCOUNT+'/'));
    assert.equal(opt.headers.authorization,'Bearer '+admin);
    if(url.endsWith('/workers/workers/'+ID))return result({id:ID,name:TARGET,tags:['cc-ordinary-factory-managed-v1'],subdomain:{enabled:ingress,previews_enabled:false}});
    if(url.endsWith('/deployments'))return result({deployments:[]});
    if(url.includes('/versions?page=1'))return result(duplicate?[{id:version,annotations:tag},{id:version,annotations:tag}]:created?[{id:version,annotations:tag}]:[]);
    if(url.endsWith('/assets-upload-session'))return result({jwt,buckets:[]});
    if(url.endsWith('/versions?deploy=false')){
      assert.equal(opt.method,'POST');const v=JSON.parse(opt.body);assert.equal(v.assets.jwt,jwt);assert.equal(v.assets.config.run_worker_first,true);
      assert.equal(v.annotations['workers/tag'],tag['workers/tag']);created=true;return result({id:version},201);
    }
    if(url.endsWith('/versions/'+version+'?include=modules'))return result({id:version,annotations:tag,main_module:'worker.mjs',modules:[{name:'worker.mjs',content_type:'application/javascript+module',content_base64:Buffer.from(badVersion?encode('bad code'):code).toString('base64')}],bindings:[{name:'ASSETS',type:'assets'}],...(versionReadbackMissing?{}:{assets:{config:{run_worker_first:true,html_handling:'none',not_found_handling:'404-page'}}})});
    assert.fail('unexpected Cloudflare path '+url);
  };
  return {fetcher,calls};
}
test('real generated dispatcher/policy registers bounded stage and verify, with existing flags',async()=>{
  const d=mkdtempSync(join(tmpdir(),'cc-static-policy-'));
  try{
    build(ACCOUNT,{outDir:d});
    const ix=readFileSync(join(d,'src','index.js'),'utf8');
    assert.match(ix,/runStaticVersion\(env,req\)/);assert.match(ix,/staticRelease/);
    const p=await import(pathToFileURL(join(d,'src','policy.js')).href);
    assert.equal(p.validateRequest(req).operation,req.operation);
    assert.equal(p.validateRequest({...req,operation:'existing_worker.static_version.verify',version_id:version}).version_id,version);
    for(const patch of [{worker_name:'cc-app-agent-fabric'},{worker_id:'bad'},{source_sha256:'bad'},{asset_path:'arbitrary'}])
      assert.throws(()=>p.validateRequest({...req,...patch}));
    assert.equal(readFileSync(join(d,'src','native-static-stage.mjs'),'utf8').includes('runStaticVersion'),true);
  }finally{rmSync(d,{recursive:true,force:true});}
});
test('stage uses exact private commit, verifies module and Worker-first config, leaves ingress closed',async()=>{
  const {fetcher,calls}=fake();
  const out=await runStaticVersion(env,req,fetcher);
  assert.equal(out.status,'staged_off_traffic',JSON.stringify(out));
  assert.equal(out.version_id,version);assert.equal(out.worker_first_verified,true);
  assert.equal(out.asset_bytes_served_verified,false);assert.equal(out.public_ingress_enabled,false);
  assert.equal(calls.filter(x=>x.method==='POST').length,2);
  assert.ok(!JSON.stringify(out).includes(jwt));assert.ok(!JSON.stringify(out).includes(admin));
});
test('same manifest reconciliation avoids duplicate upload; exact verify is GET-only',async()=>{
  for(const op of [req,{...req,operation:'existing_worker.static_version.verify',version_id:version}]){
    const {fetcher,calls}=fake({existing:true});
    const out=await runStaticVersion(env,op,fetcher);
    assert.equal(out.status,op===req?'staged_off_traffic':'version_verified',JSON.stringify(out));
    assert.equal(calls.some(x=>x.method!=='GET'),false);
  }
});
test('wrong account, closed flags, active ingress or ambiguous versions fail before mutation',async()=>{
  for(const [e,options] of [[{...env,FACTORY_ACCOUNT_ID:'c'.repeat(32)},{}],[{...env,FACTORY_STAGE_VERSION_ENABLED:'0'},{}],[env,{ingress:true}],[env,{duplicate:true}],[env,{badManifest:true}]]){
    const {fetcher,calls}=fake(options);
    const out=await runStaticVersion(e,req,fetcher);
    assert.equal(out.status,'failed_or_indeterminate');assert.equal(out.diagnostic.mutation_attempted,false);
    assert.equal(calls.some(x=>x.method!=='GET'),false);
  }
});
test('version config and module readback cannot be inferred from upload',async()=>{
  for(const opt of [{badVersion:true},{versionReadbackMissing:true}]){
    const {fetcher,calls}=fake({...opt,existing:true});
    const out=await runStaticVersion(env,{...req,operation:'existing_worker.static_version.verify',version_id:version},fetcher);
    assert.equal(out.status,'failed_or_indeterminate');assert.equal(out.diagnostic.phase,'version_readback');
    assert.equal(calls.some(x=>x.method!=='GET'),false);
  }
});
