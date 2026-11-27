// Independently administered neutral-account Cloudflare ONLY Pi root authorization service.
// This script MUST NOT be deployed by GitHub-controlled Worker credentials.
// No private key is accepted from a request, repository, or caller.
import {
  PiOwnerApprovalState,
  canonicalPiJson,
  validatePiCloudRootReleaseApproval,
  validatePiCloudBotRejoinApproval,
  publishPiOwnerGrant,
  readPiOwnerRootReceipt,
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
    bot_rejoin_enabled:flag(env.PI_OWNER_BOT_REJOIN_ENABLED),
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

function unsignedRejoinGrant(request) {
  return {
    schema:'commandcenter.pi.bot_rejoin_approval.v1',
    request_id:request.request_id,
    source_sha:request.source_sha,
    image_ref:request.image_ref,
    client_id:request.client_id,
    inspect_client_id:request.inspect_client_id,
    artifact_manifest_blob_sha:request.artifact_manifest_blob_sha,
    expected_release:request.expected_release,
    expires_at:request.expires_at,
    acknowledge_exact_existing_bot_restart:true,
    gateway_restart_forbidden:true,
    new_live_authority_granted:false,
  };
}
async function readPendingBotRejoin(env) {
  const token=String(env.PI_OWNER_QUEUE_GITHUB_TOKEN||'');
  if(token.length<20) throw Error('pi_owner_queue_credential_missing');
  const remote=await fetch(
    'https://api.github.com/repos/XoticHaze/CommandCenter-gate-control/'
      +'contents/pi-node/bot-rejoin-proposal.json?ref=pi-node-inbox',
    {headers:{authorization:'Bearer '+token,accept:'application/vnd.github+json',
      'x-github-api-version':'2022-11-28'},redirect:'manual'});
  if(!remote.ok) throw Error('pi_owner_pending_rejoin_unavailable');
  const file=await remote.json();
  if(!/^[a-f0-9]{40}$/.test(String(file?.sha||''))
      || file.encoding!=='base64' || !Number.isInteger(file.size)
      || file.size<1 || file.size>4096
      || typeof file.content!=='string') throw Error('pi_owner_pending_rejoin_invalid');
  const raw=atob(file.content.replace(/\s/g,''));
  if(raw.length>4096) throw Error('pi_owner_pending_rejoin_oversize');
  const request=JSON.parse(raw);
  await validatePiCloudBotRejoinApproval(unsignedRejoinGrant(request),request);
  return {schema:'commandcenter.pi.pending_bot_rejoin_review.v1',
    request,review_only:true,cloudflare_signature_issued:false};
}
async function readPendingCCRootRelease(env) {
  // Fixed private Git transport, not arbitrary repository/path/URL input.
  // The owner sees the current pending proposal and must explicitly review it.
  const token=String(env.PI_OWNER_QUEUE_GITHUB_TOKEN||'');
  if(token.length<20) throw Error('pi_owner_queue_credential_missing');
  const url='https://api.github.com/repos/XoticHaze/CommandCenter-gate-control/'
    +'contents/pi-node/root-release-proposal.json?ref=pi-node-inbox';
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
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#101822">
<title>Pi bot recovery</title>
<style>
:root{color-scheme:dark}
*{box-sizing:border-box}
body{font:16px/1.45 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:0 auto;max-width:42rem;padding:clamp(.75rem,3vw,1.25rem);padding-bottom:calc(1.5rem + env(safe-area-inset-bottom));background:#101822;color:#e8f1ff}
header{padding:.25rem .1rem .75rem}
h1{font-size:1.55rem;line-height:1.2;margin:.2rem 0 .55rem}
h2{font-size:1.12rem;margin:0 0 .45rem}
p{margin:.35rem 0 .8rem;color:#c5d2e2}
.eyebrow{font-size:.75rem;letter-spacing:.09em;text-transform:uppercase;color:#9db5d4;font-weight:700}
section{border:1px solid #455872;border-radius:14px;padding:1rem;margin:.85rem 0;background:#142132}
#bot-rejoin{border-color:#6285b4;box-shadow:0 0 0 1px #6285b433}
button{display:block;width:100%;min-height:48px;margin:.55rem 0;padding:.78rem 1rem;border:1px solid #7895b8;border-radius:10px;background:#20344c;color:#fff;font:600 1rem system-ui;cursor:pointer;touch-action:manipulation}
button.primary{background:#245b91;border-color:#5d9bd6}
button:disabled{opacity:.45;cursor:not-allowed}
label{display:block;margin:.75rem 0 .35rem;color:#d7e3f2}
input:not([type=checkbox]),textarea{display:block;width:100%;min-height:46px;padding:.7rem;border:1px solid #647e9f;border-radius:9px;background:#0e1a28;color:#fff;font:inherit}
input[readonly],textarea[readonly]{color:#b9c9dc}
input[type=checkbox]{width:22px;height:22px;flex:0 0 22px;margin:.1rem 0 0;accent-color:#62a5e8}
.checkbox-row{display:flex;align-items:flex-start;gap:.65rem;padding:.6rem 0}
.checkbox-row label{margin:0;line-height:1.4}
textarea{min-height:8rem;font:12px/1.45 ui-monospace,SFMono-Regular,Consolas,monospace;overflow-wrap:anywhere}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:.82rem;color:#d5e2f2;margin:.65rem 0 0}
#rejoin-summary{margin:.8rem 0;padding:.8rem;border-radius:10px;background:#0d1b2a;border:1px solid #405b7c;white-space:pre-wrap;overflow-wrap:anywhere;font-size:.92rem}
#rejoin-result{min-height:1.5rem}
details{margin:.65rem 0;border-top:1px solid #34465d;padding:.55rem 0}
summary{display:flex;align-items:center;min-height:44px;cursor:pointer;font-weight:650;color:#dce9f8}
.advanced{margin:1rem 0;border:1px solid #455872;border-radius:12px;padding:.3rem .9rem .8rem;background:#111d2b}
.advanced>summary{min-height:52px}
.advanced section{background:#101c2a}
small{color:#aebed0}
@media(min-width:640px){body{padding-top:1.5rem}#bot-rejoin{padding:1.25rem}}
</style></head><body>
<header>
<p class="eyebrow">Protected owner control</p>
<h1>Pi bot recovery</h1>
<p>One exact bot-only restart. The existing Gateway stays running. No live-order authority is granted.</p>
</header>
<section id="bot-rejoin">
<h2>Bot-only namespace rejoin</h2>
<p>Load the current request, check its target and expiry, then approve once.</p>
<button id="load-rejoin" class="primary">Load current bot rejoin</button>
<div id="rejoin-summary" hidden></div>
<details id="rejoin-details" hidden><summary>Inspect exact request JSON</summary>
<textarea id="rejoin-request" spellcheck="false" readonly></textarea></details>
<div class="checkbox-row"><input id="rejoin-approved" type="checkbox" disabled>
<label for="rejoin-approved">I approve only this exact existing bot restart. No Gateway restart or trading authority.</label></div>
<button id="approve-rejoin" class="primary" disabled>Sign and dispatch bot restart once</button>
<label for="rejoin-rid">Request ID</label><input id="rejoin-rid" readonly autocomplete="off">
<button id="rejoin-receipt" disabled>Check bot rejoin receipt</button>
<pre id="rejoin-result" role="status" aria-live="polite"></pre>
</section>
<section id="readiness">
<h2>Signer readiness</h2>
<button id="refresh">Refresh signer status</button>
<details><summary>View technical status</summary><pre id="status"></pre></details>
</section>
<details class="advanced"><summary>Advanced owner operations</summary>
<section><h2>Approve exact root release</h2>
<button id="load-proposal">Load non-executing root release proposal</button>
<label for="request">Exact fresh typed pi.release.apply request JSON</label><textarea id="request" spellcheck="false"></textarea>
<div class="checkbox-row"><input id="approved" type="checkbox"><label for="approved">I reviewed this exact source SHA, installed predecessor, expiry and request ID.</label></div>
<button id="approve">Cloudflare-sign and dispatch once</button>
<label for="rid">Request ID for receipt</label><input id="rid"><button id="receipt">Check root receipt</button>
<pre id="result"></pre></section>
<section><h2>One-time owner initialization</h2>
<p><small>Only when independently approved and first issuance is enabled by Cloudflare admin.</small></p>
<label for="activation">Owner activation code (not saved)</label><input id="activation" type="password" autocomplete="off">
<button id="initialize">Issue initial Cloudflare Ed25519 key</button></section>
<section><h2>One-time public-key enrollment acknowledgement</h2>
<p><small>Only after independent root-side PEM fingerprint verification.</small></p>
<label for="key-fp">Pi-verified public SPKI SHA-256</label><input id="key-fp">
<label for="enroll-code">Activation code</label><input id="enroll-code" type="password" autocomplete="off">
<button id="enroll">Acknowledge verified root enrollment</button></section>
</details>
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
$('initialize').onclick=()=>show(async()=>{const code=$('activation').value;$('activation').value='';
return api('initialize',{activation_code:code,confirm_first_issue:true})});
$('enroll').onclick=()=>show(async()=>{const code=$('enroll-code').value;$('enroll-code').value='';
return api('enroll',{activation_code:code,pi_enrolled_public_key_sha256:$('key-fp').value.trim(),confirm_independently_enrolled_on_pi:true})});
$('load-proposal').onclick=()=>show(async()=>{
  const proposal=await api('proposal');
  $('request').value=JSON.stringify(proposal.request,null,2);
  $('rid').value=proposal.request.request_id;
  $('approved').checked=false;
  return proposal;
});
$('approve').onclick=()=>show(async()=>{if(!$('approved').checked)throw Error('Exact owner review required');
const request=JSON.parse($('request').value),res=await api('approve-root',{request,approve_exact_release:true});
$('rid').value=request.request_id;$('approved').checked=false;return res});
$('receipt').onclick=()=>show(()=>api('receipt?request_id='+encodeURIComponent($('rid').value.trim())));

let loadedRejoin=null;
function rejoinControls(ready){
 $('rejoin-approved').disabled=!ready;
 $('approve-rejoin').disabled=!ready;
 $('rejoin-receipt').disabled=!$('rejoin-rid').value.trim();
}
function showRejoinSummary(request){
 const digest=String(request.image_ref||'').split('@sha256:')[1]||'unavailable';
 const expiry=new Date(request.expires_at);
 const expiryText=Number.isNaN(expiry.getTime())?request.expires_at:expiry.toLocaleString();
 $('rejoin-summary').textContent=[
  'Request: '+request.request_id,
  'Node: '+request.node_id+'  |  Existing release: '+request.expected_release,
  'Expires: '+expiryText,
  'Source: '+request.source_sha,
  'Image SHA-256: '+digest,
  'Gateway restart: forbidden',
  'New live-order authority: none'
 ].join('\n');
 $('rejoin-summary').hidden=false;
 $('rejoin-details').hidden=false;
}
$('load-rejoin').onclick=async()=>{
 loadedRejoin=null;rejoinControls(false);$('rejoin-approved').checked=false;
 $('rejoin-result').textContent='Loading current proposal…';
 $('rejoin-summary').hidden=true;$('rejoin-details').hidden=true;
 try{
  const proposal=await api('rejoin-proposal'),request=proposal.request;
  if(proposal.review_only!==true||proposal.cloudflare_signature_issued!==false
     ||request?.action!=='pi.bot.rejoin_existing'||request?.node_id!=='cc-pi4')
    throw Error('Unexpected proposal shape or scope');
  if(!Number.isFinite(Date.parse(request.expires_at))||Date.parse(request.expires_at)<=Date.now())
    throw Error('Proposal expired; request a fresh proposal');
  loadedRejoin=request;
  $('rejoin-request').value=JSON.stringify(request,null,2);
  $('rejoin-rid').value=request.request_id;
  showRejoinSummary(request);rejoinControls(true);
  $('rejoin-result').textContent='Review the exact target above, then confirm to sign once. No signature has been issued yet.';
 }catch(e){$('rejoin-result').textContent='Not loaded: '+e.message;rejoinControls(false)}
};
$('approve-rejoin').onclick=async()=>{
 try{
  if(!loadedRejoin||!$('rejoin-approved').checked)throw Error('Load and explicitly approve the exact request first');
  const request=JSON.parse($('rejoin-request').value);
  if(JSON.stringify(request)!==JSON.stringify(loadedRejoin))throw Error('Request text changed; reload the current proposal');
  if(Date.parse(request.expires_at)<=Date.now())throw Error('Proposal expired; reload a fresh proposal');
  const current=await api('rejoin-proposal');
  if(current.review_only!==true||current.cloudflare_signature_issued!==false
     ||JSON.stringify(current.request)!==JSON.stringify(loadedRejoin))
    throw Error('Current proposal changed; reload before signing');
  const result=await api('approve-rejoin',{request,approve_exact_bot_rejoin:true});
  $('rejoin-rid').value=request.request_id;
  $('rejoin-approved').checked=false;loadedRejoin=null;rejoinControls(false);
  $('rejoin-result').textContent=JSON.stringify(result,null,2);
 }catch(e){$('rejoin-result').textContent='Not signed: '+e.message}
};
$('rejoin-receipt').onclick=async()=>{
 try{
  const id=$('rejoin-rid').value.trim();
  if(!id)throw Error('Load or enter a request ID first');
  $('rejoin-result').textContent=JSON.stringify(
   await api('rejoin-receipt?request_id='+encodeURIComponent(id)),null,2);
 }catch(e){$('rejoin-result').textContent='Receipt unavailable: '+e.message}
};
rejoinControls(false);
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
      if (request.method==='GET' && url.pathname==='/api/proposal')
        return response(await readPendingCCRootRelease(env));
      if (request.method==='GET' && url.pathname==='/api/rejoin-proposal')
        return response(await readPendingBotRejoin(env));
      if (request.method==='GET' && url.pathname==='/api/rejoin-receipt') {
        return response(await readPiOwnerRootReceipt(env,url.searchParams.get('request_id')));
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
      if (url.pathname==='/api/approve-rejoin') {
        strict(input,['request','approve_exact_bot_rejoin']);
        if (!flag(env.PI_OWNER_BOT_REJOIN_ENABLED)
            || !flag(env.PI_OWNER_SIGNER_ENABLED)
            || input.approve_exact_bot_rejoin!==true)
          throw Error('cloudflare_bot_rejoin_not_admitted');
        const approval=unsignedRejoinGrant(input.request||{});
        await validatePiCloudBotRejoinApproval(approval,input.request);
        const issued=await doRequest(env,'POST','/sign',{
          kind:'rejoin',request:input.request,approval,
          approve_exact_release:true,operator:identity,
        });
        const dispatched=await publishPiOwnerGrant(
          env,'rejoin',approval,input.request,issued.signed_grant);
        return response({...dispatched,cloudflare_signature_issued:true,
          root_execution_verified:false},202);
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
