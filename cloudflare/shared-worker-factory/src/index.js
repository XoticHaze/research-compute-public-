import { validateRequest, workerEditorPolicy } from './policy.js';
import {verifyFactoryMachineOidc} from './machine_oidc.js';
import {stageScratchVersion} from './scratch_stage.js';
import {readProposal,writeReceipt} from './queue.js';
import {UI,SCRIPT} from './ui.js';

// Permanent, reusable, ordinary-account management executor. It is NOT a
// Cloudflare-neutral signer, an unrestricted shell, or a GitHub deploy token.
const API = 'https://api.cloudflare.com/client/v4';
const ORDINARY_ACCOUNT = 'ce43cd7b917d98a4bb4866d30eed99c0';
const DO_NAME = 'shared-worker-factory-v1';
const ID32 = /^[a-f0-9]{32}$/;
const MAX_BODY = 4096;

function response(body, status=200) {
  return new Response(JSON.stringify(body), {status, headers:{
    'content-type':'application/json; charset=utf-8',
    'cache-control':'private, no-store',
    'x-content-type-options':'nosniff',
    'referrer-policy':'no-referrer',
    'content-security-policy':"default-src 'none'",
  }});
}
function enabled(value) { return value === '1'; }
async function ownerOnly(env,ctx) {
  if (!ctx?.access || !env.FACTORY_ACCESS_AUD ||
      ctx.access.aud !== env.FACTORY_ACCESS_AUD) throw Error('access_required');
  const identity=await ctx.access.getIdentity();
  const email=String(identity?.email||'').trim().toLowerCase();
  const allowed=String(env.FACTORY_ALLOWED_EMAILS||'').toLowerCase()
    .split(',').map(x=>x.trim()).filter(Boolean);
  if (!email || !allowed.includes(email)) throw Error('owner_denied');
}
function safeAccount(env) {
  if (String(env.FACTORY_ACCOUNT_ID||'') !== ORDINARY_ACCOUNT)
    throw Error('wrong_account');
  return ORDINARY_ACCOUNT;
}
async function token(binding) {
  if (!binding || typeof binding.get!=='function') throw Error('secret_binding_absent');
  const value=await binding.get();
  if (typeof value!=='string'||value.length<20) throw Error('secret_unavailable');
  return value;
}
async function cf(bearer,method,path,body,allowed=[200]) {
  // Caller provides only fixed, locally constructed paths. No URLs in requests.
  if (!path.startsWith('/accounts/'+ORDINARY_ACCOUNT+'/') ||
      path.includes('..') || !['GET','POST','DELETE'].includes(method))
    throw Error('cloudflare_path_rejected');
  const init={method,headers:{
    authorization:'Bearer '+bearer,accept:'application/json',
  },redirect:'manual'};
  if (body !== undefined) {
    init.headers['content-type']='application/json';
    init.body=JSON.stringify(body);
  }
  const resp=await fetch(API+path,init);
  if (!allowed.includes(resp.status)) throw Error('cloudflare_operation_rejected');
  const data=await resp.json();
  if (!data || data.success!==true) throw Error('cloudflare_operation_rejected');
  return data.result;
}
function ledger(env,requestId) {
  if (!env.FACTORY_LEDGER) throw Error('ledger_binding_absent');
  return env.FACTORY_LEDGER.get(
    env.FACTORY_LEDGER.idFromName(DO_NAME+':'+requestId));
}
async function logState(env,requestId,op,body) {
  const res=await ledger(env,requestId).fetch(
    new Request('https://factory-ledger/'+op,{method:'POST',
      headers:{'content-type':'application/json'},
      body:JSON.stringify(body)}));
  if (!res.ok) throw Error('request_replayed_or_ledger_unavailable');
}
async function inspectExisting(env,req) {
  // Owner-only, exact immutable name + ID, original ordinary account only.
  // This is not token enumeration, project deployment, signing or a mutation.
  if (!enabled(env.FACTORY_INSPECT_ENABLED)) throw Error('operation_disabled');
  const t=await token(env.FACTORY_WORKERS_ADMIN);
  const found=await cf(t,'GET',
    '/accounts/'+ORDINARY_ACCOUNT+'/workers/workers/'+req.worker_id,
    undefined,[200]);
  if (String(found?.id||'')!==req.worker_id ||
      found?.name!==req.worker_name)
    throw Error('worker_identity_rejected');
  return {status:'existing_worker_identity_verified',
    account_role:'ORIGINAL_SLENDERIQ_ORDINARY_ONLY',
    worker_name:req.worker_name,worker_id:req.worker_id,
    source_version_verified:false,service_deployment_verified:false,
    bearer_returned:false,cloudflare_mutations:0};
}
async function ordinaryCreate(env,req) {
  if (!enabled(env.FACTORY_CREATE_ENABLED)) throw Error('operation_disabled');
  const t=await token(env.FACTORY_WORKERS_ADMIN);
  // No script upload, Workers.dev, preview URLs, deployment, or code selection.
  const made=await cf(t,'POST','/accounts/'+ORDINARY_ACCOUNT+'/workers/workers',
    {name:req.worker_name,subdomain:{enabled:false,previews_enabled:false}},
    [200,201]);
  const id=String(made?.id||'');
  if (!ID32.test(id) || made?.name!==req.worker_name)
    throw Error('creation_readback_indeterminate');
  const check=await cf(t,'GET',
    '/accounts/'+ORDINARY_ACCOUNT+'/workers/workers/'+id,undefined,[200]);
  if (check?.id!==id || check?.name!==req.worker_name)
    throw Error('creation_readback_indeterminate');
  return {status:'created_inert',worker_name:req.worker_name,
          worker_id:id,script_deployed:false,public_traffic_enabled:false};
}
async function issueEditor(env,req) {
  if (!enabled(env.FACTORY_SCOPED_TOKEN_ENABLED))
    throw Error('operation_disabled');
  if (!env.FACTORY_TOKEN_ISSUER || !env.FACTORY_SECRET_WRITER ||
      !ID32.test(String(env.FACTORY_SECRETS_STORE_ID||'')))
    throw Error('token_issuer_unconfigured');
  const workerAdmin=await token(env.FACTORY_WORKERS_ADMIN);
  const target=await cf(workerAdmin,'GET',
    '/accounts/'+ORDINARY_ACCOUNT+'/workers/workers/'+req.worker_id,
    undefined,[200]);
  if (target?.id!==req.worker_id || target?.name!==req.worker_name)
    throw Error('worker_identity_rejected');
  const issuer=await token(env.FACTORY_TOKEN_ISSUER);
  const writer=await token(env.FACTORY_SECRET_WRITER);
  const name='CC-Scoped-Editor-'+req.worker_name+'-'+req.request_id.slice(0,12);
  const expiresOn=new Date(Date.now()+req.token_ttl_hours*3600000).toISOString();
  const result=await cf(issuer,'POST',
    '/accounts/'+ORDINARY_ACCOUNT+'/tokens',{
      name,expires_on:expiresOn,
      policies:workerEditorPolicy(ORDINARY_ACCOUNT,req.worker_id),
    },[200]);
  let issuedId=String(result?.id||'');
  let issuedValue=String(result?.value||'');
  if (!ID32.test(issuedId)||issuedValue.length<20)
    throw Error('token_creation_indeterminate');
  const secretName='CC_WORKER_EDITOR_'+req.request_id.toUpperCase();
  try {
    await cf(writer,'POST','/accounts/'+ORDINARY_ACCOUNT+
      '/secrets_store/stores/'+env.FACTORY_SECRETS_STORE_ID+'/secrets',
      [{name:secretName,value:issuedValue,scopes:['workers'],
        comment:'Bounded existing-Worker Editor token; managed by CommandCenter factory'}],
      [200,201]);
  } catch {
    // Fail closed, never return the bearer. A failed revoke is indeterminate.
    try {
      await cf(issuer,'DELETE','/accounts/'+ORDINARY_ACCOUNT+
        '/tokens/'+issuedId,undefined,[200,204]);
    } catch { throw Error('token_storage_and_revoke_indeterminate'); }
    throw Error('token_storage_failed_revoked');
  } finally {
    issuedValue=''; // Never enter receipts, logs, Git or response payloads.
  }
  return {status:'scoped_editor_stored',worker_name:req.worker_name,
    worker_id:req.worker_id,secret_name:secretName,
    token_id_suffix:issuedId.slice(-8),expires_at:expiresOn,
    bearer_returned:false,github_secret_created:false};
}
export class FactoryLedger {
  constructor(state) {this.state=state;}
  async fetch(request) {
    const url=new URL(request.url);
    if(request.method!=='POST' || !['/claim','/finish'].includes(url.pathname))
      return response({error:'not_found'},404);
    let body;
    try {body=await request.json();}catch{return response({error:'invalid'},400);}
    if (!body || typeof body!=='object' || Array.isArray(body) ||
        !ID32.test(String(body.request_id||'')))
      return response({error:'invalid'},400);
    const record=await this.state.storage.transaction(async(txn)=>{
      const key='request';
      const old=await txn.get(key);
      if(url.pathname==='/claim'){
        if(old) return null;
        const next={request_id:body.request_id,state:'claimed',
          operation:body.operation,claimed_at:Date.now()};
        await txn.put(key,next);
        return next;
      }
      if(!old || old.state!=='claimed' || old.request_id!==body.request_id)
        return null;
      const next={...old,state:'terminal',result:body.result,
        finished_at:Date.now()};
      await txn.put(key,next);
      return next;
    });
    return record?response({ok:true}):response({error:'conflict'},409);
  }
}
async function executeOnce(env,req) {
  await logState(env,req.request_id,'claim',
    {request_id:req.request_id,operation:req.operation});
  let result;
  try {
    if (req.operation==='ordinary_worker.create') {
      result=await ordinaryCreate(env,req);
    } else if (req.operation==='existing_worker.editor_token.issue') {
      result=await issueEditor(env,req);
    } else if (req.operation==='existing_worker.inspect') {
      result=await inspectExisting(env,req);
    } else if (req.operation==='existing_worker.scratch_version.stage') {
      // Separate stage flag, never a live deploy or source-replacement command.
      if (!enabled(env.FACTORY_STAGE_VERSION_ENABLED))
        throw Error('operation_disabled');
      result=await stageScratchVersion(env,req);
    } else {
      throw Error('unknown_operation');
    }
  } catch {
    await logState(env,req.request_id,'finish',
      {request_id:req.request_id,result:{status:'failed_or_indeterminate'}});
    return {schema:'commandcenter.cloudflare.factory_receipt.v1',
      request_id:req.request_id,status:'failed_or_indeterminate',
      retry_same_id:false};
  }
  await logState(env,req.request_id,'finish',{request_id:req.request_id,result});
  return {schema:'commandcenter.cloudflare.factory_receipt.v1',
    request_id:req.request_id,...result};
}
function sameOrigin(request,url) {
  return request.headers.get('content-type')==='application/json'
    && request.headers.get('origin')===url.origin
    && request.headers.get('sec-fetch-site')==='same-origin';
}
async function jsonBody(request,max=MAX_BODY) {
  const raw=await request.text();
  if(!raw || new TextEncoder().encode(raw).length>max)
    throw Error('bad_request');
  return JSON.parse(raw);
}
async function machineReadOnly(request,env,url) {
  // No owner impersonation. A directly verified GitHub OIDC principal does not
  // imply any mutation, Cloudflare admin or protected neutral signing rights.
  safeAccount(env);
  if(request.method!=='POST' || !enabled(env.FACTORY_MACHINE_READONLY_ENABLED))
    return response({error:'machine_route_not_admitted'},403);
  const authorization=request.headers.get('authorization')||'';
  const runId=request.headers.get('x-cc-github-run-id')||'';
  if(!authorization.startsWith('Bearer ') || authorization.length>16010 ||
     !/^[0-9]{4,20}$/.test(runId))
    return response({error:'unauthorized_machine_identity'},401);
  let machine;
  try {machine=await verifyFactoryMachineOidc(authorization.slice(7),runId);}
  catch {return response({error:'unauthorized_machine_identity'},401);}
  if(url.pathname==='/v1/machine/readiness')
    return response({
      schema:'commandcenter.cloudflare.factory_machine_readiness.v1',
      identity_verified:machine.identity_verified,
      github_run_id:machine.run_id,
      account_role:'ORIGINAL_SLENDERIQ_ORDINARY_ONLY',
      generic_executor_admitted:enabled(env.FACTORY_EXECUTOR_ENABLED),
      machine_inspection_admitted:enabled(env.FACTORY_MACHINE_INSPECT_ENABLED),
      machine_creation_admitted:false,
      credentials_or_private_keys_returned:false,
      cloudflare_mutations:0
    });
  if(url.pathname!=='/v1/machine/inspect' ||
     !enabled(env.FACTORY_EXECUTOR_ENABLED) ||
     !enabled(env.FACTORY_MACHINE_INSPECT_ENABLED) ||
     !enabled(env.FACTORY_INSPECT_ENABLED))
    return response({error:'machine_operation_not_admitted'},403);
  let payload;
  try {payload=validateRequest(await jsonBody(request));}
  catch {return response({error:'invalid_machine_request'},400);}
  if(payload.operation!=='existing_worker.inspect')
    return response({error:'machine_operation_not_admitted'},403);
  // Reuses the same durable one-shot journal as owner-approved commands.
  const receipt=await executeOnce(env,payload);
  return response({
    ...receipt,
    github_run_id:machine.run_id,
    identity_verified:true,
    machine_path:true,
    mutation_permissions_granted:false
  },receipt.status==='failed_or_indeterminate'?409:200);
}

