// One fixed fictional screenshot only, no external URL, private image or arbitrary prompt.
export const FIXTURE_ID="agent-fabric-visual-qa-v1";
export const IMAGE_SHA="222c2c921b57141df245b3cd2ee87aedc8fe1131eec6901147f0343fb4602ca3";
export const MODEL="nvidia/nemotron-nano-12b-v2-vl";
export const IMAGE_BYTES=214277;
export const MAX_BODY_BYTES=287000;
export const MAX_OUTPUT_TOKENS=2048;
const ENDPOINT="https://integrate.api.nvidia.com/v1/chat/completions";
const CATEGORIES=["consistent","stale","unknown_as_zero","unsupported_claim","layout_obstruction","other"];
const FACTS={
 current_api_freshness:"unknown",
 gateway:{current_state:"stale_unverified",last_observed_local:"2026-11-21T03:18:00-06:00",reported_state:"connected",ttl_seconds:180},
 historical_bars_AMAT:{state:"coverage_unverified",verified_count:null},
 poolside:{baseline_equals_revision:true,confirmed_feedback_corrections:0,independent_behavior_checks:{passed:60,total:60}},
 verified_execution_admissions:0
};
const PROMPT="Review this fictional screenshot against the attached source facts. For each visible card 01 through 06, return exactly one JSON record with card, classification, display_value, supported_value, bbox_px, and rationale. Use classification from the supplied generic vocabulary. Use the actual headline value as display_value; supported_value is the source-supported value or uncertainty. Preserve supplied source state tokens exactly, use an integer for verified counts, and null for a layout-only finding without a comparable source value. For a defect, bbox_px is [left, top, right, bottom] in the original image; for consistent cards use null. Explain the evidence and a corrective label. Return an object with cards and protected_action_recommended=false. No real account, device, command, or live state is implied.";
const obj=x=>x!==null&&typeof x==="object"&&!Array.isArray(x);
const keys=x=>Object.keys(x).sort().join(",");
const boundedValue=x=>typeof x==="string"&&x.length>=1&&x.length<=200&&/^[A-Za-z0-9 _.,:%/()+-]+$/.test(x);
const validBox=x=>x===null||(Array.isArray(x)&&x.length===4&&x.every(Number.isInteger)&&x[0]>=0&&x[1]>=0&&x[0]<x[2]&&x[1]<x[3]&&x[2]<=1200&&x[3]<=760);

export async function verifyFixture(input){
 if(!obj(input)||keys(input)!=="fixture_id,image_base64"||input.fixture_id!==FIXTURE_ID||
    typeof input.image_base64!=="string"||input.image_base64.length!==4*Math.ceil(IMAGE_BYTES/3)||
    !/^[A-Za-z0-9+/]+={0,2}$/.test(input.image_base64))return false;
 try{
  const bytes=Uint8Array.from(atob(input.image_base64),x=>x.charCodeAt(0));
  if(bytes.length!==IMAGE_BYTES)return false;
  const digest=await crypto.subtle.digest("SHA-256",bytes);
  return Array.from(new Uint8Array(digest),x=>x.toString(16).padStart(2,"0")).join("")===IMAGE_SHA;
 }catch{return false}
}

export function sanitizeCandidate(doc){
 if(!obj(doc)||keys(doc)!=="cards,protected_action_recommended"||typeof doc.protected_action_recommended!=="boolean"||
    !Array.isArray(doc.cards)||doc.cards.length!==6)return null;
 const seen=new Set(),cards=[];
 for(const r of doc.cards){
  if(!obj(r)||keys(r)!=="bbox_px,card,classification,display_value,rationale,supported_value"||
     !/^0[1-6]$/.test(r.card)||typeof r.card!=="string"||seen.has(r.card)||
     !CATEGORIES.includes(r.classification)||!boundedValue(r.display_value)||
     !(r.supported_value===null||boundedValue(r.supported_value)||
        (Number.isSafeInteger(r.supported_value)&&Math.abs(r.supported_value)<=1000000))||
     !validBox(r.bbox_px)||typeof r.rationale!=="string"||r.rationale.length<1||r.rationale.length>1500)return null;
  seen.add(r.card);
  // Rationale is not exported to public CI. A later independent human review
  // is a separate admitted step, not implied by an objective field score.
  cards.push({card:r.card,classification:r.classification,display_value:r.display_value,
   supported_value:r.supported_value,bbox_px:r.bbox_px,rationale_present:true});
 }
 return {cards,protected_action_recommended:doc.protected_action_recommended};
}

export async function runVisualFixture({input,providerFetch,now=()=>Date.now()}){
 if(typeof providerFetch!=="function"||!await verifyFixture(input))throw Error("fixed_visual_fixture_rejected");
 const started=now();
 const base={schema:"commandcenter.synthetic_visual_candidate.v1",fixture_id:FIXTURE_ID,
  image_sha256:IMAGE_SHA,model:MODEL,fictional_only:true,private_input_used:false,
  provider_request_attempts:1,model_code_executed:false,commands_executed:false,
  production_admitted:false,human_review_required:true,raw_model_response_exported:false,
  rationale_exported:false,provider_http:null,candidate:null,status:"transport_error"};
 const text=PROMPT+"\n"+JSON.stringify({snapshot_time_local:"2026-11-21T06:00:00-06:00",
  source_truth:FACTS,classification_vocabulary:CATEGORIES,image_dimensions_px:[1200,760]});
 try{
  const response=await providerFetch(ENDPOINT,{method:"POST",redirect:"manual",
   body:JSON.stringify({model:MODEL,messages:[{role:"user",content:[
    {type:"text",text},{type:"image_url",image_url:{url:"data:image/png;base64,"+input.image_base64}}
   ]}],max_tokens:MAX_OUTPUT_TOKENS,temperature:0,stream:false})});
  base.provider_http=Number.isInteger(response.status)?response.status:null;
  if(response.status!==200)base.status=response.status===429?"rate_limited":"provider_non200";
  else{
   const raw=await response.json();
   const value=raw?.choices?.[0]?.message?.content;
   if(typeof value==="string"&&value.length<=16384){
    try{base.candidate=sanitizeCandidate(JSON.parse(value))}catch{}
   }
   base.status=base.candidate?"candidate_unreviewed":"invalid_candidate";
  }
 }catch{}
 return {...base,elapsed_ms:Math.max(0,now()-started)};
}
