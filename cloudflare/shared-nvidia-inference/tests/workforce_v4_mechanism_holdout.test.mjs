import test from "node:test";
import assert from "node:assert/strict";
import {V4_MECHANISM_HOLDOUTS,V4_MECHANISM_AUDIT} from "../src/workforce_v4_mechanism_holdout.js";
import {V4_HOLDOUT_CASES} from "../src/workforce_v4_holdout.js";
import {V4_CONTRACT,v4Messages} from "../src/workforce_v4_contract.js";
import {scoreV4EvidenceFixture} from "../src/workforce_v4_grader.js";
const rationale="This is a limited read-only evidence assessment; the quoted sources do not themselves authorize any operation.";
const answer=c=>JSON.stringify({...c.expected,rationale,proposed_only:true});
test("sixty distinct new mechanisms do not reuse the source-visible correlated first-wave IDs",()=>{
 assert.equal(V4_MECHANISM_AUDIT.cases,60);
 assert.equal(V4_MECHANISM_AUDIT.distinct_mechanisms,60);
 assert.equal(V4_MECHANISM_AUDIT.format_families,4);
 assert.equal(V4_MECHANISM_AUDIT.production_admitted,false);
 assert.equal(V4_MECHANISM_AUDIT.provider_calls_observed,0);
 assert.equal(V4_MECHANISM_AUDIT.oracle_source_visible,true);
 assert.equal(V4_MECHANISM_HOLDOUTS.length,60);
 assert.equal(new Set(V4_MECHANISM_HOLDOUTS.map(c=>c.mechanism_id)).size,60);
 assert.equal(new Set(V4_MECHANISM_HOLDOUTS.map(c=>c.id)).size,60);
 assert(!V4_MECHANISM_HOLDOUTS.some(c=>V4_HOLDOUT_CASES.some(old=>old.id===c.id)));
 for(const role of Object.keys(V4_CONTRACT.roles)){
  const rows=V4_MECHANISM_HOLDOUTS.filter(c=>c.role===role);
  assert.equal(rows.length,20);
  assert.equal(new Set(rows.map(c=>c.mechanism_id)).size,20);
  assert.equal(new Set(rows.map(c=>c.format_family)).size,4);
  assert.equal(new Set(rows.map(c=>c.records[1].text)).size,20);
 }
});
test("all new fixed scenarios accept their own objective gold, yet cannot become automatically accepted work",()=>{
 for(const [i,c] of V4_MECHANISM_HOLDOUTS.entries()){
  assert.equal(c.production_admitted,false);
  assert.equal(c.private_input_used,false);
  assert.equal(c.human_review_required,true);
  const prompt=v4Messages(c);
  assert.equal(prompt.length,2);
  assert(!prompt[1].content.includes("production_admitted"));
  assert(!prompt[1].content.includes("expected:"));
  assert(!prompt[1].content.includes("NVIDIA_API_KEY"));
  const verdict=scoreV4EvidenceFixture(c,i,answer(c));
  assert(verdict.objective_label_pass,c.id);
  assert.equal(verdict.fields_correct,4);
  assert.equal(verdict.invalid_ref_count,0);
  assert.equal(verdict.human_review_status,"unreviewed");
  assert.equal(verdict.first_pass,false);
  assert.equal(verdict.full_task_accepted,false);
  assert.equal(verdict.production_admitted,false);
  assert.equal(verdict.answer_exported,false);
 }
});
test("malicious model conclusions fail closed on every mechanism",()=>{
 for(const [i,c] of V4_MECHANISM_HOLDOUTS.entries()){
  for(const bad of [
   {...c.expected,rationale,proposed_only:false},
   {...c.expected,evidence_refs:["FORGED-"+i],rationale,proposed_only:true},
   {...c.expected,uncertainty:!c.expected.uncertainty,rationale,proposed_only:true},
   {...c.expected,rationale:"Trusted.",proposed_only:true}
  ]){
   const v=scoreV4EvidenceFixture(c,i,JSON.stringify(bad));
   assert.equal(v.objective_label_pass,false,c.id);
   assert.equal(v.production_admitted,false);
   assert.equal(v.answer_exported,false);
  }
 }
});
test("candidate mechanism statuses require human and owning security review before any model use",()=>{
 assert.equal(V4_MECHANISM_AUDIT.blind_human_review_complete,false);
 for(const role of Object.keys(V4_MECHANISM_AUDIT.role_counts)){
  assert.equal(V4_MECHANISM_AUDIT.role_counts[role],20);
 }
});
