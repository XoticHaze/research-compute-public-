// Strict metadata-only transport for model workforce qualifications. Handles
// broad model catalogs without accepting model-supplied arbitrary identifiers,
// secrets, source documents, tool arguments or text. Provenance is bound to
// the owning public workflow separately, never inferred from this receipt.
import {CASES} from "../../src/workforce_domain_suite.js";
import {modelId} from "../../src/benchmark_fixtures.js";
const statuses=new Set(["not_started","provider_rate_limited","catalog_unavailable",
 "model_index_not_in_authenticated_catalog","model_http_unavailable",
 "request_profile_rejected","provider_upstream_error",
 "scored_pass","scored_fail","human_review_required","tool_attempt_rejected",
 "transport_or_decoding_failure"]);
const finish=new Set(["not_recorded","stop","length","tool_calls","content_filter","other"]);
const int=(x,min,max)=>Number.isSafeInteger(x)&&x>=min&&x<=max;
const nullableInt=(x,min,max)=>x===null||int(x,min,max);
const bool=x=>typeof x==="boolean";
export function sanitizeWorkforceReceipt(v){
 if(!v||typeof v!=="object"||Array.isArray(v)||v.schema!=="commandcenter.model_workforce_provider_case.v1"||
   !int(v.case_index,0,CASES.length-1)||!int(v.model_index,0,9999)||
   !statuses.has(v.status)||!int(v.provider_calls,0,2)||
   !nullableInt(v.catalog_status,100,599)||!nullableInt(v.completion_status,100,599)||
   !nullableInt(v.catalog_count,0,10000)||!nullableInt(v.eligible_model_count,0,10000)||
   !int(v.latency_ms,0,300000)||!finish.has(v.finish_reason)||
   !int(v.fields_correct,0,20)||!int(v.fields_total,0,20)||
   v.fields_correct>v.fields_total||
   !bool(v.first_pass)||!bool(v.format_valid)||!bool(v.human_review_required)||
   !bool(v.tool_calls_proposed)||
   v.answer_exported!==false||v.private_input_used!==false||
   v.production_authorized!==false||v.tools_executed!==false)return null;
 const c=CASES[v.case_index];
 if(v.case_id!==c.id||v.role!==c.role||v.domain!==c.domain||
   v.baseline!==c.baseline||v.priority!==c.priority||
   v.human_review_required!==c.human_review_required||
   (v.model!==null&&(!modelId(v.model)||v.model.length>160))||
   (v.status==="scored_pass"&&(!v.first_pass||!v.format_valid||
     v.fields_correct!==v.fields_total||v.completion_status!==200))||
   (v.status==="human_review_required"&&(!c.human_review_required||v.first_pass))||
   (v.status==="scored_fail"&&v.first_pass)||
   (v.status==="tool_attempt_rejected"&&(!v.tool_calls_proposed||v.first_pass))||
   (v.first_pass&&v.tool_calls_proposed)||
   (v.model===null&&v.completion_status!==null))return null;
 const keys=Object.keys(c.expected);
 const fieldChecks=v.field_checks===undefined?null:v.field_checks;
 // Perfect/graded claims require the complete source-owned scorecard.
 // A forged 0/0 pass or a missing per-field proof must never cross the binding.
 if(v.fields_total!==keys.length||
    (["scored_pass","scored_fail","human_review_required"].includes(v.status)&&fieldChecks===null))return null;
 if(fieldChecks!==null&&(!fieldChecks||typeof fieldChecks!=="object"||
    Array.isArray(fieldChecks)||JSON.stringify(Object.keys(fieldChecks).sort())!==
    JSON.stringify([...keys].sort())||
    keys.some(k=>typeof fieldChecks[k]!=="boolean")||
    keys.filter(k=>fieldChecks[k]).length!==v.fields_correct))return null;
 const tokens={};
 for(const field of ["prompt_tokens","completion_tokens","reasoning_tokens"]){
  const n=v[field];
  if(!nullableInt(n,0,1000000))return null;
  tokens[field]=n;
 }
 // Construct from known catalog/project-owned contract fields, never spread
 // an untrusted receipt or copy a model's arbitrary key to the caller.
 return{schema:v.schema,model_index:v.model_index,model:v.model,
  case_id:c.id,case_index:c.index,role:c.role,domain:c.domain,
  baseline:c.baseline,priority:c.priority,status:v.status,
  provider_calls:v.provider_calls,catalog_status:v.catalog_status,
  completion_status:v.completion_status,catalog_count:v.catalog_count,
  eligible_model_count:v.eligible_model_count,
  finish_reason:v.finish_reason,...tokens,
  first_pass:v.first_pass,format_valid:v.format_valid,
  fields_correct:v.fields_correct,fields_total:v.fields_total,
  field_checks:fieldChecks===null?null:Object.fromEntries(keys.map(k=>[k,fieldChecks[k]])),
  human_review_required:v.human_review_required,
  latency_ms:v.latency_ms,
  tool_calls_proposed:v.tool_calls_proposed,tools_executed:false,
  answer_exported:false,private_input_used:false,production_authorized:false};
}
