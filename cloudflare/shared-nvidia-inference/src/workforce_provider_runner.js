// Provider-backed cross-project shadow qualification. No model writes or tools.
// The authenticated catalog, not any public user-supplied ID, controls models.
// Only metadata from the model completion is returned outside the private Worker.
import {eligibleChatModel,modelId} from "./benchmark_fixtures.js";
import {CASES,messagesForCase,gradeCase} from "./workforce_domain_suite.js";
const ENDPOINT="https://integrate.api.nvidia.com/v1";
const status=n=>Number.isInteger(n)&&n>=100&&n<=599?n:null;
const count=n=>Number.isSafeInteger(n)&&n>=0&&n<=1000000?n:null;
const finishes=new Set(["stop","length","tool_calls","content_filter"]);
export function eligibleWorkforceCatalog(doc){
 const rows=doc?.data;
 if(!Array.isArray(rows)||rows.length>10000)throw Error("invalid_catalog");
 const list=rows.map(v=>v?.id).filter(v=>modelId(v)&&eligibleChatModel(v));
 return [...new Set(list)].sort();
}
export async function runWorkforceCase({modelIndex,caseIndex,providerFetch,now=()=>Date.now()}){
 if(!Number.isSafeInteger(modelIndex)||modelIndex<0||modelIndex>=10000||
   !Number.isSafeInteger(caseIndex)||caseIndex<0||caseIndex>=CASES.length||
   typeof providerFetch!=="function")throw Error("invalid_fixed_workforce_selector");
 const start=now(),c=CASES[caseIndex];
 const out={schema:"commandcenter.model_workforce_provider_case.v1",
  model_index:modelIndex,model:null,case_id:c.id,case_index:caseIndex,
  role:c.role,domain:c.domain,baseline:c.baseline,priority:c.priority,
  status:"not_started",provider_calls:0,
  catalog_status:null,completion_status:null,catalog_count:null,
  eligible_model_count:null,finish_reason:"not_recorded",
  prompt_tokens:null,completion_tokens:null,reasoning_tokens:null,
  first_pass:false,format_valid:false,fields_correct:0,
  fields_total:Object.keys(c.expected).length,
  human_review_required:c.human_review_required,latency_ms:0,
  answer_exported:false,private_input_used:false,
  production_authorized:false,tool_calls_proposed:false,tools_executed:false};
 try{
  out.provider_calls++;
  const raw=await providerFetch(ENDPOINT+"/models",{method:"GET",redirect:"manual"});
  out.catalog_status=status(raw?.status);
  if(out.catalog_status===429){out.status="provider_rate_limited";return out;}
  if(out.catalog_status!==200){out.status="catalog_unavailable";return out;}
  const catalog=eligibleWorkforceCatalog(await raw.json());
  out.catalog_count=catalog.length;
  out.eligible_model_count=catalog.length;
  if(modelIndex>=catalog.length){out.status="model_index_not_in_authenticated_catalog";return out;}
  const model=catalog[modelIndex];
  out.model=model;
  out.provider_calls++;
  const request={model,messages:messagesForCase(caseIndex),
    temperature:1.0,top_p:0.95,max_tokens:8192,stream:false};
  const response=await providerFetch(ENDPOINT+"/chat/completions",
    {method:"POST",redirect:"manual",body:JSON.stringify(request)});
  out.completion_status=status(response?.status);
  if(out.completion_status===429){out.status="provider_rate_limited";return out;}
  if(out.completion_status!==200){out.status="model_http_unavailable";return out;}
  const result=await response.json();
  const choice=result?.choices?.[0],message=choice?.message;
  out.finish_reason=finishes.has(choice?.finish_reason)?choice.finish_reason:"other";
  out.prompt_tokens=count(result?.usage?.prompt_tokens);
  out.completion_tokens=count(result?.usage?.completion_tokens);
  out.reasoning_tokens=count(result?.usage?.completion_tokens_details?.reasoning_tokens);
  // A model-proposed tool invocation is never executed or silently accepted.
  out.tool_calls_proposed=Array.isArray(message?.tool_calls)&&message.tool_calls.length>0;
  const graded=gradeCase(caseIndex,message?.content);
  out.fields_correct=graded.fields_correct;
  out.fields_total=graded.fields_total;
  out.format_valid=graded.format_valid;
  out.first_pass=graded.passed&&!out.tool_calls_proposed;
  out.status=out.tool_calls_proposed?"tool_attempt_rejected":
    out.human_review_required?"human_review_required":
    graded.passed?"scored_pass":"scored_fail";
 }catch{
  // Never export raw exception details, URLs, model text or provider bodies.
  out.status="transport_or_decoding_failure";
 }finally{out.latency_ms=Math.max(0,Math.min(300000,now()-start));}
 return out;
}
