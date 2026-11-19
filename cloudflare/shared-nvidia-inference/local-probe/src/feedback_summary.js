// Strict read-only campaign consumer for twelve source-owned paired receipts.
// Output is research evidence only; it can never activate agent/model authority.
import {sanitizeFeedbackReceipt} from './feedback_receipt.js';
import {FEEDBACK_HOLDOUTS} from '../../src/micro_feedback_holdouts.js';
const REPORT_SCHEMA='commandcenter.nvidia_feedback_campaign_review.v1';

export function summarizeFeedbackCampaign(receipts){
 if(!Array.isArray(receipts)||receipts.length>FEEDBACK_HOLDOUTS.length)
   throw Error('feedback_campaign_receipts_invalid');
 const rows=[];
 const ids=new Set();let model=null;
 for(const raw of receipts){
   const safe=sanitizeFeedbackReceipt(raw);
   if(!safe||ids.has(safe.case_index))throw Error('feedback_campaign_identity_invalid');
   if(model!==null&&model!==safe.model)throw Error('feedback_campaign_mixed_models');
   ids.add(safe.case_index);model=safe.model;rows.push(safe);
 }
 const completed=rows.filter(x=>x.status==='pair_complete' && x.baseline?.http_status===200 && x.lesson?.http_status===200);
 const baseline=completed.filter(x=>x.baseline.passed).length;
 const lesson=completed.filter(x=>x.lesson.passed).length;
 const regressions=completed.filter(x=>x.baseline.passed&&!x.lesson.passed).length;
 const protectedRows=completed.filter(x=>x.protected);
 const protectedMisses=protectedRows.filter(x=>!x.lesson.passed).length;
 const protectedRegressions=protectedRows.filter(x=>x.protected_regression).length;
 const full=ids.size===FEEDBACK_HOLDOUTS.length&&completed.length===FEEDBACK_HOLDOUTS.length;
 const zeroProtected=full&&protectedMisses===0&&protectedRegressions===0;
 return {schema:REPORT_SCHEMA,model,expected_cases:FEEDBACK_HOLDOUTS.length,
  cases_observed:rows.length,paired_cases_completed:completed.length,
  status:full?'fully_scored':'incomplete_no_inference_claim',
  baseline_passes:baseline,lesson_passes:lesson,lesson_delta:lesson-baseline,
  regressions,protected_cases_scored:protectedRows.length,
  protected_misses:protectedMisses,protected_regressions:protectedRegressions,
  advisory_review_candidate:zeroProtected&&lesson>=baseline&&regressions===0,
  automatic_model_promotion:false,protected_routing_allowed:false,
  commands_executed:false,production_admitted:false,raw_responses_exported:false};
}