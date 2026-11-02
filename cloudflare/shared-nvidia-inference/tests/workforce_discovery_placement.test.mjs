import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import {CASES,WORKFORCE_SKILLS,WORKFORCE_DOMAINS} from "../src/workforce_domain_suite.js";
const x=JSON.parse(fs.readFileSync(new URL("../docs/WORKFORCE_ROLE_DISCOVERY_V3_20261102.json",import.meta.url),"utf8"));
test("32 source-locked cases across 16 domains with no false production permission",()=>{
 assert.equal(x.schema,"commandcenter.nvidia_workforce_role_discovery.v3");
 assert.equal(x.evaluated_source_sha,"d18a85c78e3db84ffde6d51cb3d785971e6f0a38");
 for(const field of ["production_admitted","private_workload_admitted","economic_value_verified","stronger_fleet_replacement_proven","provider_cost_verified"])assert.equal(x[field],false);
 assert.equal(x.active_model_assignments,0);
 assert.deepEqual([x.total_cases,x.objective_cases,x.scored_passes,x.scored_failures,x.writing_cases_pending_human_review],[32,30,20,10,2]);
 assert.equal(x.roles.length,16);
 assert.deepEqual(new Set(x.roles.map(r=>r.role_id)),new Set(WORKFORCE_SKILLS.filter(r=>!r.endsWith('_v4'))));
 assert.deepEqual(new Set(x.roles.map(r=>r.domain)),new Set(WORKFORCE_DOMAINS.filter(d=>!d.endsWith('_v4'))));
 const seen=new Set();let pass=0,fail=0,human=0,candidates=0;
 for(const r of x.roles){
  assert.equal(r.production_admitted,false);
  assert.equal(r.first_pass_status,"DISCOVERY_ONLY_NOT_PRODUCTION_QUALIFIED");
  assert.equal(r.tested_cases,2);
  assert.equal(r.case_indices.length,2);
  for(const i of r.case_indices){assert.equal(CASES[i].role,r.role_id);assert.equal(CASES[i].domain,r.domain);assert(!seen.has(i));seen.add(i);}
  assert.equal(r.passed+r.failed+r.human_review_pending,2);
  if(r.candidate_status==="candidate_read_only"){assert.equal(r.proposed_capability,"read_only_proposal");assert.equal(r.passed,2);candidates++;}else assert.equal(r.proposed_capability,"none");
  pass+=r.passed;fail+=r.failed;human+=r.human_review_pending;
 }
 assert.equal(seen.size,32);
 assert.deepEqual([pass,fail,human,candidates],[20,10,2,8]);
});
test("every documented execution has concrete source-pinned job and digest provenance",()=>{
 const runs=new Map(x.runs.map(r=>[r.run_id,r]));
 assert.equal(runs.size,5);
 assert.equal(x.runs.reduce((a,r)=>a+r.cases,0),32);
 for(const r of x.runs){assert.equal(r.source_sha,x.evaluated_source_sha);assert.match(r.artifact_sha256,/^[0-9a-f]{64}$/);assert(Number.isSafeInteger(r.job_id));assert(Number.isSafeInteger(r.artifact_id));assert.equal(r.diagnostic_restored_disabled,true);assert.equal(r.conclusion,"success");}
 for(const role of x.roles)assert(role.evidence_run_ids.every(id=>runs.has(id)));
});
test("three arithmetic/causality tasks failed, protected planning never promoted",()=>{
 const m=Object.fromEntries(x.roles.map(r=>[r.domain,r]));
 for(const domain of ["news_causal_join","portfolio_exposure","income_quote_economics"]){assert.equal(m[domain].passed,0);assert.equal(m[domain].proposed_capability,"none");}
 assert.equal(m.tool_plan_safety.proposed_capability,"none");
 assert.equal(m.operator_narrative.human_review_pending,2);
});
