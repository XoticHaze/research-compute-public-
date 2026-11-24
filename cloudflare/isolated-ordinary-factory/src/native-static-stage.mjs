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
async function verifiedTarget(fetcher,admin,req){
  const w=await cf(fetcher,admin,'/workers/workers/'+req.worker_id);
  need(w?.id===req.worker_id&&w?.name===TARGET&&Array.isArray(w.tags)&&w.tags.includes(TAG),'static_target_identity_rejected');
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
async function verifyVersion(fetcher,admin,req,id,manifest){
  need(UUID.test(id),'static_version_id_invalid');
  const v=await cf(fetcher,admin,'/workers/workers/'+req.worker_id+'/versions/'+id+'?include=modules');
  need(v?.id===id&&v.annotations?.['workers/tag']===versionTag(req),'static_version_identity_or_tag_mismatch');
  need(v.main_module===undefined||v.main_module==='worker.mjs','static_main_module_mismatch');
  need(Array.isArray(v.modules)&&v.modules.length===1,'static_module_count_mismatch');
  const m=v.modules[0];
  need(m?.name==='worker.mjs'&&['application/javascript+module','text/javascript+module'].includes(m.content_type)&&typeof m.content_base64==='string'&&m.content_base64.length<=MAX_MODULE*2,'static_module_readback_invalid');
  const module=Uint8Array.from(atob(m.content_base64),c=>c.charCodeAt(0));
  need(await sha(module)===manifest.module_sha256,'static_module_readback_mismatch');
  const bindings=v.bindings;
  // Only the named asset binding is permitted. Fail closed if provider omits
  // required configuration; never infer security from successful upload alone.
  need(Array.isArray(bindings)&&bindings.length===1&&bindings[0].type==='assets'&&bindings[0].name==='ASSETS','static_asset_binding_unverified');
  need(v.assets?.config?.run_worker_first===true&&v.assets.config.html_handling==='none'&&v.assets.config.not_found_handling==='404-page','static_worker_first_readback_unverified');
  await verifiedTarget(fetcher,admin,req);
  return true;
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
