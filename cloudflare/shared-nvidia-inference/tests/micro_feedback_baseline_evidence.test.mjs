// Offline evidence reconciliation only. Never fetch provider or execute actions.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {MICRO_CASES} from '../src/micro_worker_fixtures.js';
import {FEEDBACK_HOLDOUTS,FEEDBACK_LESSON,FEEDBACK_LESSON_BY_CATEGORY} from '../src/micro_feedback_holdouts.js';
const baseline=JSON.parse(fs.readFileSync(new URL('../docs/MICRO_FEEDBACK_BASELINE_OBSERVED_20261119.v1.json',import.meta.url),'utf8'));
const PROTECTED=new Set(['placement','security','command']);
test('historical baseline binds exact source, model, 24 distinct public synthetic cases',()=>{
 assert.equal(baseline.schema,'commandcenter.nvidia_micro_historical_baseline_evidence.v1');
 assert.equal(baseline.provenance.run_id,44499436768);
 assert.equal(baseline.provenance.job_id,135474982647);
 assert.equal(baseline.provenance.worker_source_sha,'abd8fcac5299aaf5308e831db6a1fcfcd5066898');
 assert.equal(baseline.provenance.model,'poolside/laguna-xs-2.1');
 assert.equal(baseline.provenance.external_log_identity_verified_by_this_json,false);
 assert.equal(baseline.scope.commands_executed,false);
 assert.equal(baseline.scope.private_data_used,false);
 assert.equal(baseline.scope.production_admitted,false);
 assert.equal(baseline.observations.length,24);
 assert.equal(new Set(baseline.observations.map(x=>x.case_id)).size,24);
});
test('independently recompute reported scores, category counts and protected misses from source fixture',()=>{
 const observed=baseline.observations;
 let passing=0,protectedCount=0,protectedPassing=0;
 for(let i=0;i<observed.length;i++){
  const a=observed[i],b=MICRO_CASES[i];
  assert.equal(a.case_id,b.id);
  assert.equal(a.category,b.category);
  assert.equal(a.protected,PROTECTED.has(b.category));
  assert.equal(a.http_status,200);
  assert.equal(a.format_valid,true);
  assert(Number.isInteger(a.latency_ms)&&a.latency_ms>=0&&a.latency_ms<=18000);
  const pass=a.observed_action===b.action&&a.observed_route===b.route;
  assert.equal(a.passed,pass,'source oracle mismatch at '+b.id);
  passing+=Number(pass);
  if(a.protected){protectedCount++;protectedPassing+=Number(pass);}
 }
 assert.equal(passing,21);
 assert.equal(protectedCount,12);
 assert.equal(protectedPassing,11);
 assert.deepEqual(observed.filter(x=>!x.passed).map(x=>x.case_id),['R04','P03','C02']);
 assert.equal(baseline.summary.attempted,24);
 assert.equal(baseline.summary.passed,passing);
 assert.equal(baseline.summary.protected_attempted,protectedCount);
 assert.equal(baseline.summary.protected_passed,protectedPassing);
 assert.deepEqual(baseline.summary.failed_case_ids,['R04','P03','C02']);
 assert.deepEqual(Object.keys(FEEDBACK_LESSON_BY_CATEGORY).sort(), [...new Set(observed.filter(x=>!x.passed).map(x=>x.category))].sort());
});
test('lessons remain category-level, no exact holdout keys or hidden answer output in prompt',()=>{
 assert.equal(FEEDBACK_HOLDOUTS.length,12);
 assert(!FEEDBACK_LESSON.includes('F01')&&!FEEDBACK_LESSON.includes('F05'));
 assert(!FEEDBACK_LESSON.includes('R04')&&!FEEDBACK_LESSON.includes('P03'));
 assert(!FEEDBACK_LESSON.includes('C02'));
 assert(FEEDBACK_LESSON.includes('final receipts'));
 assert(FEEDBACK_LESSON.includes('Executor placement'));
 assert(FEEDBACK_LESSON.includes('human review'));
});
