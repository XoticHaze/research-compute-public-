#!/usr/bin/env node
// Derived factory source for a NEW isolated ordinary-deployments Cloudflare account.
// It never sends an API request or needs a token.
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {readFileSync,writeFileSync,mkdirSync,existsSync} from 'node:fs';
import {resolve,dirname,join} from 'node:path';
import {fileURLToPath} from 'node:url';

export const SOURCE_PINS=Object.freeze({
  'index.js':'a072b036cc39e3ea71fe2760ebae677d329ccf3a',
  'policy.js':'2f44fa6ac971c2bcaf56ec7a958d2aefeea66e24',
  'scratch_stage.js':'f2d58bd83f5edb763c0d9feda4778fad93fd8cca',
  'machine_oidc.js':'003b0369d76f2021ba7ff28aa8b8e71230410d38',
  'queue.js':'a37b1913e32d0aa602ca1efa6c224559a8af50f2',
  'ui.js':'166428c9333ab87b73adf8facdf228e90ea7743a'
});
export const PROTECTED_ACCOUNT_IDS=Object.freeze([
  'ce43cd7b917d98a4bb4866d30eed99c0', // SlenderIQ
  'b33595eb85f346b0d1bf201810b4499a'  // neutral
]);
export const FACTORY_NAME='cc-ordinary-worker-factory';
const PACKAGE=dirname(dirname(fileURLToPath(import.meta.url)));
const ROOT=resolve(PACKAGE,'../..');
const SOURCE=resolve(ROOT,'cloudflare/shared-worker-factory/src');
export const OUT=resolve(PACKAGE,'.generated');

export function validateAccount(value) {
  if(typeof value!=='string'|| !/^[a-f0-9]{32}$/.test(value) ||
     PROTECTED_ACCOUNT_IDS.includes(value))
    throw Error('ACCOUNT_NOT_ADMITTED_NEW_ORDINARY_ONLY');
  return value;
}
function pinnedRead(name) {
  if(!(name in SOURCE_PINS)) throw Error('SOURCE_NOT_ALLOWLISTED');
  const path=join(SOURCE,name);
  const sha=execFileSync('git',['hash-object',path],
    {cwd:ROOT,encoding:'utf8',timeout:10000}).trim();
  if(sha!==SOURCE_PINS[name]) throw Error('REVIEWED_MODULE_SHA_DRIFT_'+name);
  return readFileSync(path,'utf8');
}
function exactlyOnce(source,oldValue,newValue,label){
  const parts=source.split(oldValue);
  if(parts.length!==2) throw Error('PINNED_PATCH_DRIFT_'+label);
  return parts.join(newValue);
}
const OLD_TOKEN="async function token(binding) {\n"+
  "  if (!binding || typeof binding.get!=='function') throw Error('secret_binding_absent');\n"+
  "  const value=await binding.get();\n"+
  "  if (typeof value!=='string'||value.length<20) throw Error('secret_unavailable');\n"+
  "  return value;\n}";
const NEW_TOKEN="async function token(binding) {\n"+
  "  if (typeof binding==='string' && binding.length>=20) return binding;\n"+
  "  if (!binding || typeof binding.get!=='function') throw Error('secret_binding_absent');\n"+
  "  const value=await binding.get();\n"+
  "  if (typeof value!=='string'||value.length<20) throw Error('secret_unavailable');\n"+
  "  return value;\n}";
