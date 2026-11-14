// Independently administered neutral-account Cloudflare ONLY Pi root authorization service.
// This script MUST NOT be deployed by GitHub-controlled Worker credentials.
// No private key is accepted from a request, repository, or caller.
import {
  PiOwnerApprovalState,
  canonicalPiJson,
  validatePiCloudRootReleaseApproval,
  publishPiRootReleaseGrant,
  readPiRootReleaseReceipt,
} from './pi_owner_approval.js';
export { PiOwnerApprovalState } from './pi_owner_approval.js';

const OWNER_ID = 'cc-pi4-owner-v1';
const SHA256 = /^[a-f0-9]{64}$/;
const MAX_BODY = 8192;
const encoder = new TextEncoder();

function response(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: {
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'private, no-store',
    'referrer-policy': 'no-referrer',
    'x-content-type-options': 'nosniff',
    'content-security-policy': "default-src 'none'",
  }});
}
function strict(v, fields) {
  if (!v || typeof v !== 'object' || Array.isArray(v)
      || Object.keys(v).length !== fields.length
      || !fields.every(k => Object.hasOwn(v,k))) throw Error('exact_fields_required');
}
function flag(value) { return value === '1'; }
function ownerAllowed(env,email) {
  const allowed=String(env.PI_OWNER_SIGNER_ALLOWED_EMAILS||'')
    .toLowerCase().split(',').map(x=>x.trim()).filter(Boolean);
  return allowed.length>0 && allowed.includes(email);
}
async function owner(request,env,ctx) {
  // 'ctx.access' is inserted only on *direct* Cloudflare Access authenticated
  // Worker invocations. Service bindings do NOT propagate owner identity.
  if (!ctx?.access || !String(env.PI_OWNER_ACCESS_AUD || '')
      || ctx.access.aud !== env.PI_OWNER_ACCESS_AUD) throw Error('cloudflare_access_required');
  const identity=await ctx.access.getIdentity();
  const email=String(identity?.email||'').trim().toLowerCase();
  if (!email || !ownerAllowed(env,email)) throw Error('pi_owner_email_not_admitted');
  return {email,sub:'cf-access-authenticated:'+email};
}
function requireBrowser(request) {
  const url=new URL(request.url);
  const origin=request.headers.get('origin');
  const site=request.headers.get('sec-fetch-site');
  const contentType=request.headers.get('content-type')||'';
  if (origin!==url.origin || (site && site!=='same-origin')
      || !/^application\/json(?:\s*;\s*charset\s*=\s*utf-8)?$/i.test(contentType))
    throw Error('same_origin_json_required');
}
async function body(request) {
  const raw=await request.text();
  if (encoder.encode(raw).length>MAX_BODY) throw Error('request_oversized');
  const parsed=JSON.parse(raw);
  if (parsed===null || typeof parsed!=='object' || Array.isArray(parsed)) {
    throw Error('request_object_required');
  }
  return parsed;
}
function signer(env) {
  if (!env.PI_OWNER_APPROVER) throw Error('protected_signer_binding_missing');
  return env.PI_OWNER_APPROVER.get(env.PI_OWNER_APPROVER.idFromName(OWNER_ID));
}
async function doRequest(env,method,path,payload) {
  const init={method};
  if (method==='POST') {
    init.headers={'content-type':'application/json'};
    init.body=canonicalPiJson(payload);
  }
  const raw=await signer(env).fetch(new Request('https://pi-owner.internal'+path,init));
  const data=await raw.json();
  if (!raw.ok) throw Error(String(data?.error||'pi_owner_signer_rejected'));
  return data;
}
async function status(env) {
  const raw=await doRequest(env,'GET','/status');
  return {
    schema:'commandcenter.pi.cloudflare_primary_signer_status.v1',
    initialized:raw.initialized===true,
    enrolled:raw.enrolled===true,
    public_key_sha256:typeof raw.public_key_sha256==='string'?raw.public_key_sha256:null,
    queue_configured:Boolean(env.PI_OWNER_QUEUE_GITHUB_TOKEN),
    root_public_fingerprint_configured:SHA256.test(String(env.PI_OWNER_ENROLLED_PUB_SHA256||'')),
    isolated_cloudflare_signer_enabled:flag(env.PI_OWNER_SIGNER_ENABLED),
    first_issue_enabled:flag(env.PI_OWNER_FIRST_ISSUE_ENABLED),
    root_enroll_enabled:flag(env.PI_OWNER_FIRST_ENROLL_ENABLED),
    normal_release_enabled:flag(env.PI_OWNER_NORMAL_RELEASE_ENABLED),
  };
}
function unsignedGrant(request) {
  return {
    schema:'commandcenter.pi.release_request_approval.v1',
    request_id:request.request_id,
    source_sha:request.source_sha,
    expected_release:request.expected_release,
    expires_at:request.expires_at,
  };
}
async function readPendingCCRootRelease(env) {
  // Fixed private Git transport, not arbitrary repository/path/URL input.
  // The owner sees the current pending proposal and must explicitly review it.
  const token=String(env.PI_OWNER_QUEUE_GITHUB_TOKEN||'');
  if(token.length<20) throw Error('pi_owner_queue_credential_missing');
  const url='https://api.github.com/repos/XoticHaze/CommandCenter-gate-control/'
    +'contents/pi-node/release-request.json?ref=pi-node-inbox';
  const remote=await fetch(url,{
    headers:{authorization:'Bearer '+token,accept:'application/vnd.github+json',
      'x-github-api-version':'2022-11-28'},redirect:'manual',
  });
  if(!remote.ok) throw Error('pi_owner_pending_release_unavailable');
  const file=await remote.json();
  if(!/^[a-f0-9]{40}$/.test(String(file?.sha||''))
      || file.encoding!=='base64'
      || !Number.isInteger(file.size) || file.size<1 || file.size>4096
      || typeof file.content!=='string') throw Error('pi_owner_pending_release_invalid');
  const raw=atob(file.content.replace(/\s/g,''));
  if(raw.length>4096) throw Error('pi_owner_pending_release_oversized');
  const request=JSON.parse(raw);
  await validatePiCloudRootReleaseApproval(unsignedGrant(request),request);
  return {schema:'commandcenter.pi.pending_root_review.v1',
    request,review_only:true,cloudflare_signature_issued:false};
}
const page=`<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cloudflare Pi root approval</title>
<style>body{font:16px system-ui;margin:2rem auto;max-width:48rem;padding:1rem;background:#101822;color:#e8f1ff}
section{border:1px solid #455872;border-radius:10px;padding:1rem;margin:1rem 0}
textarea,input{box-sizing:border-box;width:100%;padding:.6rem;color:#fff;background:#192a3c;border:1px solid #8ba5c9}
textarea{height:9rem}button{margin:.5rem 0;padding:.7rem 1rem}
pre{white-space:pre-wrap;overflow-wrap:anywhere}small{color:#aebed0}</style></head><body>
<h1>Cloudflare primary Pi root release</h1>
<p>This is the separately protected Cloudflare owner signer. Each request binds one source SHA,
one installed predecessor, expiry and request ID. Pi root independently verifies before installation.</p>
<section><h2>Readiness</h2><button id="refresh">Check protected signer</button><pre id="status"></pre></section>
<section><h2>One-time owner initialization</h2>
<p><small>Only when independently approved and first issuance is enabled by Cloudflare admin.</small></p>
<label>Owner activation code (not saved)</label><input id="activation" type="password" autocomplete="off">
<button id="initialize">Issue initial Cloudflare Ed25519 key</button></section>
<section><h2>One-time public-key enrollment acknowledgement</h2>
<p><small>Only after independent root-side PEM fingerprint verification.</small></p>
<label>Pi-verified public SPKI SHA-256</label><input id="key-fp">
<label>Activation code</label><input id="enroll-code" type="password" autocomplete="off">
<button id="enroll">Acknowledge verified root enrollment</button></section>
<section><h2>Approve exact root release</h2>
<button id="load-proposal">Load current CC proposal for review</button>
<label>Exact fresh typed pi.release.apply request JSON</label><textarea id="request" spellcheck="false"></textarea>
<p><label><input id="approved" type="checkbox" style="width:auto">
I reviewed this exact source SHA, installed predecessor, expiry and request ID.</label></p>
<button id="approve">Cloudflare-sign and dispatch once</button>
<label>Request ID for receipt</label><input id="rid"><button id="receipt">Check root receipt</button>
<pre id="result"></pre></section>
<script src="/owner.js" defer></script></body></html>`;
const client=`const $=x=>document.getElementById(x);
async function api(path,doc){
 const opt=doc===undefined?{}:{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(doc)};
 const res=await fetch('/api/'+path,{...opt,credentials:'same-origin'}),obj=await res.json();
 if(!res.ok)throw Error(obj.error||'HTTP '+res.status);
 return obj;
}
async function show(fn){try{$('result').textContent=JSON.stringify(await fn(),null,2)}
catch(e){$('result').textContent='Denied: '+e.message}}
async function refresh(){try{$('status').textContent=JSON.stringify(await api('status'),null,2)}
catch(e){$('status').textContent='Denied: '+e.message}}
$('refresh').onclick=refresh;
$('load-proposal').onclick=()=>show(async()=>{
  const proposal=await api('proposal');
  $('request').value=JSON.stringify(proposal.request,null,2);
  $('rid').value=proposal.request.request_id;
  $('approved').checked=false;
  return proposal;
});
$('initialize').onclick=()=>show(async()=>{const code=$('activation').value;$('activation').value='';
return api('initialize',{activation_code:code,confirm_first_issue:true})});
$('enroll').onclick=()=>show(async()=>{const code=$('enroll-code').value;$('enroll-code').value='';
return api('enroll',{activation_code:code,pi_enrolled_public_key_sha256:$('key-fp').value.trim(),confirm_independently_enrolled_on_pi:true})});
$('approve').onclick=()=>show(async()=>{if(!$('approved').checked)throw Error('Exact owner review required');
const request=JSON.parse($('request').value),res=await api('approve-root',{request,approve_exact_release:true});
$('rid').value=request.request_id;$('approved').checked=false;return res});
$('receipt').onclick=()=>show(()=>api('receipt?request_id='+encodeURIComponent($('rid').value.trim())));
refresh();`;
const noStore={headers:{'content-type':'text/html; charset=utf-8','cache-control':'private, no-store',
'x-content-type-options':'nosniff','referrer-policy':'no-referrer',
'content-security-policy':"default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"}};
export default {
  async fetch(request,env,ctx) {
    let identity;
    try { identity=await owner(request,env,ctx); }
    catch { return response({error:'cloudflare_owner_access_denied'},403); }
    const url=new URL(request.url);
    try {
      if (request.method==='GET' && url.pathname==='/') return new Response(page,noStore);
      if (request.method==='GET' && url.pathname==='/owner.js') {
        return new Response(client,{headers:{'content-type':'text/javascript; charset=utf-8','cache-control':'private, no-store','x-content-type-options':'nosniff'}});
      }
      if (request.method==='GET' && url.pathname==='/api/status') return response(await status(env));
      if (request.method==='GET' && url.pathname==='/api/proposal') {
        return response(await readPendingCCRootRelease(env));
      }
      if (request.method==='GET' && url.pathname==='/api/receipt') {
        const id=url.searchParams.get('request_id');
        return response(await readPiRootReleaseReceipt(env,id));
      }
      if (request.method!=='POST') return response({error:'unsupported_owner_route'},404);
      requireBrowser(request);
      const input=await body(request);
      if (url.pathname==='/api/initialize') {
        strict(input,['activation_code','confirm_first_issue']);
        if (!flag(env.PI_OWNER_FIRST_ISSUE_ENABLED)
            || input.confirm_first_issue!==true) throw Error('initial_issuance_not_admitted');
        const result=await doRequest(env,'POST','/initialize',
          {...input,operator:identity});
        return response(result,201);
      }
      if (url.pathname==='/api/enroll') {
        strict(input,['activation_code','pi_enrolled_public_key_sha256','confirm_independently_enrolled_on_pi']);
        if (!flag(env.PI_OWNER_FIRST_ENROLL_ENABLED)
            || !SHA256.test(input.pi_enrolled_public_key_sha256)
            || input.pi_enrolled_public_key_sha256!==env.PI_OWNER_ENROLLED_PUB_SHA256
            || input.confirm_independently_enrolled_on_pi!==true)
          throw Error('independent_root_enrollment_required');
        return response(await doRequest(env,'POST','/enroll',{...input,operator:identity}),201);
      }
      if (url.pathname==='/api/approve-root') {
        strict(input,['request','approve_exact_release']);
        if (!flag(env.PI_OWNER_NORMAL_RELEASE_ENABLED)
            || !flag(env.PI_OWNER_SIGNER_ENABLED)
            || input.approve_exact_release!==true) throw Error('cloudflare_root_signing_not_admitted');
        const approval=unsignedGrant(input.request||{});
        await validatePiCloudRootReleaseApproval(approval,input.request);
        const issued=await doRequest(env,'POST','/sign',{
          kind:'root_release',request:input.request,approval,
          approve_exact_release:true,operator:identity,
        });
        const dispatched=await publishPiRootReleaseGrant(
          env,input.request,issued.signed_grant);
        return response({...dispatched,cloudflare_signature_issued:true,
          root_execution_verified:false},202);
      }
      return response({error:'unsupported_owner_action'},404);
    } catch(error) {
      // Never reflect activation code, GitHub token, signature or key material.
      const safe=String(error?.message||'rejected').slice(0,96);
      if (/token|secret|password|activation_code/i.test(safe))return response({error:'protected_owner_action_denied'},403);
      return response({error:safe},403);
    }
  },
};
