import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import {V4_HOLDOUT_CASES,V4_HOLDOUT_ROLES} from "../src/workforce_v4_holdout.js";
const v=JSON.parse(fs.readFileSync(new URL("../docs/WORKFORCE_V4_CANDIDATE_STATE_20261102.json",import.meta.url),"utf8"));
test("operator projection cannot confuse source preparation with model or deployment acceptance",()=>{
  assert.equal(v.schema,"commandcenter.nvidia_workforce_v4_candidate_state.v1");
  assert.equal(v.stage,"M2_PUBLIC_SOURCE_ONLY");
  assert.deepEqual(v.roles,V4_HOLDOUT_ROLES);
  assert.equal(v.source_visible_first_wave_case_count,V4_HOLDOUT_CASES.length);
  for(const k of ["first_wave_is_independent_holdout","first_wave_gold_is_concealed",
    "provider_cost_observed","reviewer_time_savings_measured"])
    assert.equal(v[k],false);
  for(const k of ["independently_reviewed_hidden_mechanism_count","model_provider_v4_attempts",
    "model_provider_v4_scored_cases","deterministic_same_task_comparators_observed",
    "stronger_worker_same_task_comparators_observed","blind_human_narratives_accepted"])
    assert.equal(v[k],0);
  for(const [key,value] of Object.entries(v.admission)){
    assert.equal(value,key==="active_model_assignments"?0:false);
  }
  assert(v.next_owner_acceptance.length>=6);
});
