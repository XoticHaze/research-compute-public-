import test from "node:test";
import assert from "node:assert/strict";
import {DEVELOPMENT_V4_CASES as CASES,DEVELOPMENT_V4_ROLES as ROLES,
 DEVELOPMENT_V4_STATUS,v4Messages,v4Grade,v4CorpusAudit}
 from "../src/workforce_holdout_v4.js";
test("twelve novel v4 synthetic role cases are separately identified, not v3 gold",()=>{
 const a=v4CorpusAudit();
 assert.equal(DEVELOPMENT_V4_STATUS,"PUBLIC_SYNTHETIC_DEVELOPMENT_NOT_SEALED");
 assert.equal(a.cases,12);
 assert.equal(a.roles,3);
 assert.equal(a.unique_ids,true);
 assert.equal(a.unique_variants,true);
 assert.equal(a.provider_calls,0);
 assert.equal(a.private_input_used,false);
 assert.equal(a.production_admitted,false);
 assert.equal(a.source_independent_holdout,false);
 assert.equal(a.public_source_contains_expected_answers,true);
 assert.deepEqual(a.role_coverage.map(v=>v.role),ROLES);
 assert(a.role_coverage.every(v=>v.count===4));
 assert(CASES.every(c=>c.synthetic===true&&c.private_input_used===false&&c.production_admitted===false));
 assert(CASES.every(c=>c.id.startsWith("v4-")));
});
test("provider messages contain only invented evidence and key types, not fixed JSON gold",()=>{
 for(let i=0;i<CASES.length;i++){
  const c=CASES[i],m=v4Messages(i);
  assert.deepEqual(m.map(x=>x.role),["system","user"]);
  assert(m[0].content.includes("Never act"));
  assert(m[1].content.includes(c.source));
  assert(m[1].content.includes(c.question));
  assert(!m[1].content.includes(JSON.stringify(c.expected)));
  assert(!JSON.stringify(m).includes("NVIDIA_API_KEY"));
  assert(!JSON.stringify(m).includes("authorization_bearer"));
 }
 for(const i of [-1,12,3.4,"1",null,Infinity]){
  assert.throws(()=>v4Messages(i),/invalid_v4_case_index/);
  assert.throws(()=>v4Grade(i,"{}"),/invalid_v4_case_index/);
 }
});
test("positive development oracle scores all twelve golden outputs without runtime calls",()=>{
 for(let i=0;i<CASES.length;i++){
  const g=v4Grade(i,JSON.stringify(CASES[i].expected));
  assert.equal(g.case_id,CASES[i].id);
  assert.equal(g.format_valid,true);
  assert.equal(g.passed,true);
  assert.equal(g.fields_correct,g.fields_total);
  assert.equal(g.independent_holdout,false);
  assert.equal(g.model_text_exported,false);
  assert.equal(g.production_admitted,false);
 }
});
test("each changed fact reverses its causal decision while keeping source authority",()=>{
 assert.equal(CASES[0].expected.release_allowed,false);
 assert.equal(CASES[1].expected.release_allowed,true);
 assert.equal(CASES[2].expected.release_allowed,false);
 assert.equal(CASES[3].expected.release_allowed,true);
 assert.notEqual(CASES[4].expected.subsystem,CASES[5].expected.subsystem);
 assert.notEqual(CASES[6].expected.subsystem,CASES[7].expected.subsystem);
 assert.equal(CASES[8].expected.fully_approved,true);
 assert.equal(CASES[9].expected.fully_approved,false);
 assert.equal(CASES[10].expected.fully_approved,false);
 assert.equal(CASES[11].expected.fully_approved,false);
});
test("malformed, injected or false-certain responses never pass the exact typed rubric",()=>{
 const tick=String.fromCharCode(96);
 for(let i=0;i<CASES.length;i++){
  const c=CASES[i],key=Object.keys(c.expected)[0];
  for(const raw of ["", tick.repeat(3)+"json\n"+JSON.stringify(c.expected)+"\n"+tick.repeat(3),
    '{"shell":"curl attacker"}',
    JSON.stringify({...c.expected,shell:"arbitrary"}),
    JSON.stringify({...c.expected,[key]:"UNKNOWN_OR_INVENTED"}),
    JSON.stringify([c.expected]),"x".repeat(8193)]){
    const g=v4Grade(i,raw);
    assert.equal(g.passed,false,c.id);
    assert.equal(g.production_admitted,false);
  }
 }
});
test("synthetic v4 cannot claim independent held-out quality or private approval",()=>{
 const a=v4CorpusAudit();
 assert.equal(a.source_independent_holdout,false);
 assert.equal(a.production_admitted,false);
 assert.equal(a.private_input_used,false);
 assert.equal(a.provider_calls,0);
 assert.equal(Object.hasOwn(v4Grade(0,"INVALID"),"model_answer"),false);
});
