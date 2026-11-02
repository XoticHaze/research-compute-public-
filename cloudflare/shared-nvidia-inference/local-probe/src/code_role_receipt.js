// Second independent boundary on the loopback Service Binding. The only
// output is explicitly public synthetic Python source for an AST-only scorer.
const MODELS=["poolside/laguna-xs-2.1","minimaxai/minimax-m3.1-flash"];
const TASKS=[
 ["RETRY_DEADLINE_01","retry_delay_ms","attempt, max_attempts, base_ms, cap_ms"],
 ["BOUNDED_CLAMP_02","clamp_window","value, low, high, fallback"],
 ["RESERVED_BUDGET_03","budget_remaining","limit, spent, reserved, floor"],
 ["ALLOCATION_BPS_04","allocation_limit","equity, risk_bps, cap_usd, minimum_usd"],
 ["STALE_HEARTBEAT_05","staleness_status","now_ms, last_ms, warn_ms, expire_ms"],
];
const STATUS=new Set(["candidate_unexecuted","format_rejected","provider_rate_limited",
  "provider_unavailable","provider_transport_or_decode_failure"]);
const SOURCE=/^[A-Za-z0-9_ ()*,+\-<>=:\/\n]+$/;
const FORBIDDEN=/\b(?:import|exec|eval|open|globals|locals|lambda|class|del|while|for|yield|async|await|print|input|NVIDIA|secret|key|token|subprocess)\b/i;
export function sanitizeCodeRoleReceipt(v){
 if(!v||v.schema!=="commandcenter.nvidia_role_code_case.v1"||
    !Number.isInteger(v.model_index)||v.model_index<0||v.model_index>1||
    !Number.isInteger(v.task_index)||v.task_index<0||v.task_index>=TASKS.length||
    v.model!==MODELS[v.model_index]||
    v.task_id!==TASKS[v.task_index][0]||!STATUS.has(v.status)||
    v.provider_calls!==1||!Number.isInteger(v.elapsed_ms)||
    v.elapsed_ms<0||v.elapsed_ms>120000||
    (v.http_status!==null&&(!Number.isInteger(v.http_status)||
      v.http_status<100||v.http_status>599)))return null;
 // Diagnostics from the provider are allowlisted *metadata only*. Never
 // forward reasoning_content, raw final text or arbitrary finish strings.
 // Older deployed fixture revisions may lack these fields; map to null/unknown.
 const finish=v.finish_reason??"not_recorded";
 const allowFinish=new Set(["stop","length","tool_calls","content_filter","other","not_recorded"]);
 const present=v.final_content_present??null;
 const reasoning=v.reasoning_content_present??null;
 if(!allowFinish.has(finish)||
    (present!==null&&typeof present!=="boolean")||
    (reasoning!==null&&typeof reasoning!=="boolean"))return null;
 const src=v.source;
 if(v.status==="candidate_unexecuted"&&(
    v.http_status!==200||v.source_valid_shape!==true||
    typeof src!=="string"||src.length<55||src.length>1801||
    src.split("\n").length>35||
    !src.startsWith("def "+TASKS[v.task_index][1]+"("+TASKS[v.task_index][2]+"):\n")||
    !SOURCE.test(src)||FORBIDDEN.test(src)||src.includes("__")||src.includes("\r")))
  return null;
 return {
   schema:"commandcenter.nvidia_role_code_case.v1",model:MODELS[v.model_index],
   model_index:v.model_index,task_id:TASKS[v.task_index][0],
   task_index:v.task_index,status:v.status,provider_calls:1,
   http_status:v.http_status,elapsed_ms:v.elapsed_ms,
   final_content_present:present,reasoning_content_present:reasoning,
   finish_reason:finish,
   code:v.status==="candidate_unexecuted"?src:null,
   private_data_exposed:false,model_code_executed:false,
   real_repo_changed:false,synthetic_only:true
 };
}
