// Exactly one fixed holdout, run as paired baseline + category-level lesson.
// Private Service Binding only. No exported user content, raw replies or tools.
import {MICRO_MODELS} from './micro_worker_fixtures.js';
import {FEEDBACK_SCHEMA,FEEDBACK_HOLDOUTS,feedbackRequest,scoreFeedback} from './micro_feedback_holdouts.js';
const API='https://integrate.api.nvidia.com/v1/chat/completions';
export async function runFeedbackPair({modelIndex,caseIndex,providerFetch,now=()=>Date.now()}){
 if(!Number.isInteger(modelIndex)||modelIndex<0||modelIndex>=MICRO_MODELS.length||
    !Number.isInteger(caseIndex)||caseIndex<0||caseIndex>=FEEDBACK_HOLDOUTS.length||
    typeof providerFetch!=='function')throw Error('invalid_fixed_feedback_selector');
 const caseRow=FEEDBACK_HOLDOUTS[caseIndex];
 const start=now();
 const out={schema:FEEDBACK_SCHEMA,model:MICRO_MODELS[modelIndex],model_index:modelIndex,
   case_index:caseIndex,case_id:caseRow.id,category:caseRow.category,protected:caseRow.protected,
   status:'not_started',provider_calls:0,elapsed_ms:0,baseline:null,lesson:null,
   raw_response_exposed:false,private_input_used:false,commands_executed:false,
   protected_action_authorized:false,production_admitted:false};
 try{
  for(const [index,name] of ['baseline','lesson'].entries()){
   const started=now();
   const row={http_status:null,latency_ms:null,format_valid:false,passed:false,
              observed_action:null,observed_route:null,error:null};
   try{
    out.provider_calls++;
    const request=feedbackRequest(modelIndex,caseIndex,index);
    const response=await providerFetch(API,{method:'POST',redirect:'manual',body:JSON.stringify(request)});
    row.http_status=Number.isInteger(response?.status)&&response.status>=100&&response.status<=599?response.status:null;
    row.latency_ms=Math.max(0,Math.min(120000,now()-started));
    if(row.http_status===200){
      const json=await response.json();
      const observed=scoreFeedback(json?.choices?.[0]?.message,caseIndex);
      row.format_valid=observed.valid;row.passed=observed.passed;
      row.observed_action=observed.observed_action;
      row.observed_route=observed.observed_route;
    }
   }catch(e){
    row.error=e?.name==='AbortError'?'aborted':e?.name==='TimeoutError'?'timeout':'transport_error';
    row.latency_ms=Math.max(0,Math.min(120000,now()-started));
   }
   out[name]=row;
   if(row.http_status===429 || row.http_status===401 || row.http_status===402){out.status=row.http_status===429?'rate_limited':'account_gate';return out;}
   if(row.http_status!==200||row.error){out.status='provider_unavailable_or_partial';return out;}
  }
  out.status='pair_complete';
  out.lesson_delta=(out.lesson.passed?1:0)-(out.baseline.passed?1:0);
  out.protected_regression=caseRow.protected && out.baseline.passed && !out.lesson.passed;
  return out;
 }finally {out.elapsed_ms=Math.max(0,Math.min(240000,now()-start));}
}