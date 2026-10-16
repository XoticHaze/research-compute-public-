// Real source-level integration of the existing Cloudflare maintainer with
// synthetic external API responses. No Cloudflare credentials, deployment,
// Worker mutation, independent maintenance signatures, or private input.
import fs from 'node:fs';
import assert from 'node:assert/strict';
import { createHash, webcrypto } from 'node:crypto';
if (!globalThis.crypto) globalThis.crypto=webcrypto;
const sha=x=>createHash('sha256').update(x).digest('hex');
const sourcePath='cloudflare/reference-release-maintainer/src/index.js';
const source=fs.readFileSync(sourcePath,'utf8');
assert.ok(source.includes('import { WorkerEntrypoint } from "cloudflare:workers";'));
const code=source.replace('import { WorkerEntrypoint } from "cloudflare:workers";',
  'class WorkerEntrypoint {}')+'\nexport { maintainManifest };';
const module=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));
const {maintainManifest}=module;
const brokerSource='cloudflare/reference-release-broker/src/';
const sourceFiles=['index.js','intent.js','ticket.js'];
const bodies=Object.fromEntries(sourceFiles.map(x=>[x,
  fs.readFileSync(brokerSource+x,'utf8')]));
const hashes=Object.fromEntries(sourceFiles.map(x=>[x,sha(bodies[x])]));
const canonical=x=>JSON.stringify(Object.fromEntries(Object.entries(x).sort(([a],[b])=>a<b?-1:a>b?1:0)));
const candidate='9cc2ab27dac66147e432703eec0281254379b62b';
const old='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const newer='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const other='cccccccc-cccc-4ccc-8ccc-cccccccccccc';
const keyId='sha256:'+'8'.repeat(64);
const baseManifest={
  schema:'reference-release-maintenance-v1',
  issuer:'private-maintenance-authority-v1',
  maintenance_id:'synthetic-maint-0123456789abcdef',
  target_worker:'reference-release-broker-v1',
  candidate_source_sha:candidate,
  files:hashes,candidate_package_sha256:sha(canonical(hashes)),
  expected_current_version:old,rollback_version:old,
  expected_broker_key_id:keyId,
  not_before:100,expires_at:200
};
const account='b33595eb85f346b0d1bf201810b4499a';
const cf='https://api.cloudflare.com/client/v4/accounts/'+account;
const target='/workers/scripts/reference-release-broker-v1';
const origin='https://reference-release-broker-v1.slenderiq.workers.dev';

