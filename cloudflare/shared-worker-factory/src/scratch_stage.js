// Bounded, version-only stage for existing disposable scratch Workers.
// Never deploys a version, configures routes, or modifies protected resources.
// Cloudflare reference:
// https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/versions/methods/create/
const ACCOUNT='ce43cd7b917d98a4bb4866d30eed99c0';
const API='https://api.cloudflare.com/client/v4';
const SOURCE='https://raw.githubusercontent.com/XoticHaze/research-compute-public-/';
const SHA40=/^[a-f0-9]{40}$/;
const SHA64=/^[a-f0-9]{64}$/;
const ID32=/^[a-f0-9]{32}$/;
const UUID=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
const SCRATCH=/^cc-scratch-[a-z0-9]+(?:-[a-z0-9]+)*$/;
const SIZE_MAX=32768;
const compat='2026-11-18';
function check(name,id,commit,digest) {
  if(typeof name!=='string'||name.length>58||!SCRATCH.test(name)||
     !ID32.test(String(id||''))||!SHA40.test(String(commit||''))||
     !SHA64.test(String(digest||''))) throw Error('scratch_release_contract_rejected');
}
async function bodyLimited(resp) {
  if(!resp.ok || resp.redirected || resp.status!==200) throw Error('source_unavailable');
  const length=resp.headers.get('content-length');
  if(length && (+length>SIZE_MAX || !Number.isInteger(+length)))
    throw Error('source_size_rejected');
  if(!resp.body) throw Error('source_unavailable');
  const reader=resp.body.getReader();
  const chunks=[];let size=0;
  try {
    while(true) {
      const {done,value}=await reader.read();
      if(done)break;
      size+=value.byteLength;
      if(size>SIZE_MAX) throw Error('source_size_rejected');
      chunks.push(value);
    }
  } finally {reader.releaseLock();}
  if(size<35) throw Error('source_size_rejected');
  const bytes=new Uint8Array(size);let p=0;
  for(const c of chunks){bytes.set(c,p);p+=c.byteLength;}
  return bytes;
}
const hex=bytes=>Array.from(new Uint8Array(bytes),b=>b.toString(16).padStart(2,'0')).join('');
async function cloudflareJson(fetcher,bearer,method,path,body,expectedStatuses) {
  const init={method,redirect:'error',headers:{
    authorization:'Bearer '+bearer,accept:'application/json'
  }};
  if(body!==undefined)init.body=body;
  const resp=await fetcher(API+path,init);
  if(!expectedStatuses.includes(resp.status))throw Error('cloudflare_stage_rejected');
  let result;
  try{result=await resp.json();}catch{throw Error('cloudflare_stage_invalid');}
  if(!result || result.success!==true)throw Error('cloudflare_stage_rejected');
  return result.result;
}
export async function stageScratchVersion(env,req,fetcher=fetch) {
  check(req.worker_name,req.worker_id,req.source_commit,req.source_sha256);
  if(String(env.FACTORY_ACCOUNT_ID)!==ACCOUNT ||
     env.FACTORY_STAGE_VERSION_ENABLED!=='1')
    throw Error('scratch_stage_disabled');
  const binding=env.FACTORY_WORKERS_ADMIN;
  if(!binding || typeof binding.get!=='function')
    throw Error('cloudflare_credentials_not_bound');
  const bearer=await binding.get();
  if(typeof bearer!=='string'||bearer.length<20)
    throw Error('cloudflare_credentials_unavailable');
  const worker=await cloudflareJson(fetcher,bearer,'GET',
    '/accounts/'+ACCOUNT+'/workers/workers/'+req.worker_id,undefined,[200]);
  if(worker?.id!==req.worker_id||worker?.name!==req.worker_name)
    throw Error('worker_identity_rejected');

  // The source path is derived from a validated scratch Worker name, never a
  // user-controlled arbitrary URL or private repository.
  const path='cloudflare/ordinary-scratch-releases/'+req.worker_name+'/worker.mjs';
  const response=await fetcher(SOURCE+req.source_commit+'/'+path,{
    method:'GET',redirect:'error',headers:{accept:'text/plain'}
  });
  const bytes=await bodyLimited(response);
  const digest=hex(await crypto.subtle.digest('SHA-256',bytes));
  if(digest!==req.source_sha256)throw Error('source_digest_rejected');
  const source=new TextDecoder('utf-8',{fatal:true}).decode(bytes);
  if(!source.includes('export default') || source.includes('import('))
    throw Error('unsupported_scratch_source');

  const form=new FormData();
  form.append('metadata',JSON.stringify({
    main_module:'worker.mjs',compatibility_date:compat,bindings:[]
  }));
  form.append('worker.mjs',new Blob([bytes],{
    type:'application/javascript+module'}),'worker.mjs');
  const staged=await cloudflareJson(fetcher,bearer,'POST',
    '/accounts/'+ACCOUNT+'/workers/scripts/'+req.worker_name+'/versions',
    form,[200,201]);
  const version=String(staged?.id||'');
  if(!UUID.test(version))throw Error('version_stage_indeterminate');
  // The versions/upload API explicitly does not create a deployment. This
  // receipt reports successful stage only, not verified live code or traffic.
  return {
    status:'staged_off_traffic',account_role:'ORIGINAL_SLENDERIQ_ORDINARY_ONLY',
    worker_name:req.worker_name,worker_id:req.worker_id,version_id:version,
    source_commit:req.source_commit,source_sha256:digest,
    file_count:1,source_size_bytes:bytes.length,
    active_deployment_unchanged_by_api:true,live_serving_verified:false,
    cloudflare_mutations:1,secret_included:false
  };
}
