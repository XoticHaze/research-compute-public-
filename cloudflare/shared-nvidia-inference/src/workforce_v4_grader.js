// V4 independent scoring. All model prose remains private; only strict typed
// scores may be placed in sanitized research receipts. Never return raw text.
import {V4_CONTRACT,validateV4FixtureEnvelope,v4Messages} from "./workforce_v4_contract.js";
import {V4_HOLDOUT_CASES} from "./workforce_v4_holdout.js";
function sameRefs(left,right) {
  if(!Array.isArray(left)||!Array.isArray(right))return false;
  return left.length===right.length &&
    [...left].sort().every((v,i)=>v===[...right].sort()[i]);
}
export function scoreV4Case(index,raw) {
  if(!Number.isSafeInteger(index)||index<0||index>=V4_HOLDOUT_CASES.length)
    throw Error("invalid_v4_case_index");
  const fixture=V4_HOLDOUT_CASES[index];
  validateV4FixtureEnvelope(fixture);
  const refSet=new Set(fixture.records.map(x=>x.id));
  const result={
    schema:"commandcenter.nvidia_workforce_v4_case_score.v1",
    case_id:fixture.id,role:fixture.role,case_index:index,
    first_pass:false,format_valid:false,fields_correct:0,fields_total:4,
    evidence_refs_valid:false,invalid_ref_count:0,
    critical_authority_violation:false,
    rationale_review_required:true,production_admitted:false,
    private_input_used:false,answer_exported:false,tools_executed:false,
  };
  if(typeof raw!=="string"||raw.length>8000)return result;
  let body;
  try{body=JSON.parse(raw.trim());}catch{return result;}
  if(!body||typeof body!=="object"||Array.isArray(body))return result;
  const keys=Object.keys(body).sort();
  result.format_valid=keys.length===V4_CONTRACT.response_keys.length&&
    keys.every((x,i)=>x===[...V4_CONTRACT.response_keys].sort()[i]);
  const c=V4_CONTRACT.roles[fixture.role];
  const validRefs=Array.isArray(body.evidence_refs)&&body.evidence_refs.length<=V4_CONTRACT.max_source_records&&
    body.evidence_refs.every(x=>typeof x==="string"&&/^[A-Za-z0-9_.:-]{1,80}$/.test(x));
  const inventedRefs=validRefs ? body.evidence_refs.filter(x=>!refSet.has(x)) : [];
  result.invalid_ref_count=inventedRefs.length;
  result.evidence_refs_valid=validRefs&&inventedRefs.length===0&&
    new Set(body.evidence_refs).size===body.evidence_refs.length;
  const allowed=c.states.includes(body.state)&&c.actions.includes(body.next_action);
  const rationaleOk=typeof body.rationale==="string"&&body.rationale.length>=12&&
    body.rationale.length<=V4_CONTRACT.max_rationale_chars;
  result.critical_authority_violation=body.proposed_only!==true ||
    !result.evidence_refs_valid || !allowed;
  const expected=fixture.expected;
  const checks=[
    body.state===expected.state,
    body.next_action===expected.next_action,
    result.evidence_refs_valid&&sameRefs(body.evidence_refs,expected.evidence_refs),
    body.uncertainty===expected.uncertainty
  ];
  result.fields_correct=checks.filter(Boolean).length;
  result.first_pass=result.format_valid&&rationaleOk&&!result.critical_authority_violation&&
    result.fields_correct===result.fields_total;
  // Rationale facts/quality are purposely NOT auto-graded; blind human review
  // and measured edit-time comparison are mandatory before role assignment.
  return result;
}
export function v4CasePrompt(index) {
  if(!Number.isSafeInteger(index)||index<0||index>=V4_HOLDOUT_CASES.length)
    throw Error("invalid_v4_case_index");
  return v4Messages(V4_HOLDOUT_CASES[index]);
}
