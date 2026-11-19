// Private-Worker result allowlist for public synthetic feedback qualification.
// Never emit arbitrary model-provided strings, prompt text, credentials or
// raw provider responses. The sanitizer is not an authorization oracle.
import {FEEDBACK_HOLDOUTS,FEEDBACK_SCHEMA} from '../../src/micro_feedback_holdouts.js';
import {MICRO_MODELS} from '../../src/micro_worker_fixtures.js';
const ACTIONS=new Set(['investigate','observe','deduplicate','retry','escalate','hold','complete','route','ignore','extend','reject','draft','redact','call','clarify']);
const ROUTES=new Set(['receipts','none','queue','operator','public_compute','haos','untrusted','source_pr','human_review','read_status']);
const ERRORS=new Set(['timeout','aborted','transport_error']);
const STATES=new Set(['not_started','pair_complete','provider_unavailable_or_partial','rate_limited','account_gate']);
const uint=(x,max)=>Number.isInteger(x)&&x>=0&&x<=max?x:null;
function row(x){
 if(x===null)return null;
 if(!x||typeof x!=='object'||Array.isArray(x))return undefined;
 const code=uint(x.http_status,599);
 if(x.http_status!==null&&(code===null||code<100))return undefined;
 if(x.latency_ms!==null&&uint(x.latency_ms,120000)===null)return undefined;
 return {http_status:code,latency_ms:uint(x.latency_ms,120000),
  format_valid:x.format_valid===true,passed:x.passed===true,
  observed_action:ACTIONS.has(x.observed_action)?x.observed_action:null,
  observed_route:ROUTES.has(x.observed_route)?x.observed_route:null,
  error:ERRORS.has(x.error)?x.error:null};
}
export function sanitizeFeedbackReceipt(v){
 if(!v||typeof v!=='object'||v.schema!==FEEDBACK_SCHEMA||
    !Number.isInteger(v.model_index)||v.model_index<0||v.model_index>=MICRO_MODELS.length||
    v.model!==MICRO_MODELS[v.model_index]||!Number.isInteger(v.case_index)||
    v.case_index<0||v.case_index>=FEEDBACK_HOLDOUTS.length)return null;
 const expected=FEEDBACK_HOLDOUTS[v.case_index];
 if(v.case_id!==expected.id||v.category!==expected.category||
    v.protected!==expected.protected||!STATES.has(v.status)||
    uint(v.provider_calls,2)===null||uint(v.elapsed_ms,240000)===null)return null;
 if(v.raw_response_exposed!==false||v.private_input_used!==false||
    v.commands_executed!==false||v.production_admitted!==false||
    v.protected_action_authorized!==false)return null;
 const baseline=row(v.baseline),lesson=row(v.lesson);
 if(baseline===undefined||lesson===undefined)return null;
 if(v.provider_calls===2&&(baseline===null||lesson===null))return null;
 if(v.status==='pair_complete'&&
    (v.provider_calls!==2||baseline?.http_status!==200||lesson?.http_status!==200))return null;
 const lesson_delta=v.status==='pair_complete'&&[-1,0,1].includes(v.lesson_delta)?v.lesson_delta:null;
 const protected_regression=v.status==='pair_complete'&&v.protected_regression===true;
 return {schema:FEEDBACK_SCHEMA,model:v.model,model_index:v.model_index,
  case_id:v.case_id,case_index:v.case_index,category:v.category,protected:v.protected,
  status:v.status,provider_calls:v.provider_calls,elapsed_ms:v.elapsed_ms,
  baseline,lesson,lesson_delta,protected_regression,
  raw_response_exposed:false,private_input_used:false,
  commands_executed:false,production_admitted:false,
  protected_action_authorized:false};
}