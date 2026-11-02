// Strict metadata-only boundary for five-skill fixed fictional model research.
// Never forward source prompts, model response, reasoning, credentials, or tools.
const MODELS=["poolside/laguna-xs-2.1","minimaxai/minimax-m3.1-flash"];
const TASKS=[
 ["evidence_reconciliation","cross_source_investigation"],
 ["messy_extraction","structured_extraction"],
 ["bounded_plan","tool_use_planning"],
 ["tradeoff_analysis","uncertainty_aware_analysis"],
 ["operator_explanation","contextual_writing"],
 ["evidence_reconciliation_holdout","cross_source_investigation"],
 ["messy_extraction_holdout","structured_extraction"],
 ["bounded_plan_holdout","tool_use_planning"],
 ["tradeoff_analysis_holdout","uncertainty_aware_analysis"],
 ["operator_explanation_holdout","contextual_writing"]
];
const STATUSES=new Set(["scored_pass","scored_fail","human_review_required",
 "provider_rate_limited","provider_unavailable","provider_transport_or_decode_failure"]);
const FINISH=new Set(["stop","length","tool_calls","content_filter","other","not_recorded"]);
const integer=(v,min,max)=>Number.isSafeInteger(v)&&v>=min&&v<=max;
const flag=v=>typeof v==="boolean";
export function sanitizeDiscoveryReceipt(v){
 if(!v||typeof v!=="object"||Array.isArray(v)||
    v.schema!=="commandcenter.nvidia_discovery_case.v1"||
    !integer(v.model_index,0,1)||!integer(v.task_index,0,9)||
    v.model!==MODELS[v.model_index]||
    v.task_id!==TASKS[v.task_index][0]||
    v.skill!==TASKS[v.task_index][1]||
    !STATUSES.has(v.status)||v.provider_calls!==1||
    (v.http_status!==null&&!integer(v.http_status,100,599))||
    !integer(v.latency_ms,0,120000)||
    !flag(v.format_valid)||!flag(v.passed)||
    !flag(v.human_review_required)||
    !integer(v.checks_total,0,7)||!integer(v.checks_passed,0,v.checks_total)||
    !FINISH.has(v.finish_reason)||
    v.raw_output_included!==false||v.private_data_used!==false||
    v.production_authorized!==false)return null;
 const totals={};
 for(const field of ["prompt_tokens","completion_tokens","reasoning_tokens"]){
  const n=v[field];
  if(n!==null&&!integer(n,0,1000000))return null;
  totals[field]=n;
 }
 const isWriting=v.task_index===4||v.task_index===9;
 if(v.human_review_required!==isWriting||
    (isWriting&&v.passed)||
    (v.status==="scored_pass"&&(!v.passed||!v.format_valid||
      v.checks_total<1||v.checks_passed!==v.checks_total))||
    (v.status==="scored_fail"&&v.passed)||
    (v.status==="human_review_required"&&(!isWriting||v.passed))||
    (["provider_rate_limited","provider_unavailable","provider_transport_or_decode_failure"].includes(v.status)&&v.passed))return null;
 return{schema:v.schema,model:v.model,model_index:v.model_index,
   task_id:v.task_id,task_index:v.task_index,skill:v.skill,
   status:v.status,http_status:v.http_status,provider_calls:1,
   latency_ms:v.latency_ms,format_valid:v.format_valid,
   checks_passed:v.checks_passed,checks_total:v.checks_total,passed:v.passed,
   human_review_required:isWriting,finish_reason:v.finish_reason,...totals,
   raw_output_included:false,private_data_used:false,
   production_authorized:false};
}
