// Actual model-generated pure Python code is parsed and scored by a separate
// AST-only interpreter in public synthetic compute. Never eval/exec this code.
import {MODELS,TASK_ID,fixedRepairRequest,sanitizeCodeCandidate} from "./fixed_code_repair_fixture.js";
const ENDPOINT="https://integrate.api.nvidia.com/v1/chat/completions";
export async function runFixedCodeRepair({modelIndex,providerFetch,now=()=>Date.now()}){
 if(!Number.isInteger(modelIndex)||modelIndex<0||modelIndex>1||
    typeof providerFetch!=="function")throw Error("invalid_fixed_code_repair_selector");
 const begin=now();
 const out={schema:"commandcenter.nvidia_fixed_code_repair.v1",
    task_id:TASK_ID,model:MODELS[modelIndex],model_index:modelIndex,
    status:"not_attempted",provider_calls:0,http_status:null,
    elapsed_ms:0,source:null,source_valid_shape:false,
    no_private_input:true,real_project_data:false,
    source_executed:false,real_repo_modified:false};
 try{
  out.provider_calls++;
  const response=await providerFetch(ENDPOINT,{
   method:"POST",redirect:"manual",body:JSON.stringify(fixedRepairRequest(modelIndex))});
  out.http_status=Number.isInteger(response?.status)?response.status:null;
  if(out.http_status===429){out.status="rate_limited";return out;}
  if(out.http_status!==200){out.status="provider_unavailable";return out;}
  const body=await response.json();
  out.source=sanitizeCodeCandidate(body?.choices?.[0]?.message?.content);
  out.source_valid_shape=out.source!==null;
  out.status=out.source_valid_shape?"candidate_unexecuted":"candidate_format_rejected";
 }catch{
  out.status="transport_or_decode_error";
 }finally{out.elapsed_ms=Math.max(0,Math.min(120000,now()-begin));}
 return out;
}
