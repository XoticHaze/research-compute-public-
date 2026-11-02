// Bounded, synthetic-only provider adapter. This module is deliberately
// network-inert until an authenticated private Service Binding passes fetch.
// No raw response, prompts, reasoning, or credentials leave its receipt.
import {MODELS} from "./code_role_suite.js";
import {TASKS,promptFor,grade} from "./role_discovery_high_signal.js";
const API="https://integrate.api.nvidia.com/v1/chat/completions";
const finishKinds=new Set(["stop","length","tool_calls","content_filter"]);
const count=v=>Number.isSafeInteger(v)&&v>=0&&v<=1000000?v:null;
export async function runDiscoveryCase({modelIndex,taskIndex,providerFetch,now=()=>Date.now()}){
 if(!Number.isInteger(modelIndex)||modelIndex<0||modelIndex>=MODELS.length||
    !Number.isInteger(taskIndex)||taskIndex<0||taskIndex>=TASKS.length||
    typeof providerFetch!=="function")throw Error("invalid_fixed_discovery_selector");
 const task=TASKS[taskIndex],start=now();
 const out={schema:"commandcenter.nvidia_discovery_case.v1",
  model:MODELS[modelIndex],model_index:modelIndex,task_id:task.id,task_index:taskIndex,
  skill:task.skill,status:"not_started",http_status:null,provider_calls:0,
  latency_ms:0,format_valid:false,checks_passed:0,checks_total:0,passed:false,
  human_review_required:task.id==="operator_explanation",
  finish_reason:"not_recorded",prompt_tokens:null,completion_tokens:null,
  reasoning_tokens:null,raw_output_included:false,private_data_used:false,
  production_authorized:false};
 try{
  const request={model:MODELS[modelIndex],messages:promptFor(task.id),
   temperature:1.0,top_p:0.95,max_tokens:8192,stream:false};
  out.provider_calls++;
  const response=await providerFetch(API,{method:"POST",redirect:"manual",body:JSON.stringify(request)});
  out.http_status=Number.isInteger(response?.status)&&response.status>=100&&response.status<=599?response.status:null;
  if(out.http_status===429){out.status="provider_rate_limited";return out;}
  if(out.http_status!==200){out.status="provider_unavailable";return out;}
  const document=await response.json();
  const choice=document?.choices?.[0];
  const message=choice?.message;
  const usage=document?.usage;
  out.finish_reason=finishKinds.has(choice?.finish_reason)?choice.finish_reason:"other";
  out.prompt_tokens=count(usage?.prompt_tokens);
  out.completion_tokens=count(usage?.completion_tokens);
  out.reasoning_tokens=count(usage?.completion_tokens_details?.reasoning_tokens);
  const assessed=grade(task.id,message?.content);
  out.format_valid=assessed.format_valid;
  out.checks_passed=assessed.checks_passed;
  out.checks_total=assessed.checks_total;
  out.passed=assessed.passed;
  out.status=assessed.human_review_required?"human_review_required":
   assessed.passed?"scored_pass":"scored_fail";
 }catch{
  out.status="provider_transport_or_decode_failure";
 }finally{
  out.latency_ms=Math.max(0,Math.min(120000,now()-start));
 }
 return out;
}