function fake(overrides={}){
  const state={
    active:old,consumed:false,consumes:0,events:[],uploads:0,promotions:[],rawReads:0,
    privateKeyRead:false, wrongBinding:false,...overrides,
  };
  const env={
    CLOUDFLARE_ACCOUNT_ID:state.overrideAccount||account,
    BROKER_PUBLIC_ORIGIN:origin,
    MAINTENANCE_AUTHORITY:{
      verifyManifest:async wrapper=>{
        state.events.push('authority_verify');
        return structuredClone(wrapper);
      }
    },
    BROKER_EDITOR_TOKEN:{
      get:async()=>{
        state.events.push('token_get');
        return state.noToken?null:'synthetic-scoped-editor-not-a-credential';
      }
    },
    MAINTENANCE_LEDGER:{
      idFromName:id=>id,
      get:()=>({fetch:async (_url,init)=>{
        assert.equal(init.method,'POST');
        state.events.push('consume');
        state.consumes++;
        if(state.consumed) return new Response('{}',{status:409});
        state.consumed=true;
        return new Response('{"ok":true}',{status:200});
      }})
    }
  };
  globalThis.fetch=async (url,init={})=>{
    const u=String(url),method=init.method||'GET';
    if(u.startsWith('https://raw.githubusercontent.com/')){
      state.events.push('candidate_read');
      state.rawReads++;
      const name=sourceFiles.find(n=>u.endsWith('/'+n));
      assert.ok(name,'unexpected candidate file');
      assert.ok(u.includes('/'+candidate+'/'),'candidate must be SHA pinned');
      return new Response(state.badSource&&name==='ticket.js'?'wrong source':bodies[name],{status:200});
    }
    if(u===cf+target+'/deployments'&&method==='GET'){
      state.events.push('active_read');
      state.activeReads=(state.activeReads||0)+1;
      if((state.raceBeforeUpload&&state.activeReads===2)
          || (state.raceBeforePromotion&&state.activeReads===3)){
        state.active=other;
      }
      return Response.json({success:true,result:{deployments:[
        {versions:[{version_id:state.active,percentage:100}]}
      ]}});
    }
    if(u===cf+target+'/versions?bindings_inherit=strict'&&method==='POST'){
      state.events.push('upload');
      state.uploads++;
      assert.equal(init.body instanceof FormData,true);
      const metadata=JSON.parse(await init.body.get('metadata').text());
      assert.equal(metadata.main_module,'index.js');
      assert.equal(metadata.bindings.length,7);
      assert.deepEqual(metadata.bindings.map(x=>x.name).sort(),[
        'BROKER_SIGNING_PRIVATE_JWK','AUTHORITY_PUBLIC_B64','GRANT_LEDGER',
        'ALLOWED_JOB_WORKFLOW_REF','ALLOWED_JOB_WORKFLOW_SHA',
        'MAX_ADMISSION_SECONDS','MAX_INTENT_SECONDS'].sort());
      assert.ok(metadata.bindings.every(x=>x.type==='inherit'&&x.version_id===old));
      assert.equal(metadata.annotations['workers/commit_sha'],candidate);
      for(const name of sourceFiles){
        assert.equal(await init.body.get(name).text(),bodies[name]);
      }
      return state.uploadFailure?
        Response.json({success:false},{status:403}):
        Response.json({success:true,result:{id:newer}});
    }
    if(u===cf+target+'/deployments'&&method==='POST'){
      const request=JSON.parse(init.body);
      const version=request.versions[0].version_id;
      state.events.push('deploy_'+version);
      state.promotions.push(version);
      if(version===newer){
        if(state.promoteUnexpected)state.active=other;
        else if(!state.promotionNoMutation)state.active=newer;
        return state.promotionHttpFailure?
          Response.json({success:false},{status:500}):
          Response.json({success:true});
      }
      assert.equal(version,old,'rollback must target exact prior version');
      if(state.rollbackFails)return Response.json({success:false},{status:503});
      state.active=old;
      return Response.json({success:true});
    }
    if(u===origin+'/healthz'){
      state.events.push('health_read');
      return state.postdeployUnhealthy?
        Response.json({ok:false},{status:503}):
        Response.json({ok:true});
    }
    if(u===origin+'/v1/public-key'){
      state.events.push('key_read');
      return Response.json({key_id:keyId});
    }
    throw Error('unexpected_network_target');
  };
  return {env,state};
}
async function reject(label,opts,expected){
  const {env,state}=fake(opts);
  let code='';
  try{await maintainManifest(structuredClone(baseManifest),env);}
  catch(e){code=String(e.message);}
  assert.equal(code,expected,label);
  return state;
}
let checks=0;
{
  const {env,state}=fake();
  const response=await maintainManifest(structuredClone(baseManifest),env);
  assert.equal(response.status,200);
  const result=await response.json();
  assert.equal(result.ok,true);
  assert.equal(result.deployed_version,newer);
  assert.equal(result.previous_version,old);
  assert.equal(result.rollback_performed,false);
  assert.equal(result.secret_material_included,false);
  assert.equal(state.consumes,1);
  assert.equal(state.uploads,1);
  assert.equal(state.active,newer);
  assert.deepEqual(state.promotions,[newer]);
  assert.ok(state.events.indexOf('candidate_read')<state.events.indexOf('consume'));
  assert.ok(state.events.indexOf('token_get')<state.events.indexOf('consume'));
  assert.ok(state.events.indexOf('active_read')<state.events.indexOf('consume'));
  checks++;
}
{
  const s=await reject('no_editor_token',{noToken:true},'broker_editor_token_unavailable');
  assert.equal(s.consumes,0);assert.equal(s.uploads,0);checks++;
}
{
  const s=await reject('stale_version',{active:other},'current_version_mismatch');
  assert.equal(s.consumes,0);assert.equal(s.uploads,0);checks++;
}
{
  const s=await reject('incorrect_candidate_hash',{badSource:true},'candidate_file_hash_rejected_ticket.js');
  assert.equal(s.consumes,0);assert.equal(s.uploads,0);checks++;
}
{
  const s=await reject('already_consumed',{consumed:true},'maintenance_replay_rejected');
  assert.equal(s.consumes,1);assert.equal(s.uploads,0);checks++;
}
{
  const s=await reject('upload_does_not_promote',{uploadFailure:true},'version_upload_rejected_403');
  assert.equal(s.consumes,1);assert.equal(s.active,old);assert.equal(s.promotions.length,0);checks++;
}
{
  const s=await reject('promotion_remote_commits_but_http_fails',{promotionHttpFailure:true},'deployment_create_rejected_500');
  assert.deepEqual(s.promotions,[newer,old]);
  assert.equal(s.active,old);assert.equal(s.consumes,1);checks++;
}
{
  const s=await reject('postdeploy_unhealthy_rollback_preseal',{postdeployUnhealthy:true},'postdeploy_health_rejected');
  assert.deepEqual(s.promotions,[newer,old]);
  assert.equal(s.active,old);assert.equal(s.consumes,1);checks++;
}
{
  const s=await reject('failed_promote_without_remote_mutation',{promotionHttpFailure:true,promotionNoMutation:true},'deployment_create_rejected_500');
  assert.deepEqual(s.promotions,[newer]);assert.equal(s.active,old);checks++;
}
{
  const s=await reject('unexpected_concurrent_version_never_clobbered',{promotionHttpFailure:true,promoteUnexpected:true},'maintenance_unexpected_active_version');
  assert.deepEqual(s.promotions,[newer]);assert.equal(s.active,other);checks++;
}
{
  const s=await reject('rollback_fails_closed',{promotionHttpFailure:true,rollbackFails:true},'maintenance_failed_and_rollback_failed');
  assert.deepEqual(s.promotions,[newer,old]);assert.equal(s.active,newer);checks++;
}
{
  const s=await reject('raced_after_preflight_before_upload',
                       {raceBeforeUpload:true},'preupload_version_mismatch');
  assert.equal(s.consumes,1);assert.equal(s.uploads,0);
  assert.equal(s.active,other);assert.equal(s.promotions.length,0);checks++;
}
{
  const s=await reject('raced_after_upload_before_promotion',
                       {raceBeforePromotion:true},'prepromotion_version_mismatch');
  assert.equal(s.consumes,1);assert.equal(s.uploads,1);
  assert.equal(s.active,other);assert.equal(s.promotions.length,0);checks++;
}
{
  const s=await reject('original_account_must_not_receive_maintenance',{
    overrideAccount:'ce43cd7b917d98a4bb4866d30eed99c0',
  },'neutral_cloudflare_account_mismatch');
  assert.equal(s.consumes,0);assert.equal(s.rawReads,0);
  assert.equal(s.events.includes('token_get'),false);checks++;
}
{
  const s=await reject('other_account_even_with_editor_must_not_receive_maintenance',{
    overrideAccount:'ffffffffffffffffffffffffffffffff',
  },'neutral_cloudflare_account_mismatch');
  assert.equal(s.consumes,0);assert.equal(s.rawReads,0);
  assert.equal(s.events.includes('token_get'),false);checks++;
}
{
  const {env,state}=fake({
    overrideAccount:'ce43cd7b917d98a4bb4866d30eed99c0',
  });
  const maintainer=new module.default();
  maintainer.env=env;
  let rejected=false;
  try{await maintainer.brokerState();}
  catch(e){rejected=e.message==='neutral_cloudflare_account_mismatch';}
  assert.equal(rejected,true,'read-only broker state must reject stale account');
  assert.equal(state.events.includes('token_get'),false);checks++;
}
assert.equal(checks,16);
console.log('REFERENCE_MAINTAINER_ACTUAL_SOURCE_PREFLIGHT_AND_ROLLBACK_PASS='+checks);
console.log('REFERENCE_MAINTAINER_PUBLIC_CI_SYNTHETIC_ONLY=1');
