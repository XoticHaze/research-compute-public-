// Private synthetic prose task evaluation. Scores actual fictional drafts
// against static templates without returning model text to public compute.
import {DRAFT_CASES,DRAFT_MODEL,draftRequest,scoreDraft,templateBaseline} from "./draft_pilot_fixtures.js";
const API="https://integrate.api.nvidia.com/v1/chat/completions";
export async function runFixedDraftPilot({providerFetch,now=()=>Date.now()}) {
 if(typeof providerFetch!=="function")throw Error("missing_fixed_draft_provider");
 const started=now();
 const result={schema:"commandcenter.nvidia_fixed_draft_pilot.v1",model:DRAFT_MODEL,
    status:"not_started",attempted:0,results:[],model_text_exposed:false,
    private_input_used:false,commands_executed:false,customer_messages_sent:false,
    template_only_baseline:true};
 for(let i=0;i<DRAFT_CASES.length;i++){
  if(now()-started>115000){result.status="time_limit";return result;}
  const fixture=DRAFT_CASES[i];
  const row={id:fixture.id,kind:fixture.kind,http_status:null,latency_ms:0,
    format_valid:false,anchor_groups:fixture.anchors.length,anchor_groups_met:0,
    unsupported_claim_flag:false,human_review_flag:false,draft_length_ok:false,
    draft_passed:false,template_passed:templateBaseline(fixture).passed,error:null};
  const t0=now();
  try{
   result.attempted++;
   const response=await providerFetch(API,{method:"POST",redirect:"manual",
      body:JSON.stringify(draftRequest(i))});
   row.http_status=Number.isInteger(response?.status)?response.status:null;
   row.latency_ms=Math.min(120000,Math.max(0,now()-t0));
   if(row.http_status===200){
    const payload=await response.json();
    const score=scoreDraft(payload?.choices?.[0]?.message?.content,fixture);
    row.format_valid=score.format_valid;
    row.anchor_groups_met=score.factual_anchor_groups;
    row.unsupported_claim_flag=score.unsupported_claim_flag;
    row.human_review_flag=score.human_review_flag;
    row.draft_length_ok=score.draft_length_ok;
    row.draft_passed=score.passed;
   }
  }catch(e){row.error=e?.name==="AbortError"?"aborted":"transport_error";}
  result.results.push(row);
  if(row.http_status===429){result.status="rate_limited";return result;}
  if(row.http_status!==200||row.error){result.status="provider_or_transport_held";return result;}
 }
 result.status="completed_not_human_reviewed";
 return result;
}
