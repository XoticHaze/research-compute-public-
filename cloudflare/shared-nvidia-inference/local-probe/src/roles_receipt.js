// Bound local-only caller: fixed synthetic benchmark sanitization.
// No model-generated response content, credentials, URLs or prompts leave
// the private Service Binding. Model IDs are NVIDIA-published catalog metadata.
const MODEL = /^[A-Za-z0-9_.:-]{2,80}\/[A-Za-z0-9_.:-]{2,120}$/;
const TASK = new Set(["math","logic","json","tool_call"]);
const STATUS = new Set([
 "catalog_only","batch_complete","end_of_catalog","catalog_http_error",
 "catalog_decode_error","transport_error","timeout","aborted",
 "limit_reached","account_auth_rejected","rate_limited"
]);
const ERROR = new Set(["transport_error","timeout","aborted"]);
const int = (n,limit) => Number.isInteger(n)&&n>=0&&n<=limit?n:null;
const flag = n => n === true;
const model = s => typeof s==="string"&&MODEL.test(s)?s:null;
export function sanitizeRolesReceipt(input) {
 if(!input||input.schema!=="commandcenter.nvidia_synthetic_roles.v1"||
    !Number.isInteger(input.batch)||input.batch< -1||input.batch>99) {
   return null;
 }
 const ids=Array.isArray(input.catalog_model_ids)?
   input.catalog_model_ids.slice(0,150).map(model).filter(Boolean):[];
 const eligible=Array.isArray(input.eligible_model_ids)?
   input.eligible_model_ids.slice(0,150).map(model).filter(Boolean):[];
 const results=Array.isArray(input.results)?input.results.slice(0,2).map(item=>({
    model:model(item?.model),
    tests:Array.isArray(item?.results)?item.results.slice(0,4).map(t=>({
      task:TASK.has(t?.task)?t.task:null,
      http_status:int(t?.http_status,599),
      latency_ms:int(t?.latency_ms,120000),
      format_valid:flag(t?.format_valid),
      passed:flag(t?.passed),
      error:ERROR.has(t?.error)?t.error:null,
    })):[]
 })):[];
 if(results.some(x=>!x.model||x.tests.some(y=>!y.task)))return null;
 return {
  schema:"commandcenter.nvidia_synthetic_roles.v1",batch:input.batch,
  status:STATUS.has(input.status)?input.status:"invalid_status",
  catalog_http:int(input.catalog_http,599),
  catalog_count:int(input.catalog_count,10000),
  catalog_model_ids:ids,eligible_count:int(input.eligible_count,10000),
  eligible_model_ids:eligible,results,calls:int(input.calls,9),
  elapsed_ms:int(input.elapsed_ms,120000),
  secret_exposed:false,prompt_exposed:false,response_exposed:false,household_data:false,
 };
}
