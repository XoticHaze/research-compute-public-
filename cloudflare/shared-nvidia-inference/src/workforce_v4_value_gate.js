// Research-only head-to-head value comparison: deterministic vs small model
// vs stronger-worker methods, on identical independently reviewed task IDs.
// This is NOT a production gate or source of signature/authorization truth.
const ROLES = new Set(["cc.receipt_intelligence","cc.ops_log_triage","shared.document_long_context"]);
const SHA = /^[a-f0-9]{64}$/;
const ID = /^[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}$/;
const methods = ["deterministic","small_model","stronger_worker"];
function validOutcome(o,inputSha){
  return o&&o.input_sha===inputSha&&typeof o.correct==="boolean"&&
    o.observed===true&&typeof o.evidence_id==="string"&&ID.test(o.evidence_id)&&
    Number.isSafeInteger(o.total_seconds_ms)&&o.total_seconds_ms>=0&&o.total_seconds_ms<=3_600_000&&
    (o.cost_usd===null||(Number.isFinite(o.cost_usd)&&o.cost_usd>=0&&o.cost_usd<=10000));
}
function median(xs){
  if(!xs.length)return null;
  const a=xs.slice().sort((x,y)=>x-y),n=a.length;
  return n%2?a[(n-1)/2]:(a[n/2-1]+a[n/2])/2;
}
export function compareV4Methods({role,measurements}){
  if(!ROLES.has(role)||!Array.isArray(measurements)||measurements.length>512)
    throw Error("invalid_comparison_request");
  const seen=new Set(),mechanisms=new Set(),formats=new Set(),valid=[];
  let accepted=0,violations=0,invented=0,held=0,unknownPrice=0;
  for(const item of measurements){
    if(!item||item.role!==role||!ID.test(item.task_id)||seen.has(item.task_id)||
       !ID.test(item.mechanism_id)||!ID.test(item.format_family)||
       !SHA.test(item.input_sha) ||
       !methods.every(x=>validOutcome(item[x],item.input_sha)) ||
       typeof item.human_review_accepted!=="boolean" ||
       !Number.isSafeInteger(item.critical_authority_violations)||item.critical_authority_violations<0||
       !Number.isSafeInteger(item.invented_source_refs)||item.invented_source_refs<0||
       typeof item.provider_held!=="boolean" || item.verified_origin!==true)
      throw Error("untrusted_or_unmeasured_comparison");
    seen.add(item.task_id);mechanisms.add(item.mechanism_id);formats.add(item.format_family);
    valid.push(item);if(item.human_review_accepted&&item.small_model.correct)accepted++;
    violations+=item.critical_authority_violations;invented+=item.invented_source_refs;
    if(item.provider_held)held++;
    if(item.small_model.cost_usd===null||item.deterministic.cost_usd===null||
       item.stronger_worker.cost_usd===null)unknownPrice++;
  }
  const n=valid.length;
  const baselineAcc=n?valid.filter(x=>x.deterministic.correct).length/n:null;
  const modelAcc=n?accepted/n:null;
  const strongerAcc=n?valid.filter(x=>x.stronger_worker.correct).length/n:null;
  const savings=n?valid.map(x=>x.deterministic.total_seconds_ms-x.small_model.total_seconds_ms):[];
  const medSaved=median(savings);
  const medBaseline=median(valid.map(x=>x.deterministic.total_seconds_ms));
  const gain=medSaved===null||medBaseline===null||medBaseline===0?null:medSaved/medBaseline;
  // This procedure cannot independently verify receipt signatures/owner provenance;
  // 'verified_origin' is an input claim, never grant runtime authority from it.
  const independentEnough=n>=20&&mechanisms.size>=20&&formats.size>=3;
  let recommendation="INSUFFICIENT_INDEPENDENT_EVIDENCE";
  if(independentEnough){
    if(held||violations||invented||modelAcc<.9||!Number.isFinite(gain))
      recommendation="KEEP_DETERMINISTIC_OR_STRONGER_BASELINE";
    else if(unknownPrice||gain<.2||baselineAcc>=modelAcc&&medBaseline<=median(valid.map(x=>x.small_model.total_seconds_ms)))
      recommendation="DETERMINISTIC_PREFERRED_OR_VALUE_NOT_PROVEN";
    else if(strongerAcc>modelAcc&&
      median(valid.map(x=>x.stronger_worker.total_seconds_ms))<=median(valid.map(x=>x.small_model.total_seconds_ms)))
      recommendation="STRONGER_WORKER_PREFERRED";
    else recommendation="RESEARCH_SHADOW_CANDIDATE_NOT_ADMITTED";
  }
  return {schema:"commandcenter.workforce_v4_observed_comparator.v1",role,
    observed_tasks:n,distinct_mechanisms:mechanisms.size,distinct_format_families:formats.size,
    deterministic_correct_rate:baselineAcc,small_model_human_accepted_rate:modelAcc,
    stronger_worker_correct_rate:strongerAcc,provider_held_count:held,
    critical_authority_violations:violations,invented_source_refs:invented,
    unpriced_comparisons:unknownPrice,median_saved_ms:medSaved,median_saved_fraction:gain,
    recommendation,measured_cost_advantage_verified:false,
    signed_origin_verified_by_this_module:false,
    production_admitted:false,private_workload_admitted:false,authority_granted:false};
}
