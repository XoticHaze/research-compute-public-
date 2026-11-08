// Cloudflare Access-locked operator transport UI. The only signing key is
// held on a separately downloaded/offline owner device; this Worker never
// creates, imports, stores, or uses that private key.
const source = 'https://github.com/XoticHaze/research-compute-public-/blob/e2fa785d33c1185289f7e360d7bddb3d3b7d9e5d/cloudflare/operator-console/owner-device-offline-signer.html';
const html = [
  '<!doctype html><html lang="en"><head><meta charset="utf-8">',
  '<meta name="viewport" content="width=device-width,initial-scale=1">',
  '<title>CommandCenter Pi owner authorization</title>',
  '<style>body{font:16px system-ui;background:#111a25;color:#eff5fc;max-width:48rem;margin:auto;padding:1rem}section{background:#203044;padding:1rem;margin:1rem 0;border-radius:12px}label{display:block;margin:.7rem 0 .3rem}textarea,input,select{box-sizing:border-box;width:100%;background:#071320;color:white;padding:.7rem;border:1px solid #92a9c2;border-radius:6px}textarea{min-height:8rem;font-size:.8rem}button{background:#a2ceff;color:#081627;padding:.8rem;margin:.5rem .3rem 0 0;border:0;border-radius:6px;font-weight:700}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#071320;padding:.7rem;border-radius:6px}p{line-height:1.5}small{color:#c8d8ea}input[type=checkbox]{width:auto}a{color:#a2ceff}</style></head><body>',
  '<h1>Pi owner authorization</h1><p>Cloudflare Access identifies the operator. <strong>Signing is performed on your separate owner device</strong>; GitHub transports only a detached approval which cc-pi4 independently verifies. The former GitHub-deployable Cloudflare signer is retired.</p>',
  '<section><h2>Transport readiness</h2><button id="refresh">Refresh</button><pre id="status">Loading</pre><p>The public Ed25519 key must be enrolled exactly once by the independent Pi root owner before a signed release. Neither a public Git commit nor an Access login authorizes this.</p></section>',
  '<section><h2>Owner-device signer</h2><p>Use an immutable, reviewed copy of the <a rel="noopener noreferrer" target="_blank" href="'+source+'">standalone offline signer</a> on your phone. Download it once to the device, keep it offline, verify the encrypted-backup recovery, and never paste its private key or passphrase here.</p><p>After independent root public-key enrollment, paste an exact fresh request and unsigned matching approval below, sign them locally, and return only the signed grant JSON.</p></section>',
  '<section><h2>Dispatch one exact owner-signed grant</h2>',
  '<label for="kind">Operation</label><select id="kind"><option value="replace">pi.bot.replace_existing</option><option value="bootstrap">pi.bot.owner_bootstrap</option><option value="root_release">pi.release.apply (root-agent upgrade)</option></select>',
  '<label for="request">Exact fresh Pi typed request JSON</label><textarea id="request" spellcheck="false"></textarea>',
  '<label for="approval">Matching unsigned owner approval JSON</label><textarea id="approval" spellcheck="false"></textarea>',
  '<label for="grant">Detached grant JSON signed OFFLINE on owner device</label><textarea id="grant" spellcheck="false"></textarea>',
  '<p><input type="checkbox" id="approved"> I independently reviewed the actual request, unchanged LIVE mode, and verified the signature was issued on my owner device</p>',
  '<button id="dispatch">Verify signature and send to Pi</button>',
  '<p><small>Dispatch is not execution. Pi root checks the signature, request identities, expiry and nonreplay. Read the matching root result.</small></p>',
  '<label for="root-id">Exact request ID</label><input id="root-id" spellcheck="false"><button id="check-root">Check Pi root receipt</button><pre id="result">No request dispatched</pre></section>',
  '<script src="/operator/pi-owner-approval.js" defer></script></body></html>'
].join('\n');
export function piOwnerApprovalPage(){
  return new Response(html,{headers:{
    'content-type':'text/html; charset=utf-8','cache-control':'private, no-store',
    'x-content-type-options':'nosniff',
    'content-security-policy':"default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
  }});
}
const client=[
  'const $=id=>document.getElementById(id);',
  'function show(x){$("result").textContent=typeof x==="string"?x:JSON.stringify(x,null,2)}',
  'async function api(path,data){const options=data===undefined?{}:{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify(data)};const r=await fetch("/api/pi-owner/"+path,{...options,credentials:"same-origin"});let j;try{j=await r.json()}catch{throw Error("Non-JSON HTTP "+r.status)}if(!r.ok)throw Error((j.error||"HTTP "+r.status)+(j.reason?": "+j.reason:""));return j}',
  'async function run(fn){try{await fn()}catch(e){show("Rejected: "+e.message)}}',
  'async function refresh(){const s=await api("device-status");$("status").textContent=JSON.stringify(s,null,2)}',
  '$("refresh").onclick=()=>run(refresh);',
  '$("dispatch").onclick=()=>run(async()=>{if(!$("approved").checked)throw Error("Explicit owner approval required");const req=JSON.parse($("request").value);const result=await api("dispatch-signed",{kind:$("kind").value,request:req,approval:JSON.parse($("approval").value),signed_grant:JSON.parse($("grant").value),approve_exact_release:true});show(result);$("root-id").value=req.request_id;$("approved").checked=false});',
  '$("check-root").onclick=()=>run(async()=>{const id=$("root-id").value.trim();if(!id)throw Error("Exact request ID required");show(await api("receipt?kind="+encodeURIComponent($("kind").value)+"&request_id="+encodeURIComponent(id)))});',
  'run(refresh);',
].join('\n');
export function piOwnerApprovalClientJs(){
  return new Response(client,{headers:{
    'content-type':'text/javascript; charset=utf-8','cache-control':'private, no-store',
    'x-content-type-options':'nosniff',
  }});
}
