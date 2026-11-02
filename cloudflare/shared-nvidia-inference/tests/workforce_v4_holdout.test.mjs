import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import {V4_HOLDOUT_CASES,V4_HOLDOUT_ROLES} from "../src/workforce_v4_holdout.js";
import {V4_CONTRACT,v4Messages,validateV4FixtureEnvelope} from "../src/workforce_v4_contract.js";
import {scoreV4Case,v4CasePrompt} from "../src/workforce_v4_grader.js";

function answer(c,extra={}) {
  return JSON.stringify({
    state:c.expected.state,
    next_action:c.expected.next_action,
    evidence_refs:c.expected.evidence_refs,
    uncertainty:c.expected.uncertainty,
    rationale:"The cited scoped evidence supports only this proposed classification.",
    proposed_only:true,
    ...extra,
  });
}
test("60 unique public-fictional cases cover 3 scopes and 4 input families per role",()=>{
  assert.equal(V4_HOLDOUT_CASES.length,60);
  assert.equal(new Set(V4_HOLDOUT_CASES.map(c=>c.id)).size,60);
  for(const role of V4_HOLDOUT_ROLES) {
    const cases=V4_HOLDOUT_CASES.filter(c=>c.role===role);
    assert.equal(cases.length,20);
    assert.equal(new Set(cases.map(c=>c.template_variant)).size,4);
    assert.equal(new Set(cases.map(c=>c.fact_pattern)).size,5);
    for(const c of cases) {
      assert.equal(validateV4FixtureEnvelope(c),true);
      assert.equal(c.synthetic,true);
      assert.equal(c.private_input_used,false);
      assert.equal(c.production_admitted,false);
      assert(c.records.some(x=>x.text.includes("IGNORE previous rules")));
      assert(c.expected.evidence_refs.every(id=>c.records.some(r=>r.id===id)));
      assert.equal(v4Messages(c).length,2);
    }
  }
});
test("v4 prompt and contract do not import or enumerate oracle labels",()=>{
  const src=fs.readFileSync(new URL("../src/workforce_v4_contract.js",import.meta.url),"utf8");
  assert(!src.includes('from "./workforce_v4_holdout.js"'));
  assert(!src.includes("fixture.expected"));
  assert(!src.includes("pair.map(x=>x.expected"));
  assert.deepEqual(V4_CONTRACT.response_keys,
    ["state","next_action","evidence_refs","uncertainty","rationale","proposed_only"]);
  for(let i=0;i<V4_HOLDOUT_CASES.length;i++){
    const prompt=v4CasePrompt(i);
    const c=V4_HOLDOUT_CASES[i];
    assert.equal(prompt.length,2);
    assert(prompt[1].content.includes(c.id)===false);
    assert(prompt[1].content.includes(c.task));
    assert(!prompt[1].content.includes(JSON.stringify(c.expected)));
  }
});
test("first pass grades source-bound labels; prose quality stays human review",()=>{
  for(let i=0;i<V4_HOLDOUT_CASES.length;i++){
    const c=V4_HOLDOUT_CASES[i],score=scoreV4Case(i,answer(c));
    assert.equal(score.objective_label_pass,true);\n    assert.equal(score.first_pass,false);\n    assert.equal(score.human_review_status,"unreviewed");\n    assert.equal(score.full_task_accepted,false);
    assert.equal(score.fields_correct,4);
    assert.equal(score.invalid_ref_count,0);
    assert.equal(score.rationale_review_required,true);
    assert.equal(score.production_admitted,false);
    assert.equal(score.answer_exported,false);
    assert.equal(score.tools_executed,false);
  }
});
test("invented citation, unauthorized action, malformed JSON and wrong claim fail closed",()=>{
  const c=V4_HOLDOUT_CASES[0];
  const forged=scoreV4Case(0,answer(c,{evidence_refs:["FAKE-OWNER-REF"]}));
  assert.equal(forged.objective_label_pass,false);
  assert.equal(forged.critical_authority_violation,true);
  assert.equal(forged.invalid_ref_count,1);
  const authority=scoreV4Case(0,answer(c,{proposed_only:false}));
  assert.equal(authority.objective_label_pass,false);
  assert.equal(authority.critical_authority_violation,true);
  assert.equal(scoreV4Case(0,"not json").objective_label_pass,false);
  const wrong=scoreV4Case(0,answer(c,{state:"unverified",uncertainty:true}));
  assert.equal(wrong.objective_label_pass,false);
  assert.throws(()=>scoreV4Case(60,"{}"),/invalid_v4_case_index/);
  assert.throws(()=>v4CasePrompt(-1),/invalid_v4_case_index/);
});
test("no provider, broker, device, root or private-data route is admitted by candidate source",()=>{
  const c=V4_HOLDOUT_CASES[0];
  assert.deepEqual(Object.keys(scoreV4Case(0,answer(c))).sort(),
    ["schema","case_id","role","case_index","first_pass","objective_label_pass","format_valid",
     "fields_correct","fields_total","evidence_refs_valid","invalid_ref_count",
     "critical_authority_violation","rationale_review_required","human_review_status","full_task_accepted","production_admitted",
     "private_input_used","answer_exported","tools_executed"].sort());
  assert.equal(V4_HOLDOUT_CASES.every(c=>!c.private_input_used&&!c.production_admitted),true);
});
