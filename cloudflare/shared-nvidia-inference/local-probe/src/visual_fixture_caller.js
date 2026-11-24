// One-use loopback transport for one exact fictional PNG and one model attempt.
import {verifyFixture,FIXTURE_ID,IMAGE_SHA,MODEL,MAX_BODY_BYTES} from "../../src/visual_fixture_runner.js";
const DEST="https://cc-shared-nvidia-inference.invalid/internal/diagnostics/nvidia-visual-fixture";
const reply=(status,doc)=>new Response(JSON.stringify(doc),{status,headers:{"Content-Type":"application/json","Cache-Control":"no-store"}});
export function createVisualFixtureCaller(){
 let attempted=false;
 return {async fetch(request,env){
  const url=new URL(request.url);
  if(request.method!=="POST"||url.pathname!=="/visual-fixture"||url.search||
    !["127.0.0.1","localhost","[::1]"].includes(url.hostname))return reply(404,{error:"not_found"});
  const n=Number(request.headers.get("content-length"));
  if(!Number.isInteger(n)||n<1||n>MAX_BODY_BYTES||request.headers.get("content-type")!=="application/json")return reply(400,{error:"invalid_fixture"});
  let input;
  try{const raw=await request.text();if(raw.length!==n)throw Error();input=JSON.parse(raw)}catch{return reply(400,{error:"invalid_fixture"})}
  if(!await verifyFixture(input))return reply(400,{error:"invalid_fixture"});
  if(attempted)return reply(409,{error:"attempt_already_reserved"});
  if(!env?.NVIDIA_SERVICE?.fetch)return reply(503,{error:"binding_unavailable"});
  attempted=true;
  const body=JSON.stringify(input);
  let doc;
  try{
   const res=await env.NVIDIA_SERVICE.fetch(new Request(DEST,{method:"POST",headers:{"Content-Type":"application/json","Content-Length":String(body.length)},body}));
   doc=await res.json();
  }catch{return reply(503,{error:"binding_transport_or_receipt_unavailable",request_attempt_upper_bound:1})}
  if(doc?.schema!=="commandcenter.synthetic_visual_candidate.v1"||doc.fixture_id!==FIXTURE_ID||doc.image_sha256!==IMAGE_SHA||doc.model!==MODEL||
   doc.provider_request_attempts!==1||doc.fictional_only!==true||doc.private_input_used!==false||doc.model_code_executed!==false||
   doc.commands_executed!==false||doc.production_admitted!==false||doc.human_review_required!==true||
   doc.raw_model_response_exported!==false||doc.rationale_exported!==false||
   !["candidate_unreviewed","transport_error","rate_limited","provider_non200","invalid_candidate"].includes(doc.status)||
   !Number.isInteger(doc.elapsed_ms)||doc.elapsed_ms<0||doc.elapsed_ms>120000)
   return reply(503,{error:"untrusted_receipt",request_attempt_upper_bound:1});
  if(doc.status==="candidate_unreviewed"){
   const candidate=doc.candidate;
   if(doc.provider_http!==200||!candidate||!Array.isArray(candidate.cards)||candidate.cards.length!==6)
    return reply(503,{error:"invalid_candidate",request_attempt_upper_bound:1});
   // Reconstruct only validated fields, never pass through a raw provider body.
   const cards=candidate.cards.map(r=>({card:r?.card,classification:r?.classification,display_value:r?.display_value,supported_value:r?.supported_value,bbox_px:r?.bbox_px,rationale_present:r?.rationale_present}));
   const allowed=(v)=>typeof v==="string"&&v.length>=1&&v.length<=200&&/^[A-Za-z0-9 _.,:%/()+-]+$/.test(v);
   if(new Set(cards.map(r=>r.card)).size!==6||cards.some(r=>typeof r.card!=="string"||!/^0[1-6]$/.test(r.card)||
    !["consistent","stale","unknown_as_zero","unsupported_claim","layout_obstruction","other"].includes(r.classification)||
    !allowed(r.display_value)||!(r.supported_value===null||allowed(r.supported_value)||(Number.isSafeInteger(r.supported_value)&&Math.abs(r.supported_value)<=1000000))||
    !(r.bbox_px===null||(Array.isArray(r.bbox_px)&&r.bbox_px.length===4&&r.bbox_px.every(Number.isInteger)&&r.bbox_px[0]>=0&&r.bbox_px[1]>=0&&r.bbox_px[0]<r.bbox_px[2]&&r.bbox_px[1]<r.bbox_px[3]&&r.bbox_px[2]<=1200&&r.bbox_px[3]<=760))||
    r.rationale_present!==true)||typeof candidate.protected_action_recommended!=="boolean")
    return reply(503,{error:"invalid_candidate",request_attempt_upper_bound:1});
   return reply(200,{schema:doc.schema,fixture_id:FIXTURE_ID,image_sha256:IMAGE_SHA,model:MODEL,provider_http:200,status:doc.status,
    elapsed_ms:doc.elapsed_ms,request_attempt_upper_bound:1,candidate:{cards,protected_action_recommended:candidate.protected_action_recommended},
    fictional_only:true,private_input_used:false,model_code_executed:false,commands_executed:false,production_admitted:false,
    human_review_required:true,raw_model_response_exported:false,rationale_exported:false});
  }
  return reply(503,{schema:doc.schema,fixture_id:FIXTURE_ID,image_sha256:IMAGE_SHA,model:MODEL,status:doc.status,request_attempt_upper_bound:1,
   provider_http:Number.isInteger(doc.provider_http)&&doc.provider_http>=100&&doc.provider_http<=599?doc.provider_http:null,
   elapsed_ms:doc.elapsed_ms,candidate:null,fictional_only:true,private_input_used:false,production_admitted:false});
 }};
}
export default createVisualFixtureCaller();
