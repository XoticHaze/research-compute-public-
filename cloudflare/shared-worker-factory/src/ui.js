// Static owner-only review UI. All untrusted proposal text uses textContent.
export const UI = '<!doctype html><html lang="en"><head><meta charset="utf-8">'
  +'<meta name="viewport" content="width=device-width, initial-scale=1">'
  +'<title>CommandCenter Worker Factory</title></head><body>'
  +'<main><h1>CommandCenter shared Worker factory</h1>'
  +'<p>Review this exact inert CommandCenter proposal before approving.</p>'
  +'<pre id="proposal">Loading reviewed proposal...</pre>'
  +'<button id="approve" type="button" disabled>Approve exactly once</button>'
  +'<pre id="result" aria-live="polite"></pre></main>'
  +'<script src="/operator/factory.js" defer></script></body></html>';
export const SCRIPT = String.raw`'use strict';
const show=document.querySelector('#proposal');
const go=document.querySelector('#approve');
const result=document.querySelector('#result');
let proposal=null;
async function load(){
  try {
    const r=await fetch('/v1/proposal',{credentials:'same-origin',cache:'no-store'});
    if(!r.ok) throw Error('No admitted pending proposal available');
    proposal=await r.json();
    show.textContent=JSON.stringify(proposal.request,null,2);
    go.disabled=false;
  } catch(e){show.textContent=String(e.message);go.disabled=true;}
}
go.addEventListener('click',async()=>{
  if(!proposal)return;
  go.disabled=true;
  result.textContent='Submitting exact owner approval...';
  try {
    const r=await fetch('/v1/approve',{
      method:'POST',headers:{'content-type':'application/json'},
      credentials:'same-origin',
      body:JSON.stringify({request_id:proposal.request.request_id,
        expected_blob_sha:proposal.blob_sha})
    });
    result.textContent=JSON.stringify(await r.json(),null,2);
  } catch(e) {result.textContent='Result unknown; inspect private receipt.';}
});
load();`;
