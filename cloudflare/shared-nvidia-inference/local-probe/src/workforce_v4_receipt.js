// Exact fixed-cohort, metadata-only NVIDIA v4 receipt boundary. No prose.
import {V4_MECHANISM_HOLDOUTS} from "../../src/workforce_v4_mechanism_holdout.js";
import {modelId} from "../../src/benchmark_fixtures.js";
const statuses=new Set(["not_started","provider_rate_limited","catalog_unavailable",
 "model_index_not_in_authenticated_catalog","model_not_admitted_for_v4",
 "model_http_unavailable","request_profile_rejected","provider_upstream_error",
 "human_review_required","tool_attempt_rejected","transport_or_decoding_failure"]);
const finishes=new Set(["not_recorded","stop","length","tool_calls","content_filter","other"]);
const int=(x,min,max)=>Number.isSafeInteger(x)&&x>=min&&x<=max;
const nullableInt=(x,min,max)=>x===null||int(x,min,max);
const bool=x=>typeof x==="boolean";
export function sanitizeV4MechanismReceipt(v){
 if(!v||typeof v!=="object"||Array.isArray(v)||
  v.schema!=="commandcenter.nvidia_workforce_v4_provider_case.v1"||
  v.cohort!=="mechanism_v4"||!int(v.case_index,0,V4_MECHANISM_HOLDOUTS.length-1)||
  !int(v.model_index,0,9999)||!statuses.has(v.status)||
  !int(v.provider_calls,0,2)||!int(v.latency_ms,0,300000)||
  !nullableInt(v.catalog_status,100,599)||!nullableInt(v.completion_status,100,599)||
  !nullableInt(v.prompt_tokens,0,1000000)||!nullableInt(v.completion_tokens,0,1000000)||
  !finishes.has(v.finish_reason)||!int(v.fields_correct,0,4)||v.fields_total!==4||
  !int(v.invalid_ref_count,0,96)||!bool(v.objective_label_pass)||
  !bool(v.critical_authority_violation)||!bool(v.format_valid)||
  !bool(v.tool_calls_proposed)||v.tools_executed!==false||
  v.first_pass!==false||v.full_task_accepted!==false||
  v.production_admitted!==false||v.private_input_used!==false||
  v.answer_exported!==false||v.raw_response_exported!==false||
  v.human_review_status!=="unreviewed")return null;
 const c=V4_MECHANISM_HOLDOUTS[v.case_index];
 if(v.case_id!==c.id||v.mechanism_id!==c.mechanism_id||v.role!==c.role||
    (v.model!==null&&(!modelId(v.model)||v.model.length>160))||
    (v.objective_label_pass&&(!v.format_valid||v.fields_correct!==4||
      v.critical_authority_violation||v.invalid_ref_count!==0||
      v.tool_calls_proposed||v.status!=="human_review_required"||
      v.completion_status!==200))||
    (v.status==="tool_attempt_rejected"&&!v.tool_calls_proposed)||
    (v.model===null&&v.completion_status!==null))return null;
 // Never spread provider/model-controlled metadata beyond the allowlisted shape.
 return{schema:v.schema,cohort:"mechanism_v4",case_index:c===undefined?null:v.case_index,
  case_id:c.id,mechanism_id:c.mechanism_id,role:c.role,
  model_index:v.model_index,model:v.model,status:v.status,
  provider_calls:v.provider_calls,catalog_status:v.catalog_status,
  completion_status:v.completion_status,finish_reason:v.finish_reason,
  prompt_tokens:v.prompt_tokens,completion_tokens:v.completion_tokens,
  latency_ms:v.latency_ms,objective_label_pass:v.objective_label_pass,
  fields_correct:v.fields_correct,fields_total:4,format_valid:v.format_valid,
  invalid_ref_count:v.invalid_ref_count,
  critical_authority_violation:v.critical_authority_violation,
  tool_calls_proposed:v.tool_calls_proposed,tools_executed:false,
  human_review_status:"unreviewed",first_pass:false,full_task_accepted:false,
  answer_exported:false,raw_response_exported:false,private_input_used:false,
  production_admitted:false};
}
