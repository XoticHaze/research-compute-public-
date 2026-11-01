// Strict public-runner-facing sanitizer. Never copy raw content/headers/errors.
const MODELS=new Set(["poolside/laguna-xs-2.1","minimaxai/minimax-m3.1-flash"]);
const CATS=new Set(["triage","retry","placement","security","customer","command"]);
const ERRORS=new Set(["timeout","aborted","transport_error"]);
function uint(x,max){return Number.isInteger(x)&&x>=0&&x<=max?x:null;}
export function sanitizeMicroReceipt(v){
 if(!v||v.schema!=="commandcenter.nvidia_micro_worker_synthetic.v1"||
    !MODELS.has(v.model)|| !Number.isInteger(v.model_index)||v.model_index<0||v.model_index>1||
    !Number.isInteger(v.batch)||v.batch<0||v.batch>5||
    !Array.isArray(v.results)||v.results.length>4)return null;
 if(v.model!==(v.model_index===0?"poolside/laguna-xs-2.1":"minimaxai/minimax-m3.1-flash"))return null;
 const rows=v.results.map(x=>{
  if(!x||typeof x.id!=="string"||!/^([TRPSCD])0[1-4]$/.test(x.id)||
     !CATS.has(x.category))return null;
  return {id:x.id,category:x.category,http_status:uint(x.http_status,599),
   latency_ms:uint(x.latency_ms,120000),format_valid:x.format_valid===true,
   passed:x.passed===true,error:ERRORS.has(x.error)?x.error:null};
 });
 if(rows.some(x=>!x)||rows.some(x=>x.http_status!==null&&x.http_status<100))return null;
 const statuses=new Set(["batch_complete","limit_reached","rate_limited","account_gate","model_unavailable_or_transport"]);
 return {schema:v.schema,model:v.model,model_index:v.model_index,batch:v.batch,
  status:statuses.has(v.status)?v.status:"invalid_status",calls:uint(v.calls,4),
  elapsed_ms:uint(v.elapsed_ms,120000),results:rows,
  raw_response_exposed:false,private_input_used:false,credential_exposed:false,command_executed:false};
}
