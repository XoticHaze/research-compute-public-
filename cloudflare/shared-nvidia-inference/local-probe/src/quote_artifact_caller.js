// Loopback-only two-step source artifact caller. One draft and one revision.
// Only literal public-fictional source may cross the existing private binding.
import {admitStep, safeSource} from "../../src/quote_artifact_loop.js";
const DEST="https://cc-shared-nvidia-inference.invalid/internal/diagnostics/nvidia-quote-artifact-step";
const LOCAL="/quote-artifact-step";
const HEADERS={"Content-Type":"application/json","Cache-Control":"no-store"};
const reply=(status,value)=>new Response(JSON.stringify(value),{status,headers:HEADERS});
export function createQuoteArtifactCaller(){
 let initial=null,revisionDone=false,draftDone=false;
 return {async fetch(request,env){
   const u=new URL(request.url);
   if(request.method!=="POST"||u.pathname!==LOCAL||u.search||!["127.0.0.1","localhost","[::1]"].includes(u.hostname))
     return reply(404,{error:"not_found"});
   const n=Number(request.headers.get("content-length"));
   if(!Number.isInteger(n)||n<1||n>2000||request.headers.get("content-type")!=="application/json")
     return reply(400,{error:"invalid_selector"});
   let input;try{input=await request.json();}catch{return reply(400,{error:"invalid_selector"});}
   if(!admitStep(input))return reply(400,{error:"invalid_selector"});
   if(input.stage===0&&draftDone)return reply(409,{error:"draft_replay"});
   if(input.stage===1&&(!draftDone||revisionDone||input.source!==initial))
     return reply(409,{error:"revision_unbound_or_replay"});
   if(!env?.NVIDIA_SERVICE?.fetch)return reply(503,{error:"binding_unavailable"});
   if(input.stage===0)draftDone=true;else revisionDone=true;
   let response;
   try{const body=JSON.stringify(input);
     response=await env.NVIDIA_SERVICE.fetch(new Request(DEST,{
       method:"POST",headers:{"Content-Type":"application/json","Content-Length":String(new TextEncoder().encode(body).length)},body}));
   }catch{return reply(503,{error:"binding_transport_unavailable"});}
   let receipt;try{receipt=await response.json();}catch{return reply(503,{error:"invalid_receipt"});}
   if(receipt?.error && receipt.schema===undefined){
     const known=new Set(["quote_step_selector_rejected","diagnostic_not_admitted",
       "binding_unavailable","secret_unavailable","unavailable"]);
     return reply(503,{error:known.has(receipt.error)?"upstream_"+receipt.error:"upstream_unclassified"});
   }
   if(!receipt||receipt.schema!=="commandcenter.public_synthetic_quote_artifact_step.v1"||
     receipt.stage!==input.stage||receipt.model!=="poolside/laguna-xs-2.1"||
     receipt.provider_calls!==1||receipt.private_input_used!==false||
     receipt.model_code_executed!==false||receipt.commands_executed!==false||
     receipt.production_admitted!==false||!Number.isInteger(receipt.elapsed_ms)||
     receipt.elapsed_ms<0||receipt.elapsed_ms>120000||
     !["candidate_unexecuted","format_rejected","rate_limited","provider_unavailable","transport_or_decode_failure"].includes(receipt.status))
     return reply(503,{error:"untrusted_receipt"});
   const candidate=receipt.status==="candidate_unexecuted"?safeSource(receipt.source):null;
   if(receipt.status==="candidate_unexecuted"&&
     (!candidate||receipt.http_status!==200||receipt.source_valid_shape!==true))
     return reply(503,{error:"invalid_source_receipt"});
   if(input.stage===0)initial=candidate;
   const safe={schema:receipt.schema,stage:input.stage,model:receipt.model,
     provider_calls:1,status:receipt.status,http_status:receipt.http_status,
     elapsed_ms:receipt.elapsed_ms,source:candidate,
     synthetic_only:true,private_input_used:false,model_code_executed:false,
     commands_executed:false,production_admitted:false};
   return reply(candidate?200:503,safe);
 }};
}
export default createQuoteArtifactCaller();
