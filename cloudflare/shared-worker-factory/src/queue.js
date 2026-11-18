// Cloudflare-side reader/writer for ONE fixed private CommandCenter proposal lane.
// Token is an independently scoped Cloudflare Secrets Store binding, never
// provided by the caller, written to public Git, or returned to the browser.
import {validateRequest} from './policy.js';
const ROOT='https://api.github.com/repos/XoticHaze/CommandCenter-gate-control/contents/';
const BRANCH='cloudflare-factory-inbox';
const PROPOSAL='cloudflare-factory/proposal.json';
const OUTBOX='cloudflare-factory/results/';
const SHA40=/^[a-f0-9]{40}$/;
const ID32=/^[a-f0-9]{32}$/;

async function queueToken(env) {
  if (!env.FACTORY_QUEUE_GITHUB_TOKEN ||
      typeof env.FACTORY_QUEUE_GITHUB_TOKEN.get!=='function')
    throw Error('queue_binding_absent');
  const value=await env.FACTORY_QUEUE_GITHUB_TOKEN.get();
  if (typeof value!=='string'||value.length<20) throw Error('queue_unavailable');
  return value;
}
function headers(token) {
  return {authorization:'Bearer '+token,accept:'application/vnd.github+json',
    'x-github-api-version':'2022-11-28','user-agent':'commandcenter-cloudflare-factory-v1'};
}
function b64utf8(value) {
  const bytes=new TextEncoder().encode(value);
  let out='';
  for(const byte of bytes) out+=String.fromCharCode(byte);
  return btoa(out);
}
export async function readProposal(env) {
  const bearer=await queueToken(env);
  const r=await fetch(ROOT+PROPOSAL+'?ref='+BRANCH,{
    headers:headers(bearer),redirect:'manual'});
  if (!r.ok) throw Error('proposal_unavailable');
  const f=await r.json();
  if (!SHA40.test(String(f?.sha||'')) || f?.type!=='file' ||
      f?.path!==PROPOSAL || f?.encoding!=='base64' ||
      !Number.isInteger(f.size) || f.size<1 || f.size>4096 ||
      typeof f.content!=='string') throw Error('proposal_invalid');
  const decoded=atob(f.content.replace(/\s/g,''));
  if(decoded.length>4096)throw Error('proposal_oversized');
  const parsed=JSON.parse(decoded);
  const request=validateRequest(parsed);
  return {request,blob_sha:f.sha};
}
export async function writeReceipt(env,receipt) {
  if(!receipt || !ID32.test(receipt.request_id)) throw Error('receipt_invalid');
  const bearer=await queueToken(env);
  const body=JSON.stringify(receipt);
  if (new TextEncoder().encode(body).length>4096) throw Error('receipt_oversized');
  const dest=OUTBOX+receipt.request_id+'.json';
  // No sha: GitHub rejects attempts to overwrite an existing result.
  const r=await fetch(ROOT+dest,{method:'PUT',headers:{
    ...headers(bearer),'content-type':'application/json'},
    body:JSON.stringify({message:'factory receipt '+receipt.request_id,
      branch:BRANCH,content:b64utf8(body+'\\n')}),redirect:'manual'});
  if(r.status!==201) throw Error('receipt_write_indeterminate');
  const got=await r.json();
  if(!SHA40.test(String(got?.content?.sha||'')) ||
      got?.content?.path!==dest)throw Error('receipt_readback_indeterminate');
  return {path:dest,blob_sha:got.content.sha};
}