export default {
  async fetch(request,env,ctx) {
    const url=new URL(request.url);
    if (!new Set(['/v1/status','/v1/execute','/v1/proposal',
      '/v1/approve','/operator/factory','/operator/factory.js',
      '/v1/machine/readiness','/v1/machine/inspect'])
      .has(url.pathname)) return response({error:'not_found'},404);
    try {
      if(url.pathname==='/v1/machine/readiness' ||
         url.pathname==='/v1/machine/inspect')
        return await machineReadOnly(request,env,url);
      await ownerOnly(env,ctx);
      safeAccount(env);
      if(url.pathname==='/v1/status' && request.method==='GET')
        return response({schema:'commandcenter.cloudflare.factory_status.v1',
          admitted:enabled(env.FACTORY_EXECUTOR_ENABLED),
          ordinary_creation:enabled(env.FACTORY_CREATE_ENABLED),
          exact_readonly_inspection:enabled(env.FACTORY_INSPECT_ENABLED),
          optional_scoped_editor:enabled(env.FACTORY_SCOPED_TOKEN_ENABLED),
          scratch_version_stage_only:enabled(env.FACTORY_STAGE_VERSION_ENABLED),
          proposal_only:env.FACTORY_PROPOSAL_ONLY!=='0',
          token_values_returned:false});
      if(url.pathname==='/operator/factory' && request.method==='GET')
        return new Response(UI,{headers:{
          'content-type':'text/html; charset=utf-8',
          'cache-control':'private, no-store',
          'x-frame-options':'DENY',
          'content-security-policy':"default-src 'none'; script-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'",
        }});
      if(url.pathname==='/operator/factory.js' && request.method==='GET')
        return new Response(SCRIPT,{headers:{
          'content-type':'application/javascript; charset=utf-8',
          'cache-control':'private, no-store',
          'content-security-policy':"default-src 'none'",
        }});
      if(!enabled(env.FACTORY_EXECUTOR_ENABLED))
        return response({error:'not_admitted'},403);
      if(url.pathname==='/v1/proposal' && request.method==='GET') {
        const proposal=await readProposal(env);
        return response({schema:'commandcenter.cloudflare.factory_pending.v1',
          ...proposal,executed:false,owner_approval_required:true});
      }
      if(request.method!=='POST' || !sameOrigin(request,url))
        return response({error:'same_origin_required'},403);
      if(url.pathname==='/v1/approve') {
        const approval=await jsonBody(request,512);
        if(!approval || Object.keys(approval).sort().join(',')!==
              'expected_blob_sha,request_id' ||
            !ID32.test(approval.request_id) ||
            !/^[a-f0-9]{40}$/.test(approval.expected_blob_sha))
          return response({error:'bad_approval'},400);
        const {request:pending,blob_sha}=await readProposal(env);
        if(pending.request_id!==approval.request_id ||
            blob_sha!==approval.expected_blob_sha)
          return response({error:'stale_proposal'},409);
        const receipt=await executeOnce(env,pending);
        try {
          const persisted=await writeReceipt(env,receipt);
          return response({...receipt,private_receipt_path:persisted.path},
            receipt.status==='failed_or_indeterminate'?409:200);
        } catch {
          return response({request_id:pending.request_id,
            status:'receipt_transport_unverified',retry_same_id:false},503);
        }
      }
      if(url.pathname==='/v1/execute' &&
          env.FACTORY_PROPOSAL_ONLY==='0') {
        const req=validateRequest(await jsonBody(request));
        const receipt=await executeOnce(env,req);
        return response(receipt,receipt.status==='failed_or_indeterminate'?409:200);
      }
      return response({error:'forbidden'},403);
    } catch {
      return response({error:'denied_or_unavailable'},403);
    }
  },
};
