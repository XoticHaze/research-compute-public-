// Synthetic source-only readback, never provider prose, private inputs or keys.
// The separate public-compute AST interpreter will perform full semantics.
const MODELS=["poolside/laguna-xs-2.1","minimaxai/minimax-m3.1-flash"];
const STATUS=new Set(["candidate_unexecuted","candidate_format_rejected",
 "rate_limited","provider_unavailable","transport_or_decode_error"]);
export function sanitizeCodeReceipt(value){
 if(!value||value.schema!=="commandcenter.nvidia_fixed_code_repair.v1"||
   value.task_id!=="RETRY_DEADLINE_01"||
   !Number.isInteger(value.model_index)||value.model_index<0||value.model_index>1||
   value.model!==MODELS[value.model_index]||
   !STATUS.has(value.status)||!Number.isInteger(value.provider_calls)||
   value.provider_calls!==1||!Number.isInteger(value.elapsed_ms)||
   value.elapsed_ms<0||value.elapsed_ms>120000||
   value.http_status!==null&&(!Number.isInteger(value.http_status)||value.http_status<100||value.http_status>599))
  return null;
 const code=value.source;
 if(value.status==="candidate_unexecuted" &&
   (value.source_valid_shape!==true||typeof code!=="string"||
    code.length>1051||code.length<75||
    !/^def retry_delay_ms\(attempt, max_attempts, base_ms, cap_ms\):\n/.test(code)||
    /\b(?:import|exec|eval|open|globals|locals|lambda|class|del|while|for|yield|async|await|print|input|NVIDIA|secret|key|token)\b/i.test(code)||
    !/^[A-Za-z0-9_ ()*,+\-<>=:\n]+$/.test(code)||code.includes("__")))
    return null;
 return {
   schema:"commandcenter.nvidia_fixed_code_repair.v1",
   task_id:"RETRY_DEADLINE_01",
   model:MODELS[value.model_index],model_index:value.model_index,
   status:value.status,provider_calls:1,http_status:value.http_status,
   elapsed_ms:value.elapsed_ms,
   code:value.status==="candidate_unexecuted"?code:null,
   synthetic_only:true,private_data_exported:false,
   source_executed:false,real_repo_modified:false,
   key_value_exported:false
 };
}