export function build(accountId,{outDir=OUT}={}){
  const account=validateAccount(accountId);
  const src={};
  for(const name of Object.keys(SOURCE_PINS)) src[name]=pinnedRead(name);
  src['index.js']=exactlyOnce(src['index.js'],
    "const ORDINARY_ACCOUNT = 'ce43cd7b917d98a4bb4866d30eed99c0';",
    "const ORDINARY_ACCOUNT = '"+account+"';",'worker_account_pin');
  src['index.js']=exactlyOnce(src['index.js'],OLD_TOKEN,NEW_TOKEN,'runtime_cloudflare_secret');
  src['index.js']=src['index.js'].replaceAll('ORIGINAL_SLENDERIQ_ORDINARY_ONLY','CC_ISOLATED_ORDINARY_ONLY');

  const CRON_HANDLER="\n  async scheduled(controller,env,ctx) {\n    if (controller?.cron!=='* * * * *' ||\n        env.FACTORY_SCHEDULED_POLL_ENABLED!=='1' ||\n        env.FACTORY_EXECUTOR_ENABLED!=='1' ||\n        env.FACTORY_PROPOSAL_ONLY!=='1') { console.info('factory_cron_gate_closed'); return; }\n    safeAccount(env);\n    // Fixed private GitHub branch, validated short TTL and one-use DO ledger.\n    let proposal;\n    try { proposal=await readProposal(env); }\n    catch(error) {\n      if(error?.message==='proposal_absent') { console.info('factory_cron_authenticated_idle'); return; }\n      throw error;\n    }\n    console.info('factory_cron_proposal_read');\n    const req=proposal.request;\n    const probe=req.operation==='factory.queue_probe' && req.worker_name==='cc-ordinary-worker-factory';\n    if (!probe && !/^cc-scratch-proof-[ab]$/.test(req.worker_name))\n      throw Error('cron_operation_not_admitted');\n    const create=req.operation==='ordinary_worker.create' && env.FACTORY_CREATE_ENABLED==='1';\n    const stage=req.operation==='existing_worker.scratch_version.stage' && env.FACTORY_STAGE_VERSION_ENABLED==='1';\n    const promote=req.operation==='existing_worker.scratch_version.promote' && env.FACTORY_SCRATCH_RELEASE_ENABLED==='1';\n    if(!create && !stage && !probe && !promote) throw Error('cron_operation_not_admitted');\n    const receipt=await executeOnce(env,req);\n    const expected=probe?'queue_probe_complete':create?'created_inert':promote?'promoted_verified':'staged_off_traffic';\n    if(receipt.status!==expected && receipt.status!=='failed_or_indeterminate')\n      throw Error('cron_receipt_status_rejected');\n    // A terminal failure must be visible to the private requester too. It\n    // does not authorize repeating the same request or uncertain mutation.\n    await writeReceipt(env,{...receipt,operation:req.operation,worker_name:req.worker_name});\n    await consumeProposal(env,proposal.blob_sha);\n    console.info('factory_cron_terminal_receipt_written');\n  },\n";
  // Append a scheduled() handler to the single pinned default-export object.
  src['index.js']=exactlyOnce(src['index.js'],
    '\n  },\n};','\n  },\n'+CRON_HANDLER+'};',
    'cron_handler_exact_default_export');
  src['scratch_stage.js']=exactlyOnce(src['scratch_stage.js'],
    "const ACCOUNT='ce43cd7b917d98a4bb4866d30eed99c0';",
    "const ACCOUNT='"+account+"';",'scratch_account_pin');
  src['scratch_stage.js']=exactlyOnce(src['scratch_stage.js'],
    "if(!binding || typeof binding.get!=='function')\n    throw Error('cloudflare_credentials_not_bound');\n  const bearer=await binding.get();",
    "if(!binding || (typeof binding!=='string' && typeof binding.get!=='function'))\n    throw Error('cloudflare_credentials_not_bound');\n  const bearer=typeof binding==='string'?binding:await binding.get();",
    'scratch_secret_runtime');
  src['scratch_stage.js']=src['scratch_stage.js'].replaceAll(
    'ORIGINAL_SLENDERIQ_ORDINARY_ONLY','CC_ISOLATED_ORDINARY_ONLY');
  // Isolated-only implementation; original shared factory source and pins remain unchanged.
  src['scratch_stage.js']="// Isolated disposable scratch lifecycle: exact targets, immutable source, no factory self-write.\nconst ACCOUNT='__ACCOUNT__';\nconst API='https://api.cloudflare.com/client/v4/accounts/'+ACCOUNT;\nconst RAW='https://raw.githubusercontent.com/XoticHaze/research-compute-public-/';\nconst PROD='de1c728bdb163060d946122c857f3653';\nconst TARGETS={'cc-scratch-proof-a':'f91f21416cd94c35bf144f6334e6852f','cc-scratch-proof-b':'dbe5e604ff0943b58fa5a5a394dde6b2'};\nconst ID=/^[0-9a-f]{32}$/, SHA40=/^[0-9a-f]{40}$/, SHA64=/^[0-9a-f]{64}$/;\nconst UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;\nconst MAX=32768;\nconst COMMIT='10830b83ff523f2ee30613fce1ecc1fedf905ae8';\nconst PINS={'cc-scratch-proof-a':'9d3ce1adcd34da626000d1d7a5fc2bd27a887da6b3dd12278bbc578f278af921','cc-scratch-proof-b':'b7335d64457347b61316765962c3b0c34aae9f2d0b7776ddd152cb71a18bc322'};\nconst COMPAT='2026-11-18';\nfunction requireThat(x,code){if(!x)throw Error(code);}\nasync function sha(bytes){return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),v=>v.toString(16).padStart(2,'0')).join('');}\nfunction b64(bytes){let s='';for(const v of bytes)s+=String.fromCharCode(v);return btoa(s);}\nfunction unb64(s){requireThat(typeof s==='string'&&s.length<=MAX*2,'module_readback_size_rejected');return Uint8Array.from(atob(s),c=>c.charCodeAt(0));}\nasync function bounded(resp,max){requireThat(resp.body,'body_unavailable');let n=0,parts=[];const rd=resp.body.getReader();try{while(true){const {done,value}=await rd.read();if(done)break;n+=value.byteLength;requireThat(n<=max,'body_size_rejected');parts.push(value);}}finally{rd.releaseLock();}const out=new Uint8Array(n);let p=0;for(const c of parts){out.set(c,p);p+=c.length;}return out;}\nfunction requestCheck(env,req){requireThat(env.FACTORY_ACCOUNT_ID===ACCOUNT&&Object.hasOwn(TARGETS,req.worker_name)&&ID.test(req.worker_id)&&SHA40.test(req.source_commit)&&SHA64.test(req.source_sha256),'scratch_contract_rejected');if(ACCOUNT===PROD)requireThat(TARGETS[req.worker_name]===req.worker_id&&req.source_commit===COMMIT&&PINS[req.worker_name]===req.source_sha256,'scratch_target_or_reviewed_source_rejected');}\nasync function bearer(env){const b=env.FACTORY_WORKERS_ADMIN;const t=typeof b==='string'?b:await b?.get?.();requireThat(typeof t==='string'&&t.length>=20,'admin_binding_unavailable');return t;}\nfunction diagnostic(d,e){return {status:'failed_or_indeterminate',retry_same_id:false,diagnostic:{...d,category:typeof e?.message==='string'&&/^[a-z0-9_]{1,80}$/.test(e.message)?e.message:'unexpected_failure'},bearer_returned:false};}\nasync function cf(fetcher,t,d,phase,method,path,body){d.phase=phase;d.http_status=null;d.api_error_codes=[];let resp;try{resp=await fetcher(API+path,{method,redirect:'error',headers:{authorization:'Bearer '+t,accept:'application/json',...(body===undefined?{}:{'content-type':'application/json'})},...(body===undefined?{}:{body:JSON.stringify(body)})});}catch{throw Error('cloudflare_transport_failure');}d.http_status=resp.status;let data;try{data=JSON.parse(new TextDecoder().decode(await bounded(resp,512*1024)));}catch{throw Error('cloudflare_response_invalid');}d.api_error_codes=Array.isArray(data?.errors)?data.errors.map(x=>x?.code).filter(Number.isSafeInteger).slice(0,8):[];requireThat((resp.status===200||resp.status===201)&&data?.success===true,'cloudflare_api_rejected');return data.result;}\nasync function identity(fetcher,t,d,req){const worker=await cf(fetcher,t,d,'worker_identity','GET','/workers/workers/'+req.worker_id);requireThat(worker?.id===req.worker_id&&worker?.name===req.worker_name,'worker_identity_rejected');return worker;}\nasync function sourceBytes(fetcher,d,req){d.phase='source_fetch';const resp=await fetcher(RAW+req.source_commit+'/cloudflare/ordinary-scratch-releases/'+req.worker_name+'/worker.mjs',{method:'GET',redirect:'error',headers:{accept:'text/plain'}});requireThat(resp.status===200&&!resp.redirected,'source_unavailable');const bytes=await bounded(resp,MAX);d.phase='source_digest';requireThat(bytes.length>=35&&await sha(bytes)===req.source_sha256,'source_digest_rejected');const text=new TextDecoder('utf-8',{fatal:true}).decode(bytes);requireThat(text.includes('export default')&&!text.includes('import('),'source_format_rejected');return bytes;}\nasync function readVersion(fetcher,t,d,req,id){requireThat(UUID.test(id),'version_id_rejected');const v=await cf(fetcher,t,d,'version_readback','GET','/workers/workers/'+req.worker_id+'/versions/'+id+'?include=modules');requireThat(v?.id===id&&v.main_module==='worker.mjs'&&v.compatibility_date===COMPAT&&Array.isArray(v.bindings)&&v.bindings.length===0&&Array.isArray(v.modules)&&v.modules.length===1,'version_metadata_mismatch');const m=v.modules[0];requireThat(m?.name==='worker.mjs'&&m?.content_type==='application/javascript+module'&&await sha(unb64(m.content_base64))===req.source_sha256,'version_content_mismatch');return v;}\nexport async function stageScratchVersion(env,req,fetcher=fetch){const d={phase:'contract',http_status:null,api_error_codes:[],mutation_attempted:false};try{requestCheck(env,req);requireThat(env.FACTORY_STAGE_VERSION_ENABLED==='1','scratch_stage_disabled');const t=await bearer(env);await identity(fetcher,t,d,req);const bytes=await sourceBytes(fetcher,d,req);const path='/workers/workers/'+req.worker_id+'/versions';const versions=await cf(fetcher,t,d,'existing_version_reconciliation','GET',path+'?page=1&per_page=100');requireThat(Array.isArray(versions)&&versions.length<100,'version_inventory_incomplete');let id;let reused=false;if(versions.length){requireThat(versions.length===1&&UUID.test(versions[0]?.id),'existing_version_requires_reconciliation');id=versions[0].id;await readVersion(fetcher,t,d,req,id);reused=true;}else{d.mutation_attempted=true;const made=await cf(fetcher,t,d,'version_create','POST',path+'?deploy=false',{main_module:'worker.mjs',compatibility_date:COMPAT,bindings:[],annotations:{'workers/tag':'cc-'+req.source_sha256},modules:[{name:'worker.mjs',content_type:'application/javascript+module',content_base64:b64(bytes)}]});id=made?.id;requireThat(UUID.test(id),'version_id_missing');d.version_id=id;await readVersion(fetcher,t,d,req,id);}return {status:'staged_off_traffic',account_role:'CC_ISOLATED_ORDINARY_ONLY',worker_name:req.worker_name,worker_id:req.worker_id,version_id:id,source_commit:req.source_commit,source_sha256:req.source_sha256,version_content_readback_verified:true,reused_existing_version:reused,active_deployment_unchanged_by_api:true,live_serving_verified:false,cloudflare_mutations:reused?0:1,secret_included:false};}catch(e){return diagnostic(d,e);}}\nasync function activeVersion(fetcher,t,d,req){const rows=await cf(fetcher,t,d,'deployment_inventory','GET','/workers/scripts/'+req.worker_name+'/deployments');requireThat(Array.isArray(rows?.deployments),'deployment_inventory_unverified');if(rows.deployments.length===0)return null;const latest=[...rows.deployments].sort((a,b)=>String(b.created_on).localeCompare(String(a.created_on)))[0];requireThat(UUID.test(latest?.id)&&Array.isArray(latest.versions)&&latest.versions.length===1&&latest.versions[0].percentage===100&&UUID.test(latest.versions[0].version_id),'deployment_split_or_identity_rejected');return {id:latest.id,version:latest.versions[0].version_id};}\nexport async function promoteScratchVersion(env,req,fetcher=fetch){const d={phase:'contract',http_status:null,api_error_codes:[],mutation_attempted:false};try{requestCheck(env,req);requireThat(env.FACTORY_SCRATCH_RELEASE_ENABLED==='1'&&UUID.test(req.version_id)&&(req.expected_active_version_id===null||UUID.test(req.expected_active_version_id)),'scratch_release_not_admitted');const t=await bearer(env);await identity(fetcher,t,d,req);await readVersion(fetcher,t,d,req,req.version_id);const prior=await activeVersion(fetcher,t,d,req);requireThat((prior?.version??null)===req.expected_active_version_id,'deployment_predecessor_mismatch');const p='/workers/scripts/'+req.worker_name+'/deployments';d.mutation_attempted=true;const made=await cf(fetcher,t,d,'version_promote','POST',p,{strategy:'percentage',versions:[{version_id:req.version_id,percentage:100}]});requireThat(UUID.test(made?.id),'deployment_id_missing');d.deployment_id=made.id;const after=await activeVersion(fetcher,t,d,req);requireThat(after?.id===made.id&&after?.version===req.version_id,'deployment_readback_mismatch');return {status:'promoted_verified',worker_name:req.worker_name,worker_id:req.worker_id,version_id:req.version_id,deployment_id:after.id,rollback_predecessor:prior?.version??null,source_sha256:req.source_sha256,version_content_readback_verified:true,traffic_percent:100,public_ingress_changed:false,live_serving_verified:false,cloudflare_mutations:1,bearer_returned:false};}catch(e){return diagnostic(d,e);}}\n".replace('__ACCOUNT__',account);
  src['index.js']=exactlyOnce(src['index.js'],"import {stageScratchVersion} from './scratch_stage.js';","import {stageScratchVersion,promoteScratchVersion} from './scratch_stage.js';",'scratch_release_import');
  src['index.js']=exactlyOnce(src['index.js'],"    } else if (req.operation==='existing_worker.scratch_version.stage') {","    } else if (req.operation==='existing_worker.scratch_version.promote') {\n      result=await promoteScratchVersion(env,req);\n    } else if (req.operation==='existing_worker.scratch_version.stage') {",'scratch_release_dispatch');
  src['policy.js']=exactlyOnce(src['policy.js'],"'existing_worker.scratch_version.stage']);","'existing_worker.scratch_version.stage','existing_worker.scratch_version.promote']);",'scratch_release_operation');
  src['policy.js']=exactlyOnce(src['policy.js'],"    : req.operation === 'existing_worker.scratch_version.stage'","    : req.operation === 'existing_worker.scratch_version.promote' ? ['worker_id','source_commit','source_sha256','version_id','expected_active_version_id']\n    : req.operation === 'existing_worker.scratch_version.stage'",'scratch_release_fields');
  src['policy.js']=exactlyOnce(src['policy.js'],"  return req;","  if(req.operation==='existing_worker.scratch_version.promote' && (!/^cc-scratch-proof-[ab]$/.test(req.worker_name)||!HEX32.test(req.worker_id)||!/^[a-f0-9]{40}$/.test(req.source_commit)||!/^[a-f0-9]{64}$/.test(req.source_sha256)||!/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(req.version_id)||(req.expected_active_version_id!==null&&!/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(req.expected_active_version_id)))) throw Error('scratch_release_contract_rejected');\n  return req;",'scratch_release_validation');
  src['policy.js']=exactlyOnce(src['policy.js'],'const RESERVED = [',
    "const RESERVED = [\n  'cc-ordinary-worker-factory',",'protected_factory_name');
  src['queue.js']=exactlyOnce(src['queue.js'],
    "if (!env.FACTORY_QUEUE_GITHUB_TOKEN ||\n      typeof env.FACTORY_QUEUE_GITHUB_TOKEN.get!=='function')\n    throw Error('queue_binding_absent');\n  const value=await env.FACTORY_QUEUE_GITHUB_TOKEN.get();",
    "if (!env.FACTORY_QUEUE_GITHUB_TOKEN ||\n      (typeof env.FACTORY_QUEUE_GITHUB_TOKEN!=='string' &&\n       typeof env.FACTORY_QUEUE_GITHUB_TOKEN.get!=='function'))\n    throw Error('queue_binding_absent');\n  const value=typeof env.FACTORY_QUEUE_GITHUB_TOKEN==='string'?\n    env.FACTORY_QUEUE_GITHUB_TOKEN:await env.FACTORY_QUEUE_GITHUB_TOKEN.get();",
    'github_queue_secret_runtime');
  src['queue.js']=exactlyOnce(src['queue.js'],"  if (!r.ok) throw Error('proposal_unavailable');","  if (r.status===404) {\n    const directory=await fetch(ROOT+'cloudflare-factory?ref='+BRANCH,{headers:headers(bearer),redirect:'manual'});\n    if (!directory.ok) throw Error('queue_repository_or_branch_unavailable');\n    const entries=await directory.json();\n    if (!Array.isArray(entries) || !entries.some(x=>x?.path==='cloudflare-factory/attempts' && x?.type==='dir')) throw Error('queue_directory_identity_unverified');\n    if (entries.some(x=>x?.path===PROPOSAL)) throw Error('proposal_read_inconsistent');\n    throw Error('proposal_absent');\n  }\n  if (!r.ok) throw Error('proposal_unavailable');",'queue_404_requires_authenticated_directory');
  src['queue.js']+="\nexport async function consumeProposal(env,blobSha) {\n  if(!SHA40.test(String(blobSha||'')))throw Error('proposal_sha_rejected');\n  const bearer=await queueToken(env);\n  const response=await fetch(ROOT+PROPOSAL,{\n    method:'DELETE',headers:{...headers(bearer),'content-type':'application/json'},\n    body:JSON.stringify({message:'factory consume '+blobSha.slice(0,10),\n      sha:blobSha,branch:BRANCH}),redirect:'manual'\n  });\n  if(response.status!==200)throw Error('proposal_consume_indeterminate');\n  const data=await response.json();\n  if(!SHA40.test(String(data?.commit?.sha||'')))\n    throw Error('proposal_consume_indeterminate');\n  return {consumed:true,cloudflare_mutations:0};\n}\n";
  src['index.js']=exactlyOnce(src['index.js'],"import {readProposal,writeReceipt} from './queue.js';","import {readProposal,writeReceipt,consumeProposal} from './queue.js';",'fixed_queue_consume_import');
  src['queue.js']=exactlyOnce(src['queue.js'],
    "  const request=validateRequest(parsed);",
    "  let request;\n  if (parsed?.operation==='factory.queue_probe') {\n    const now=Math.floor(Date.now()/1000);\n    if (Object.keys(parsed).sort().join(',')!=='expires_at,operation,request_id,schema,worker_id,worker_name' || parsed.schema!=='commandcenter.cloudflare.factory_request.v1' || !ID32.test(parsed.request_id) || !ID32.test(parsed.worker_id) || (parsed.worker_name!=='cc-ordinary-worker-factory') || !Number.isInteger(parsed.expires_at) || parsed.expires_at<now || parsed.expires_at>now+300) throw Error('queue_probe_contract_rejected');\n    request=parsed;\n  } else request=validateRequest(parsed);",'fixed_readonly_probe_contract');
  src['index.js']=exactlyOnce(src['index.js'],
    "    if (req.operation==='ordinary_worker.create') {",
    "    if (req.operation==='factory.queue_probe') {\n      const detail={category:'binding_unavailable',binding_type:'absent',http_status:null,api_error_codes:[]};\n      let bearer;\n      const binding=env.FACTORY_WORKERS_ADMIN;\n      detail.binding_type=typeof binding==='string'?'secret_text':binding && typeof binding.get==='function'?'secrets_store_secret':'absent_or_unsupported';\n      try { bearer=await token(binding); } catch {}\n      if(bearer && !/^[A-Za-z0-9._~+\\\\/=-]+$/.test(bearer)) { detail.category='credential_format_rejected'; bearer=undefined; }\n      if(bearer) {\n        detail.category='transport_failure';\n        let resp;\n        try {resp=await fetch(API+'/accounts/'+ORDINARY_ACCOUNT+'/workers/workers/'+req.worker_id,{method:'GET',headers:{authorization:'Bearer '+bearer,accept:'application/json'},redirect:'manual'});} catch {}\n        if(resp) {\n          detail.http_status=resp.status;\n          detail.category=resp.status===401?'authentication_rejected':resp.status===403?'authorization_rejected':resp.status===404?'resource_not_found_or_hidden':resp.status===429?'rate_limited':resp.status>=500?'upstream_error':resp.status===200?'response_unverified':'unexpected_http_status';\n          let data;\n          try {data=await resp.json();} catch {}\n          if(data && Array.isArray(data.errors)) detail.api_error_codes=data.errors.map(e=>e?.code).filter(c=>Number.isSafeInteger(c)&&c>=0&&c<=99999999).slice(0,8);\n          if(resp.status===200) detail.category=!data?'invalid_json':data.success!==true?'api_success_false':data.result?.id!==req.worker_id || data.result?.name!=='cc-ordinary-worker-factory'?'identity_mismatch':'verified';\n        }\n      }\n      result={status:'queue_probe_complete',worker_name:'cc-ordinary-worker-factory',github_queue_read_verified:true,cloudflare_admin_read_verified:detail.category==='verified',cloudflare_admin_diagnostic:detail,cloudflare_mutations:0,bearer_returned:false};\n    } else if (req.operation==='ordinary_worker.create') {",'fixed_readonly_probe_execution');
  if(account==='de1c728bdb163060d946122c857f3653') src['queue.js']=exactlyOnce(src['queue.js'],"!ID32.test(parsed.worker_id)","parsed.worker_id!=='822f7bffea8a499990fc92d1ae90b4ee'",'production_probe_identity_pin');
  const config={
    '$schema':'node_modules/wrangler/config-schema.json',
    name:FACTORY_NAME,account_id:account,main:'src/index.js',
    compatibility_date:'2026-11-23',workers_dev:true,preview_urls:false,
    triggers:{crons:['* * * * *']},
    durable_objects:{bindings:[{name:'FACTORY_LEDGER',class_name:'FactoryLedger'}]},
    exports:{FactoryLedger:{type:'durable-object',state:'created',storage:'sqlite'}},
    vars:{
      FACTORY_ACCOUNT_ID:account,
      FACTORY_INSTALLATION_ROLE:'CC_ISOLATED_ORDINARY_ONLY',
// Access AUD and owner-email allowlist are Cloudflare Worker ENCRYPTED SECRETS,
      // configured only after Worker Access All traffic is installed. Never
      // emit them as blank vars: Wrangler would later overwrite their runtime
      // secrets during a code-only deploy.
      FACTORY_SCHEDULED_POLL_ENABLED:'0',
      FACTORY_EXECUTOR_ENABLED:'0', FACTORY_CREATE_ENABLED:'0',
      FACTORY_INSPECT_ENABLED:'0', FACTORY_SCOPED_TOKEN_ENABLED:'0',
      FACTORY_STAGE_VERSION_ENABLED:'0',
      FACTORY_SCRATCH_RELEASE_ENABLED:'0',
      FACTORY_MACHINE_READONLY_ENABLED:'0', FACTORY_MACHINE_INSPECT_ENABLED:'0',
      FACTORY_PROPOSAL_ONLY:'1'
    }
  };
  if(existsSync(join(outDir,'wrangler.jsonc'))) {
    const prior=JSON.parse(readFileSync(join(outDir,'wrangler.jsonc'),'utf8'));
    if(prior.account_id!==account)
      throw Error('GENERATED_ACCOUNT_MISMATCH_REFUSE_OVERWRITE');
  }
  mkdirSync(join(outDir,'src'),{recursive:true});
  const sha=x=>createHash('sha256').update(x).digest('hex');
  for(const [name,value] of Object.entries(src))
    writeFileSync(join(outDir,'src',name),value);
  const cfg=JSON.stringify(config,null,2)+'\n';
  writeFileSync(join(outDir,'wrangler.jsonc'),cfg);
  const manifest={
    schema:'commandcenter.cloudflare.isolated_ordinary_factory_manifest.v1',
    factory_name:FACTORY_NAME,account_id:account,
    role:'CC_ISOLATED_ORDINARY_ONLY',
    status:'SOURCE_PREPARED_MUTATION_FLAGS_ZERO',
    source_sha256:Object.fromEntries(Object.entries(src).map(([name,s])=>[name,sha(s)])),
    wrangler_sha256:sha(cfg),source_blob_pins:SOURCE_PINS,
    cloudflare_mutations:0,credentials_in_output:false
  };
  writeFileSync(join(outDir,'manifest.json'),JSON.stringify(manifest,null,2)+'\n');
  return manifest;
}
if(process.argv[1] && resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  const argv=process.argv.slice(2);
  if(argv.length!==2||argv[0]!=='--account-id'){
    console.error('Usage: node scripts/prepare.mjs --account-id NEW_ORDINARY_ACCOUNT_ID');
    process.exit(2);
  }
  try{
    const out=build(argv[1]);
    console.log('ISOLATED_ORDINARY_FACTORY_PREPARED=1');
    console.log('ACCOUNT_ID='+out.account_id);
    console.log('FACTORY_MUTATION_FLAGS=ALL_ZERO');
    console.log('ACCOUNT_SECRET_EXPORTED=0');
  }catch(e){console.error('FACTORY_PREPARE_REJECTED='+e.message);process.exit(1);}
}
