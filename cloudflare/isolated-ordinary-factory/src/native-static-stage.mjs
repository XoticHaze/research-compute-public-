// Existing factory extension: pinned private manifest, inert managed target,
// one-use queue transaction. No ingress change, promotion or protected accounts.
// Keep the initial capability bounded until an exact provider readback is known.
import {uploadAssetSet,createStaticVersion} from './native-static-assets.mjs';
const ACCOUNT='de1c728bdb163060d946122c857f3653';
const TARGET='cc-app-static-assets-proof';
const CF='https://api.cloudflare.com/client/v4/accounts/'+ACCOUNT;
const GH='https://api.github.com/repos/XoticHaze/CommandCenter-gate-control/contents/cloudflare-factory/releases/'+TARGET+'/';
const HEX32=/^[a-f0-9]{32}$/;
const HEX40=/^[a-f0-9]{40}$/;
const HEX64=/^[a-f0-9]{64}$/;
const UUID=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
const TAG='cc-ordinary-factory-managed-v1';
const OP='existing_worker.static_version.stage';
const VERIFY='existing_worker.static_version.verify';
const enc=new TextDecoder('utf-8',{fatal:true});
const MAX_MANIFEST=16384,MAX_MODULE=512*1024;
function need(x,why){if(!x)throw Error(why);}
async function sha(b){return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',b)),x=>x.toString(16).padStart(2,'0')).join('');}
async function bounded(res,max){
  need(res.body,'static_body_missing');
  let size=0,parts=[];const reader=res.body.getReader();
  try{while(true){const {done,value}=await reader.read();if(done)break;size+=value.byteLength;need(size<=max,'static_body_limit');parts.push(value);}}
  finally{reader.releaseLock();}
  const out=new Uint8Array(size);let off=0;for(const part of parts){out.set(part,off);off+=part.byteLength;}return out;
}
async function token(binding){
  const value=typeof binding==='string'?binding:await binding?.get?.();
  need(typeof value==='string'&&value.length>=20,'static_credential_unavailable');return value;
}
function check(env,req){
  need(env.FACTORY_ACCOUNT_ID===ACCOUNT&&env.FACTORY_INSTALLATION_ROLE==='CC_ISOLATED_ORDINARY_ONLY'&&
    env.FACTORY_STAGE_VERSION_ENABLED==='1'&&env.FACTORY_SCRATCH_RELEASE_ENABLED==='1','static_route_not_admitted');
  need(req.worker_name===TARGET&&HEX32.test(req.worker_id)&&HEX40.test(req.source_commit)&&HEX64.test(req.source_sha256)&&
    (req.operation===OP||req.operation===VERIFY&&UUID.test(req.version_id)),'static_request_rejected');
}
async function cf(fetcher,admin,route){
  const r=await fetcher(CF+route,{method:'GET',redirect:'manual',headers:{authorization:'Bearer '+admin,accept:'application/json'}});
  need(r.status===200,'static_cf_read_http_'+r.status);
  const j=JSON.parse(enc.decode(await bounded(r,2*1024*1024)));
  need(j?.success===true,'static_cf_read_rejected');return j.result;
}
async function raw(fetcher,github,commit,file,max){
  need(HEX40.test(commit)&&typeof file==='string'&&/^[a-zA-Z0-9_.-]+(?:\/[a-zA-Z0-9_.-]+)*$/.test(file)&&!file.includes('..'),'static_source_path_rejected');
  const url=GH+file+'?ref='+commit;
  const r=await fetcher(url,{method:'GET',redirect:'manual',headers:{authorization:'Bearer '+github,accept:'application/vnd.github.raw+json','x-github-api-version':'2022-11-28','user-agent':'commandcenter-cloudflare-factory-v1'}});
  need(r.status===200&&!r.redirected,'static_private_source_unavailable');
  return bounded(r,max);
}
async function immutableSource(fetcher,github,req){
  const bytes=await raw(fetcher,github,req.source_commit,'release.json',MAX_MANIFEST);
  need(await sha(bytes)===req.source_sha256,'static_manifest_digest_mismatch');
  const m=JSON.parse(enc.decode(bytes));
  need(m&&Object.keys(m).sort().join(',')==='files,module_sha256,schema,worker_name'&&
    m.schema==='commandcenter.cloudflare.static_assets_release.v1'&&m.worker_name===TARGET&&
    HEX64.test(m.module_sha256)&&Array.isArray(m.files)&&m.files.length>0&&m.files.length<=12,'static_manifest_contract_rejected');
  const module=await raw(fetcher,github,req.source_commit,'worker.mjs',MAX_MODULE);
  const text=enc.decode(module);
  need(await sha(module)===m.module_sha256&&text.includes('export default')&&!text.includes('import('),'static_source_digest_or_format_rejected');
  return {m,module};
}
async function targetIdentity(fetcher,admin,req){
  const w=await cf(fetcher,admin,'/workers/workers/'+req.worker_id);
  need(w?.id===req.worker_id&&w?.name===TARGET&&Array.isArray(w.tags)&&w.tags.includes(TAG),'static_target_identity_rejected');
  return w;
}
async function verifiedTarget(fetcher,admin,req){
  const w=await targetIdentity(fetcher,admin,req);
  need(w.subdomain?.enabled===false&&w.subdomain?.previews_enabled===false,'static_target_ingress_open');
  const rows=await cf(fetcher,admin,'/workers/scripts/'+TARGET+'/deployments');
  need(Array.isArray(rows?.deployments)&&rows.deployments.length===0,'static_target_has_active_deployment');
  return {account_id:ACCOUNT,worker_name:TARGET,worker_id:req.worker_id,identity_verified:true,factory_managed:true,ingress_disabled:true,previews_disabled:true};
}
function versionTag(req){return 'cc-static-'+req.source_sha256;}
async function versionInventory(fetcher,admin,req){
  const rows=await cf(fetcher,admin,'/workers/workers/'+req.worker_id+'/versions?page=1&per_page=100');
  need(Array.isArray(rows)&&rows.length<100,'static_version_inventory_incomplete');
  const exact=rows.filter(v=>v?.annotations?.['workers/tag']===versionTag(req));
  need(exact.length<=1,'static_duplicate_versions_require_reconciliation');
  return exact[0]??null;
}
async function verifyVersion(fetcher,admin,req,id,manifest,{tag=versionTag(req),privateBindings=false,requireInert=true}={}){
  need(UUID.test(id),'static_version_id_invalid');
  const v=await cf(fetcher,admin,'/workers/workers/'+req.worker_id+'/versions/'+id+'?include=modules');
  need(v?.id===id&&v.annotations?.['workers/tag']===tag,'static_version_identity_or_tag_mismatch');
  need(v.main_module===undefined||v.main_module==='worker.mjs','static_main_module_mismatch');
  need(Array.isArray(v.modules)&&v.modules.length===1,'static_module_count_mismatch');
  const m=v.modules[0];
  need(m?.name==='worker.mjs'&&['application/javascript+module','text/javascript+module'].includes(m.content_type)&&typeof m.content_base64==='string'&&m.content_base64.length<=MAX_MODULE*2,'static_module_readback_invalid');
  const module=Uint8Array.from(atob(m.content_base64),c=>c.charCodeAt(0));
  need(await sha(module)===manifest.module_sha256,'static_module_readback_mismatch');
  const bindings=v.bindings;
  // Only the named asset binding is permitted. Fail closed if provider omits
  // required configuration; never infer security from successful upload alone.
  const names=new Map(Array.isArray(bindings)?bindings.map(b=>[b.name,b.type]):[]);
  const accessKeys=['ACCESS_ISSUER','ACCESS_AUD','ACCESS_ALLOWED_EMAILS_JSON'];
  need(Array.isArray(bindings)&&names.size===bindings.length&&names.get('ASSETS')==='assets'&&names.size===(privateBindings?4:1)&&(!privateBindings||accessKeys.every(k=>names.get(k)==='secret_text')),'static_asset_binding_unverified');
  need(v.assets?.config?.run_worker_first===true&&v.assets.config.html_handling==='none'&&v.assets.config.not_found_handling==='404-page','static_worker_first_readback_unverified');
  if(requireInert)await verifiedTarget(fetcher,admin,req);
  return v;
}
export async function runStaticVersion(env,req,fetcher=fetch){
  let phase='contract',mutation=false,id=null;
  try{
    check(env,req);
    phase='credential';const admin=await token(env.FACTORY_WORKERS_ADMIN),github=await token(env.FACTORY_QUEUE_GITHUB_TOKEN);
    phase='target';const target=await verifiedTarget(fetcher,admin,req);
    phase='source';const {m,module}=await immutableSource(fetcher,github,req);
    phase='reconcile';const existing=await versionInventory(fetcher,admin,req);
    if(req.operation===VERIFY){need(existing?.id===req.version_id,'static_exact_version_not_found');id=req.version_id;}
    else if(existing){id=existing.id;}
    else{
      phase='asset_upload_session';mutation=true;
      const up=await uploadAssetSet(target,m.files,(file,size)=>raw(fetcher,github,req.source_commit,'assets'+file,size),admin,fetcher);
      phase='version_create';const v=await createStaticVersion(target,up,module,m.module_sha256,req.source_sha256,admin,fetcher);
      id=v.version_id;
    }
    phase='version_readback';await verifyVersion(fetcher,admin,req,id,m);
    return {status:req.operation===VERIFY?'version_verified':'staged_off_traffic',worker_name:TARGET,worker_id:req.worker_id,
      version_id:id,source_commit:req.source_commit,source_sha256:req.source_sha256,module_sha256:m.module_sha256,asset_count:m.files.length,
      version_content_readback_verified:true,worker_first_verified:true,asset_bytes_served_verified:false,
      active_version_id:null,production_promoted:false,public_ingress_enabled:false,previews_enabled:false,
      mutation_attempted:mutation,bearer_returned:false};
  }catch(e){
    const category=/^static_[a-z0-9_]{1,100}$/.test(String(e?.message))||/^asset_[a-z0-9_]{1,100}$/.test(String(e?.message))?e.message:'static_unexpected_failure';
    return {status:'failed_or_indeterminate',worker_name:TARGET,worker_id:req?.worker_id,
      version_id:id,diagnostic:{phase,category,mutation_attempted:mutation},retry_same_id:false,bearer_returned:false};
  }
}

const PRIVATE_OP='existing_worker.static_version.serve_private';
const PROOF_ID='206835a985d245b98367cce82db55383';
const CANARY_ID='75d882ae4da84594817608332bb35405';
const PROOF_HOST='https://cc-app-factory-proof.cc-ordinary-deployments.workers.dev';
const TARGET_HOST='https://cc-app-static-assets-proof.cc-ordinary-deployments.workers.dev';
const FIXTURE_COMMIT='700597fed7b0dc76810347948ae080c6f6b62079';
const FIXTURE_MANIFEST='6465cdf1472217ae0deffc23d2e8b378ae54858db0908c1863f73df12d613fe5';
const FIXTURE_MODULE='e3d9f27fe5f70f4e5e8bdf9ff417ba613203c4e5eee193fca274d451daf8b6e8';
function privateCheck(env,req){
  need(env.FACTORY_ACCOUNT_ID===ACCOUNT&&env.FACTORY_INSTALLATION_ROLE==='CC_ISOLATED_ORDINARY_ONLY'&&env.FACTORY_STAGE_VERSION_ENABLED==='1'&&env.FACTORY_SCRATCH_RELEASE_ENABLED==='1','static_route_not_admitted');
  need(req.operation===PRIVATE_OP&&req.worker_name===TARGET&&req.worker_id===CANARY_ID&&req.source_commit===FIXTURE_COMMIT&&req.source_sha256===FIXTURE_MANIFEST&&UUID.test(req.version_id),'static_private_exact_fixture_required');
}
export function challengeIssuer(response){
  need([302,303,307,308].includes(response.status),'static_private_edge_challenge_missing');
  const u=new URL(response.headers.get('location')||'');
  need(u.protocol==='https:'&&/^[a-z0-9-]+\.cloudflareaccess\.com$/.test(u.hostname)&&!u.username&&!u.password&&!u.port&&u.pathname.startsWith('/cdn-cgi/access/login/'),'static_private_edge_challenge_invalid');
  return u.origin;
}
async function accessConfig(env,fetcher,readAccess,req){
  const d={phase:'static_private_access',http_status:null,api_error_codes:[],mutation_attempted:false};
  const a=await readAccess(env,fetcher,d,req);
  const proof=await readAccess(env,fetcher,d,{worker_id:PROOF_ID});
  need(a.id===proof.id&&a.aud===proof.aud&&UUID.test(a.id)&&HEX64.test(a.aud),'static_private_access_app_mismatch');
  const r=await fetcher(PROOF_HOST+'/',{method:'GET',redirect:'manual',headers:{'cache-control':'no-cache',accept:'text/html'}});
  const issuer=challengeIssuer(r),email=String(env.FACTORY_ALLOWED_EMAILS||'').trim().toLowerCase();
  need(/^[^@\s*,]+@[^@\s*,]+\.[^@\s*,]+$/.test(email),'static_private_owner_required');
  return {appId:a.id,issuer,config:{ACCESS_ISSUER:issuer,ACCESS_AUD:a.aud,ACCESS_ALLOWED_EMAILS_JSON:JSON.stringify([email])}};
}
async function cfWrite(fetcher,admin,method,route,payload){
  const r=await fetcher(CF+route,{method,redirect:'manual',headers:{authorization:'Bearer '+admin,accept:'application/json','content-type':method==='PATCH'&&route.endsWith('/latest')?'application/merge-patch+json':'application/json'},body:JSON.stringify(payload)});
  need([200,201].includes(r.status),'static_private_mutation_http_'+r.status);
  const j=JSON.parse(enc.decode(await bounded(r,2*1024*1024)));
  need(j?.success===true,'static_private_mutation_rejected');return j.result;
}
async function currentStatic(fetcher,admin){
  const j=await cf(fetcher,admin,'/workers/scripts/'+TARGET+'/deployments');
  need(Array.isArray(j?.deployments),'static_private_deployment_inventory_invalid');
  if(!j.deployments.length)return null;
  const d=j.deployments;
  need(d.every(x=>UUID.test(x?.id)&&Number.isFinite(Date.parse(x.created_on))),'static_private_deployment_identity_invalid');
  const sorted=[...d].sort((a,b)=>Date.parse(b.created_on)-Date.parse(a.created_on));
  need(sorted.length===1||Date.parse(sorted[0].created_on)>Date.parse(sorted[1].created_on),'static_private_deployment_ambiguous');
  const current=sorted[0];
  need(Array.isArray(current.versions)&&current.versions.length===1&&current.versions[0].percentage===100&&UUID.test(current.versions[0].version_id),'static_private_deployment_split');
  return {id:current.id,version:current.versions[0].version_id};
}
function assetRouting(v){return JSON.stringify(Object.entries(v.assets.config).sort(([a],[b])=>a.localeCompare(b)));}
export async function runStaticPrivateRelease(env,req,readAccess,fetcher=fetch){
  let phase='contract',mutation=false,id=null,admin=null,openAttempted=false,closed=null;
  try{
    privateCheck(env,req);need(typeof readAccess==='function','static_private_access_reader_missing');
    phase='credential';admin=await token(env.FACTORY_WORKERS_ADMIN);const github=await token(env.FACTORY_QUEUE_GITHUB_TOKEN);
    phase='target';const w=await targetIdentity(fetcher,admin,req);
    need(w.subdomain?.url?.replace(/\/$/,'')===TARGET_HOST&&typeof w.subdomain.enabled==='boolean'&&w.subdomain.previews_enabled===false,'static_private_subdomain_identity_invalid');
    phase='source';const {m}=await immutableSource(fetcher,github,req);
    need(m.module_sha256===FIXTURE_MODULE&&m.files.length===2&&m.files.some(x=>x.path==='/proof.txt'),'static_private_fixture_identity_invalid');
    phase='access';const access=await accessConfig(env,fetcher,readAccess,req);
    // The tag includes exact manifest, Access app ID and a digest of issuer/AUD,
    // not owner identity or secret values. One initial protected release only.
    const accessHash=await sha(new TextEncoder().encode(access.issuer+'\n'+access.config.ACCESS_AUD));
    const tag='cc-static-private-'+req.source_sha256+'-'+access.appId+'-'+accessHash.slice(0,16);
    phase='base_readback';
    const base=await verifyVersion(fetcher,admin,req,req.version_id,m,{requireInert:false});
    const path='/workers/workers/'+CANARY_ID+'/versions';
    phase='reconcile';const rows=await cf(fetcher,admin,path+'?page=1&per_page=100');
    need(Array.isArray(rows)&&rows.length<100,'static_version_inventory_incomplete');
    const matches=rows.filter(x=>x.annotations?.['workers/tag']===tag);
    need(matches.length<=1,'static_duplicate_versions_require_reconciliation');
    const before=await currentStatic(fetcher,admin);
    if(matches.length){id=matches[0].id;need(UUID.test(id)&&id!==req.version_id,'static_private_repair_id_invalid');}
    else{
      need(before===null&&w.subdomain.enabled===false,'static_private_expected_inert_target');
      const latest=await cf(fetcher,admin,path+'/latest?include=modules');
      need(latest.id===req.version_id,'static_private_latest_not_base');
      phase='binding_repair';mutation=true;
      const repaired=await cfWrite(fetcher,admin,'PATCH',path+'/latest',{env:Object.fromEntries(Object.entries(access.config).map(([k,v])=>[k,{type:'secret_text',text:v}])),annotations:{'workers/tag':tag}});
      id=repaired?.id;need(UUID.test(id)&&id!==req.version_id,'static_private_repair_id_invalid');
    }
    phase='repaired_readback';
    const repaired=await verifyVersion(fetcher,admin,req,id,m,{tag,privateBindings:true,requireInert:false});
    need(assetRouting(base)===assetRouting(repaired),'static_private_assets_routing_changed');
    phase='promotion_preflight';
    const again=await accessConfig(env,fetcher,readAccess,req);
    need(JSON.stringify(again)===JSON.stringify(access),'static_private_access_changed');
    const active=await currentStatic(fetcher,admin);
    need(active===null||active.version===id,'static_private_unexpected_active_version');
    if(active===null){
      phase='promote';mutation=true;
      await cfWrite(fetcher,admin,'POST','/workers/scripts/'+TARGET+'/deployments',{strategy:'percentage',versions:[{version_id:id,percentage:100}]});
    }
    const promoted=await currentStatic(fetcher,admin);
    need(promoted?.version===id,'static_private_promoted_version_unverified');
    phase='open_private_ingress';
    const prior=await targetIdentity(fetcher,admin,req);
    need(prior.subdomain?.url?.replace(/\/$/,'')===TARGET_HOST&&prior.subdomain.previews_enabled===false,'static_private_subdomain_identity_invalid');
    openAttempted=true;
    if(!prior.subdomain.enabled){mutation=true;await cfWrite(fetcher,admin,'PATCH','/workers/workers/'+CANARY_ID,{subdomain:{enabled:true,previews_enabled:false}});}
    const after=await targetIdentity(fetcher,admin,req);
    need(after.subdomain?.enabled===true&&after.subdomain.previews_enabled===false&&after.subdomain.url?.replace(/\/$/,'')===TARGET_HOST,'static_private_ingress_readback_failed');
    phase='edge_access_recheck';const finalAccess=await accessConfig(env,fetcher,readAccess,req);
    need(JSON.stringify(finalAccess)===JSON.stringify(access),'static_private_access_changed');
    phase='anonymous_root_and_asset';const edges={};
    for(const path of ['/','/proof.txt']){
      const res=await fetcher(TARGET_HOST+path,{method:'GET',redirect:'manual',headers:{accept:'text/html,text/plain','cache-control':'no-cache'}});
      need(challengeIssuer(res)===access.issuer,'static_private_edge_issuer_mismatch');
      edges[path]={status:res.status,access_login_redirect:true};
    }
    const confirmed=await currentStatic(fetcher,admin);
    need(confirmed?.id===promoted.id&&confirmed.version===id,'static_private_deployment_changed');
    return {status:'private_ingress_verified',worker_name:TARGET,worker_id:CANARY_ID,base_version_id:req.version_id,version_id:id,deployment_id:promoted.id,source_sha256:req.source_sha256,served_url:TARGET_HOST,account_default_app_id:access.appId,worker_first_verified:true,exact_owner_policy_verified:true,anonymous_edge_verified:true,authorized_browser_positive_verified:false,asset_bytes_served_verified:false,previews_enabled:false,mutation_attempted:mutation,bearer_returned:false,edges};
  }catch(e){
    if(openAttempted&&admin){
      try{
        await targetIdentity(fetcher,admin,req);
        await cfWrite(fetcher,admin,'PATCH','/workers/workers/'+CANARY_ID,{subdomain:{enabled:false,previews_enabled:false}});
        const w=await targetIdentity(fetcher,admin,req);
        closed=w.subdomain?.enabled===false&&w.subdomain.previews_enabled===false;
      }catch{closed=false;}
    }
    const category=/^static_[a-z0-9_]{1,100}$/.test(String(e?.message))?e.message:'static_private_unexpected_failure';
    return {status:'failed_or_indeterminate',worker_name:TARGET,worker_id:CANARY_ID,version_id:id,diagnostic:{phase,category,mutation_attempted:mutation},ingress_closed_verified:closed,retry_same_id:false,bearer_returned:false};
  }
}
