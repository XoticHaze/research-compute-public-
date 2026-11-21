// One-use loopback public-fictional artifact draft+revision caller.
// Does not expose a public route, accept prompts, or exercise any executor.
import {admitStep, safeSource, SCHEMA, MODEL} from '../../src/evidence_status_loop.js';
const DEST='https://cc-shared-nvidia-inference.invalid/internal/diagnostics/nvidia-evidence-status-step';
const LOCAL='/evidence-status-step';
const reply=(status,doc)=>new Response(JSON.stringify(doc), {status,headers:{'Content-Type':'application/json','Cache-Control':'no-store'}});
export function createEvidenceStatusCaller(){
 let firstSource=null,draftDone=false,revisionDone=false;
 return {async fetch(request,env){
  const u=new URL(request.url);
  if(request.method!=='POST'||u.pathname!==LOCAL||u.search||!['127.0.0.1','localhost','[::1]'].includes(u.hostname))return reply(404,{error:'not_found'});
  const n=Number(request.headers.get('content-length'));
  if(!Number.isInteger(n)||n<1||n>2000||request.headers.get('content-type')!=='application/json')return reply(400,{error:'invalid_selector'});
  let input;try{input=await request.json();}catch{return reply(400,{error:'invalid_selector'});}
  if(!admitStep(input))return reply(400,{error:'invalid_selector'});
  if(input.stage===0&&draftDone)return reply(409,{error:'draft_replay'});
  if(input.stage===1&&(!draftDone||revisionDone||input.source!==firstSource))return reply(409,{error:'revision_unbound_or_replay'});
  if(!env?.NVIDIA_SERVICE?.fetch)return reply(503,{error:'binding_unavailable'});
  if(input.stage===0)draftDone=true;else revisionDone=true;
  let res;
  try{const body=JSON.stringify(input);res=await env.NVIDIA_SERVICE.fetch(new Request(DEST,{method:'POST',headers:{'Content-Type':'application/json','Content-Length':String(new TextEncoder().encode(body).length)},body}));}
  catch{return reply(503,{error:'binding_transport_unavailable'});}
  let doc;try{doc=await res.json();}catch{return reply(503,{error:'invalid_receipt'});}
  if(doc?.error && doc.schema===undefined){const allowed=new Set(['evidence_status_step_selector_rejected','diagnostic_not_admitted','binding_unavailable','secret_unavailable','unavailable']);return reply(503,{error:allowed.has(doc.error)?'upstream_'+doc.error:'upstream_unclassified'});}
  if(!doc||doc.schema!==SCHEMA||doc.stage!==input.stage||doc.model!==MODEL||doc.provider_calls!==1||doc.private_input_used!==false||doc.model_code_executed!==false||doc.commands_executed!==false||doc.production_admitted!==false||!Number.isInteger(doc.elapsed_ms)||doc.elapsed_ms<0||doc.elapsed_ms>120000||!['candidate_unexecuted','format_rejected','rate_limited','provider_unavailable','transport_or_decode_failure'].includes(doc.status))return reply(503,{error:'untrusted_receipt'});
  const source=doc.status==='candidate_unexecuted'?safeSource(doc.source):null;
  if(doc.status==='candidate_unexecuted'&&(!source||doc.http_status!==200||doc.source_valid_shape!==true))return reply(503,{error:'invalid_source_receipt'});
  if(input.stage===0)firstSource=source;
  return reply(source?200:503,{schema:SCHEMA,stage:input.stage,model:MODEL,provider_calls:1,status:doc.status,http_status:doc.http_status,elapsed_ms:doc.elapsed_ms,source,synthetic_only:true,private_input_used:false,model_code_executed:false,commands_executed:false,production_admitted:false});
 }};
}
export default createEvidenceStatusCaller();
