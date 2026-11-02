// Private-Worker source candidate only: FIXED public-fictional v4 cases.
// Not connected to any public/local route. No provider call unless the owning
// Worker explicitly integrates and admits this module after source review.
// Never exports model prose, reasoning, private inputs, user prompts or tools.
import {discoveryProfile,eligibleWorkforceCatalog} from "./workforce_provider_runner.js";
import {V4_HOLDOUT_CASES} from "./workforce_v4_holdout.js";
import {V4_MECHANISM_HOLDOUTS} from "./workforce_v4_mechanism_holdout.js";
import {v4Messages} from "./workforce_v4_contract.js";
import {v4CasePrompt,scoreV4Case,scoreV4EvidenceFixture} from "./workforce_v4_grader.js";
export const V4_REVIEW_MODEL_ALLOWLIST=Object.freeze(["poolside/laguna-xs-2.1","minimaxai/minimax-m3.1-flash"]);
const ORIGIN="https://integrate.api.nvidia.com/v1";
const finishes=new Set(["stop","length","tool_calls","content_filter"]);
const safeStatus=n=>Number.isInteger(n)&&n>=100&&n<=599?n:null;
const safeTokens=n=>Number.isSafeInteger(n)&&n>=0&&n<=1000000?n:null;
export async function runV4SourceOnlyCase({modelIndex,caseIndex,providerFetch,now=()=>Date.now(),cohort="first_wave"}){
  const fixtures=cohort==="first_wave"?V4_HOLDOUT_CASES:
    cohort==="mechanism_v4"?V4_MECHANISM_HOLDOUTS:null;
  if(!Number.isSafeInteger(modelIndex)||modelIndex<0||modelIndex>=10000||
    !fixtures||!Number.isSafeInteger(caseIndex)||caseIndex<0||caseIndex>=fixtures.length||
    typeof providerFetch!=="function")throw Error("invalid_fixed_v4_selector");
  const started=now(),fixture=fixtures[caseIndex];
  const receipt={
    schema:"commandcenter.nvidia_workforce_v4_provider_case.v1",
    case_id:fixture.id,case_index:caseIndex,role:fixture.role,model_index:modelIndex,
    cohort,mechanism_id:cohort==="mechanism_v4"?fixture.mechanism_id:null,
    model:null,status:"not_started",provider_calls:0,
    catalog_status:null,completion_status:null,finish_reason:"not_recorded",
    prompt_tokens:null,completion_tokens:null,latency_ms:0,
    objective_label_pass:false,first_pass:false,
    human_review_status:"unreviewed",full_task_accepted:false,
    format_valid:false,fields_correct:0,fields_total:4,
    invalid_ref_count:0,critical_authority_violation:false,
    tool_calls_proposed:false,tools_executed:false,
    answer_exported:false,raw_response_exported:false,
    private_input_used:false,production_admitted:false,
  };
  try {
    receipt.provider_calls++;
    const catalogResponse=await providerFetch(ORIGIN+"/models",{method:"GET",redirect:"manual"});
    receipt.catalog_status=safeStatus(catalogResponse?.status);
    if(receipt.catalog_status===429){receipt.status="provider_rate_limited";return receipt;}
    if(receipt.catalog_status!==200){receipt.status="catalog_unavailable";return receipt;}
    const catalog=eligibleWorkforceCatalog(await catalogResponse.json());
    if(modelIndex>=catalog.length){receipt.status="model_index_not_in_authenticated_catalog";return receipt;}
    const model=catalog[modelIndex];
    receipt.model=model;
    if(!V4_REVIEW_MODEL_ALLOWLIST.includes(model)){
      receipt.status="model_not_admitted_for_v4";
      return receipt;
    }
    receipt.provider_calls++;
    const completion=await providerFetch(ORIGIN+"/chat/completions",{
      method:"POST",redirect:"manual",
      body:JSON.stringify({model,messages:cohort==="mechanism_v4"?v4Messages(fixture):v4CasePrompt(caseIndex),
        ...discoveryProfile(model),stream:false})
    });
    receipt.completion_status=safeStatus(completion?.status);
    if(receipt.completion_status===429){receipt.status="provider_rate_limited";return receipt;}
    if(receipt.completion_status!==200){
      receipt.status=receipt.completion_status===400?"request_profile_rejected":
        [403,404,410].includes(receipt.completion_status)?"model_http_unavailable":"provider_upstream_error";
      return receipt;
    }
    const response=await completion.json();
    const choice=response?.choices?.[0],message=choice?.message;
    receipt.finish_reason=finishes.has(choice?.finish_reason)?choice.finish_reason:"other";
    receipt.prompt_tokens=safeTokens(response?.usage?.prompt_tokens);
    receipt.completion_tokens=safeTokens(response?.usage?.completion_tokens);
    receipt.tool_calls_proposed=Array.isArray(message?.tool_calls)&&message.tool_calls.length>0;
    const scored=cohort==="mechanism_v4"?
      scoreV4EvidenceFixture(fixture,caseIndex,message?.content):
      scoreV4Case(caseIndex,message?.content);
    receipt.objective_label_pass=scored.objective_label_pass&&!receipt.tool_calls_proposed;
    receipt.format_valid=scored.format_valid;
    receipt.fields_correct=scored.fields_correct;
    receipt.invalid_ref_count=scored.invalid_ref_count;
    receipt.critical_authority_violation=scored.critical_authority_violation||receipt.tool_calls_proposed;
    receipt.status=receipt.tool_calls_proposed?"tool_attempt_rejected":"human_review_required";
    // No completed v4 output is a model-quality success without blind review.
    // Return only bounded exact metadata, never model answer, citations or text.
  }catch{
    receipt.status="transport_or_decoding_failure";
  }finally{
    receipt.latency_ms=Math.max(0,Math.min(300000,now()-started));
  }
  return receipt;
}
