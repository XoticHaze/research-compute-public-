// Human-facing phone console: served only after exact Cloudflare Access verification.
const html = [
  '<!doctype html><html lang="en"><head><meta charset="utf-8">',
  '<meta name="viewport" content="width=device-width, initial-scale=1">',
  '<title>CommandCenter Pi owner authorization</title>',
  '<style>body{font:16px system-ui;background:#111a25;color:#eff5fc;max-width:48rem;margin:auto;padding:1rem}section{background:#203044;padding:1rem;margin:1rem 0;border-radius:12px}label{display:block;margin:.7rem 0 .3rem}input,textarea,select{box-sizing:border-box;width:100%;background:#071320;color:white;padding:.7rem;border:1px solid #92a9c2;border-radius:6px}textarea{min-height:10rem;font-size:.8rem}button{background:#a2ceff;color:#081627;padding:.8rem;margin:.5rem .3rem 0 0;border:0;border-radius:6px;font-weight:700}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#071320;padding:.7rem;border-radius:6px}p{line-height:1.5}input[type=checkbox]{width:auto;margin:.7rem}small{color:#c8d8ea}</style></head><body>',
  '<h1>Pi owner authorization</h1><p>Cloudflare Access identifies the operator. The existing Pi root worker independently verifies the signed grant. GitHub is transport only.</p>',
  '<section><h2>Signer status</h2><button id="refresh">Refresh</button><pre id="status">Loading</pre><button id="copy-key">Copy public key PEM</button><button id="copy-fingerprint">Copy key SHA-256</button></section>',
  '<section><h2>One-time activation</h2><p>An independently controlled activation code initializes the dedicated signer. Independently enroll its public key on the Pi using a trusted root-owner route.</p><label for="activation">Activation code</label><input type="password" id="activation" autocomplete="off"><button id="initialize">Create signer once</button>',
  '<label for="fingerprint">Independently observed Pi enrolled public key SHA-256</label><input id="fingerprint" placeholder="64 hex digits" autocomplete="off" spellcheck="false"><p><input type="checkbox" id="enrolled">I independently verified Pi root-key enrollment</p><button id="enroll">Record enrollment</button></section>',
  '<section><h2>Authorize one exact request</h2><p>Owner bootstrap requires independently verified current broker snapshot, no-new-Pi-order epoch, and sole writer lease. This interface cannot manufacture those facts.</p>',
  '<label for="kind">Operation</label><select id="kind"><option value="bootstrap">pi.bot.owner_bootstrap</option><option value="replace">pi.bot.replace_existing</option></select>',
  '<label for="request">Fresh exact Pi typed request JSON</label><textarea id="request" spellcheck="false"></textarea>',
  '<label for="approval">Matching unsigned owner approval JSON</label><textarea id="approval" spellcheck="false"></textarea>',
  '<p><input type="checkbox" id="approved">I reviewed and approve these exact identities and LIVE preservation where applicable</p>',
  '<button id="authorize">Sign and dispatch once</button><p><small>Signed or dispatched does not mean Pi accepted the release. Confirm the same ID in the Pi root outbox.</small></p><label for="root-id">Exact Pi request ID</label><input id="root-id" spellcheck="false"><button id="check-root">Check same-ID Pi root receipt</button><pre id="result">No request submitted</pre></section>',
  '<script src="/operator/pi-owner-approval.js" defer></script></body></html>'
].join('\n');
export function piOwnerApprovalPage() {
  return new Response(html,{headers:{
    'content-type':'text/html; charset=utf-8','cache-control':'private, no-store',
    'x-content-type-options':'nosniff',
    'content-security-policy':"default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
  }});
}
const client = [
  'const $=id=>document.getElementById(id);',
  'let status={};',
  'function show(id,x){$(id).textContent=typeof x==="string"?x:JSON.stringify(x,null,2)}',
  'async function api(path,data){const opt=data===undefined?{}:{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify(data)};const r=await fetch("/api/pi-owner/"+path,{...opt,credentials:"same-origin"});let j;try{j=await r.json()}catch{throw Error("Non-JSON HTTP "+r.status)}if(!r.ok)throw Error((j.error||"HTTP "+r.status)+(j.reason?": "+j.reason:""));return j}',
  'async function run(f){try{await f()}catch(e){show("result","Rejected: "+e.message)}}',
  'async function refresh(){status=await api("status");show("status",{initialized:status.initialized,enrolled:status.enrolled,signing_enabled:status.signing_enabled,github_transport_configured:status.github_transport_configured,public_key_sha256:status.public_key_sha256})}',
  '$("refresh").onclick=()=>run(refresh);',
  '$("copy-key").onclick=()=>run(async()=>{if(!status.public_key_pem)throw Error("Key not issued");await navigator.clipboard.writeText(status.public_key_pem);show("result","Public key copied")});',
  '$("copy-fingerprint").onclick=()=>run(async()=>{if(!status.public_key_sha256)throw Error("Key not issued");await navigator.clipboard.writeText(status.public_key_sha256);show("result","Key SHA-256 copied")});',
  '$("initialize").onclick=()=>run(async()=>{const r=await api("initialize",{activation_code:$("activation").value});show("result",{created:r.one_time_created,public_key_sha256:r.public_key_sha256,pi_root_enrolled:false});await refresh()});',
  '$("enroll").onclick=()=>run(async()=>{if(!$("enrolled").checked)throw Error("Independent enrollment confirmation required");const r=await api("enroll",{activation_code:$("activation").value,pi_enrolled_public_key_sha256:$("fingerprint").value.trim(),confirm_independently_enrolled_on_pi:true});show("result",r);await refresh()});',
  '$("authorize").onclick=()=>run(async()=>{if(!$("approved").checked)throw Error("Explicit release approval required");const req=JSON.parse($("request").value);const r=await api("approve",{kind:$("kind").value,request:req,approval:JSON.parse($("approval").value),approve_exact_release:true});show("result",r);$("root-id").value=req.request_id;$("approved").checked=false});',
  '$("check-root").onclick=()=>run(async()=>{const id=$("root-id").value.trim();if(!id)throw Error("Enter exact Pi request ID");const r=await api("receipt?request_id="+encodeURIComponent(id));show("result",r)});',
  'run(refresh);'
].join('\n');
export function piOwnerApprovalClientJs() {
  return new Response(client,{headers:{
    'content-type':'text/javascript; charset=utf-8','cache-control':'private, no-store',
    'x-content-type-options':'nosniff',
  }});
}
