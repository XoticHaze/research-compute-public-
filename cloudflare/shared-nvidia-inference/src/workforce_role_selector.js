// Evidence-driven workforce placement analyzer. No inference, commands, or
// deployment. It consumes accepted sanitized private provider receipts and
// separately measured human/deterministic baselines. Unknown cost/time is
// UNKNOWN, never zero. Two cases are discovery, not production qualification.
import {CASES,WORKFORCE_SKILLS} from "./workforce_domain_suite.js";
const statuses=new Set(["scored_pass","scored_fail","human_review_required",
 "provider_rate_limited","catalog_unavailable","model_http_unavailable",
 "model_index_not_in_authenticated_catalog","request_profile_rejected",
 "provider_upstream_error","tool_attempt_rejected",
 "transport_or_decoding_failure"]);
function percentile(values,q){
 if(!values.length)return null;
 const a=values.slice().sort((x,y)=>x-y);
 const at=(a.length-1)*q,lo=Math.floor(at),hi=Math.ceil(at);
 return Math.round(a[lo]+(a[hi]-a[lo])*(at-lo));
}
function validReceipt(v){
 return v&&v.schema==="commandcenter.model_workforce_provider_case.v1"&&
  Number.isSafeInteger(v.case_index)&&v.case_index>=0&&v.case_index<CASES.length&&
  v.case_id===CASES[v.case_index].id&&v.role===CASES[v.case_index].role&&
  v.domain===CASES[v.case_index].domain&&
  typeof v.model==="string"&&/^[A-Za-z0-9_.:-]+\/[A-Za-z0-9_.:-]+$/.test(v.model)&&
  statuses.has(v.status)&&typeof v.first_pass==="boolean"&&
  Number.isSafeInteger(v.latency_ms)&&v.latency_ms>=0&&v.latency_ms<=300000&&
  v.answer_exported===false&&v.private_input_used===false&&
  v.production_authorized===false&&v.tools_executed===false;
}
const validMeasure=(v)=>v&&Number.isFinite(v.baseline_seconds)&&v.baseline_seconds>=0&&
 Number.isFinite(v.review_seconds)&&v.review_seconds>=0&&
 Number.isFinite(v.rework_seconds)&&v.rework_seconds>=0&&
 (v.provider_cost_usd===null||(Number.isFinite(v.provider_cost_usd)&&v.provider_cost_usd>=0))&&
 v.method==="observed_comparison"&&typeof v.evidence_id==="string"&&
 /^[A-Za-z0-9_.:-]{8,120}$/.test(v.evidence_id);
export function evaluateWorkforceReadiness({receipts,measurements={}}){
 if(!Array.isArray(receipts)||!measurements||typeof measurements!=="object"||Array.isArray(measurements))
  throw Error("invalid_workforce_evidence");
 for(const r of receipts)if(!validReceipt(r))throw Error("untrusted_provider_receipt");
 const keyOf=r=>r.model+"|"+r.role;
 const groups=new Map();
 for(const r of receipts){
  const key=keyOf(r);
  if(!groups.has(key))groups.set(key,[]);
  if(groups.get(key).some(x=>x.case_id===r.case_id))
   throw Error("duplicated_case_not_independent_evidence");
  groups.get(key).push(r);
 }
 const rows=[];
 for(const [key,items] of groups){
  const model=items[0].model,role=items[0].role;
  const successes=items.filter(v=>v.first_pass&&v.status==="scored_pass");
  const unavailable=items.filter(v=>!["scored_pass","scored_fail","human_review_required"].includes(v.status));
  const evaluated=items.filter(v=>["scored_pass","scored_fail"].includes(v.status));
  const human=items.filter(v=>v.status==="human_review_required");
  const caseIds=items.map(r=>r.case_id);
  const caseExpected=CASES.filter(c=>c.role===role).map(c=>c.id);
  const coverage_complete=caseExpected.every(id=>caseIds.includes(id));
  const latency=items.filter(v=>v.completion_status===200).map(v=>v.latency_ms);
  const costKnown=items.every(v=>v.completion_tokens!==null&&v.prompt_tokens!==null);
  const measurement=measurements[key]??null;
  if(measurement!==null&&!validMeasure(measurement))throw Error("invalid_or_unmeasured_baseline");
  const measuredMedian=percentile(latency,.5);
  const netSaved=measurement===null||measuredMedian===null?null:
   measurement.baseline_seconds-measuredMedian/1000-
    measurement.review_seconds-measurement.rework_seconds;
  const effect=(netSaved===null?"UNMEASURED":
    netSaved>0?"POSITIVE_TIME_SAVED":"NO_TIME_SAVINGS");
  const anyCriticalSafety=items.some(v=>v.status==="tool_attempt_rejected");
  // This stage never promotes a provider: exact role SLAs, multiple independent
  // trials, real document reviews, provider price and consumer acceptance are
  // separate observed gates. Avoid treating 2/2 as general intelligence.
  const recommendation=anyCriticalSafety?"reject_protected_tool_work":
    unavailable.length?"investigate_provider_reliability":
    human.length?"needs_blind_human_review":
    !coverage_complete?"insufficient_domain_coverage":
    successes.length!==evaluated.length?"bounded_helper_with_verifier":
    measurement===null?"compare_against_baseline":
    effect==="NO_TIME_SAVINGS"?"deterministic_or_fleet_preferred":
    "promising_shadow_candidate";
  rows.push({model,role,covered:items.length,
   expected_cases:caseExpected.length,coverage_complete,
   first_pass_successes:successes.length,objectively_graded:evaluated.length,
   first_pass_rate:evaluated.length?successes.length/evaluated.length:null,
   unavailable_attempts:unavailable.length,human_review_pending:human.length,
   tool_attempt_rejected:anyCriticalSafety,
   p50_latency_ms:percentile(latency,.5),p95_latency_ms:percentile(latency,.95),
   prompt_and_completion_counts_available:costKnown,
   provider_cost_usd:measurement?.provider_cost_usd??null,
   seconds_saved_per_case:netSaved,measured_value:effect,
   economic_value_net_of_provider_cost:measurement?.provider_cost_usd===null||
      measurement===null?"UNKNOWN":
      "PROVIDER_COST_MEASURED_REQUIRES_CONSUMER_CONVERSION",
   recommendation,production_admitted:false,
   required_next_evidence:measurement===null?"measured_baseline_and_review_effort":
     human.length?"blind_human_quality_review":
     unavailable.length?"provider_admission_retry_with_provenance":
     "repeat_holdouts_and_consumer_specific_acceptance"});
 }
 return{schema:"commandcenter.workforce_role_readiness.v1",
  source:"sanitized_provider_observations",
  expected_skills:WORKFORCE_SKILLS.length,expected_cases:CASES.length,
  observed_cases:receipts.length,rows:rows.sort((a,b)=>a.role.localeCompare(b.role)||a.model.localeCompare(b.model)),
  any_production_admission:false,provider_prices_inferred:false};
}
