// Isolated local-only caller for a bounded pair of pre-reviewed synthetic cases.
// No production deployment, caller-provided prompts, URLs, model IDs or tools.
import {sanitizeFeedbackReceipt} from './feedback_receipt.js';
const TARGET='https://cc-shared-nvidia-inference.invalid/internal/diagnostics/nvidia-micro-feedback';
const HEADERS={'Content-Type':'application/json','Cache-Control':'no-store'};
const reply=(code,data)=>new Response(JSON.stringify(data),{status:code,headers:HEADERS});
export function createFeedbackCaller(){
 let used=false;
 return {async fetch(request,env){
  const url=new URL(request.url);
  if(request.method!=='POST'||url.pathname!=='/feedback-pair'||url.search||
     !['127.0.0.1','localhost','[::1]'].includes(url.hostname))
    return reply(404,{classification:'local_route_unavailable'});
  const length=Number(request.headers.get('content-length'));
  if(request.headers.get('content-type')!=='application/json'||
     !Number.isInteger(length)||length<1||length>65)
    return reply(400,{classification:'feedback_selector_rejected'});
  let selector;
  try{selector=await request.json();}catch{return reply(400,{classification:'feedback_selector_rejected'});}
  if(!selector||typeof selector!=='object'||Array.isArray(selector)||
     Object.keys(selector).sort().join(',')!=='case_index,model_index'||
     !Number.isInteger(selector.model_index)||selector.model_index<0||selector.model_index>1||
     !Number.isInteger(selector.case_index)||selector.case_index<0||selector.case_index>=12)
    return reply(400,{classification:'feedback_selector_rejected'});
  if(used)return reply(409,{classification:'feedback_session_replay_rejected'});
  if(typeof env?.NVIDIA_SERVICE?.fetch!=='function')
    return reply(503,{classification:'remote_service_binding_missing'});
  used=true;
  try{
   const upstream=await env.NVIDIA_SERVICE.fetch(new Request(TARGET,{method:'POST',
     headers:{'Content-Type':'application/json'},body:JSON.stringify(selector)}));
   const raw=await upstream.json();
   const safe=sanitizeFeedbackReceipt(raw);
   if(!safe||safe.model_index!==selector.model_index||safe.case_index!==selector.case_index)
     return reply(502,{classification:'untrusted_feedback_receipt'});
   return reply(upstream.ok?200:502,safe);
  }catch{return reply(502,{classification:'feedback_service_binding_transport_or_receipt_failure'});}
 }};
}
export default createFeedbackCaller();