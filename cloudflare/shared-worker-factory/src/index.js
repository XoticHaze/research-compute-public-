import { validateRequest, workerEditorPolicy } from './policy.js';

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
export default {
  async fetch(request,env,ctx) {
    const url=new URL(request.url);
    if (url.pathname!=='/v1/status' && url.pathname!=='/v1/execute')
      return response({error:'not_found'},404);
    try {
      await ownerOnly(env,ctx);
      safeAccount(env);
      if (url.pathname==='/v1/status'&&request.method==='GET') {
        return response({schema:'commandcenter.cloudflare.factory_status.v1',
          admitted:enabled(env.FACTORY_EXECUTOR_ENABLED),
          ordinary_creation:enabled(env.FACTORY_CREATE_ENABLED),
          optional_scoped_editor:enabled(env.FACTORY_SCOPED_TOKEN_ENABLED),
          token_values_returned:false});
      }
      if (request.method!=='POST' ||
          !enabled(env.FACTORY_EXECUTOR_ENABLED))
        return response({error:'not_admitted'},403);
      if (request.headers.get('content-type')!=='application/json')
        return response({error:'bad_request'},400);
      const origin=request.headers.get('origin');
      if(origin!==url.origin || request.headers.get('sec-fetch-site')!=='same-origin')
        return response({error:'same_origin_required'},403);
      const raw=await request.text();
      if (!raw || new TextEncoder().encode(raw).length>MAX_BODY)
        return response({error:'bad_request'},400);
      const req=validateRequest(JSON.parse(raw));
      await logState(env,req.request_id,'claim',
        {request_id:req.request_id,operation:req.operation});
      let result;
      try {
        result=req.operation==='ordinary_worker.create'
          ?await ordinaryCreate(env,req):await issueEditor(env,req);
      } catch {
        await logState(env,req.request_id,'finish',
          {request_id:req.request_id,result:{status:'failed_or_indeterminate'}});
        return response({request_id:req.request_id,
          status:'failed_or_indeterminate',retry_same_id:false},409);
      }
      await logState(env,req.request_id,'finish',{request_id:req.request_id,result});
      return response({schema:'commandcenter.cloudflare.factory_receipt.v1',
        request_id:req.request_id,...result});
    } catch {
      return response({error:'denied_or_unavailable'},403);
    }
  },
};
