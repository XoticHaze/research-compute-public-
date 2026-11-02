// Produces one bounded, model-generated fictional source candidate per admitted pair.
import {MODELS,TASKS,requestFor,sanitizeCandidate} from "./code_role_suite.js";
const API="https://integrate.api.nvidia.com/v1/chat/completions";
export async function runCodeRoleCase({modelIndex,taskIndex,providerFetch,now=()=>Date.now()}){
 if(!Number.isInteger(modelIndex)||modelIndex<0||modelIndex>1||
    !Number.isInteger(taskIndex)||taskIndex<0||taskIndex>=TASKS.length||
    typeof providerFetch!=="function")throw Error("invalid_fixed_role_selector");
 const start=now();
 const out={schema:"commandcenter.nvidia_role_code_case.v1",
  model:MODELS[modelIndex],model_index:modelIndex,task_id:TASKS[taskIndex].id,
  task_index:taskIndex,status:"not_started",provider_calls:0,http_status:null,
  elapsed_ms:0,source:null,source_valid_shape:false,
  synthetic_only:true,private_data_used:false,model_code_executed:false,
  real_repo_changed:false};
 try{
  out.provider_calls++;
  const response=await providerFetch(API,{
   method:"POST",redirect:"manual",body:JSON.stringify(requestFor(modelIndex,taskIndex))
  });
  out.http_status=Number.isInteger(response?.status)?response.status:null;
  if(out.http_status===429){out.status="provider_rate_limited";return out;}
  if(out.http_status!==200){out.status="provider_unavailable";return out;}
  const body=await response.json();
  out.source=sanitizeCandidate(body?.choices?.[0]?.message?.content,taskIndex);
  out.source_valid_shape=out.source!==null;
  out.status=out.source_valid_shape?"candidate_unexecuted":"format_rejected";
 }catch{out.status="provider_transport_or_decode_failure";}
 finally{out.elapsed_ms=Math.max(0,Math.min(120000,now()-start));}
 return out;
}
