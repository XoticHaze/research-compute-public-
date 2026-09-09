import test from 'node:test';
import assert from 'node:assert/strict';

const MM_HEAD = '81a8e42e5171d2e722df546d9e120a96ac3ab32f';

const p64 = Object.freeze({
  product_state: 'DIVERSIFICATION_SLEEVE_SUPPORTED_QQQ200D_TIMING_GATE_REJECTED',
  causal_gate_state: 'REJECTED_SPECIFIC_GATE_MODEL_RETAINED',
  causal_gate: Object.freeze({ run_id: 34344785605, job_id: 102443700557, artifact_id: 10101222898, from2015_excess_vs_matched_pp: -0.54, from2015_excess_vs_qqq_pp: -1.90 }),
});
const p82 = Object.freeze({
  bootstrap_state: 'REGIME_TEMPORAL_STATISTICAL_FRAGILITY',
  bootstrap: Object.freeze({ run_id: 34344879240, job_id: 102444008013, artifact_id: 10101270421, from2015_nonpositive_probability_vs_matched: 0.266, from2015_nonpositive_probability_vs_qqq: 0.387 }),
  chronology_state: 'REGIME_CHRONOLOGY_WEAKNESS_CONFIDENCE_REDUCED_SURVIVOR_PRESERVED',
  chronology: Object.freeze({ run_id: 34346766915, job_id: 102450095558, artifact_id: 10102018001, aggregate_matched: 0.01264951438606765, aggregate_qqq: 0.011234961662293985, rolling24_matched_positive: 0.4915254237288136, rolling36_matched_positive: 0.4528301886792453, rolling36_qqq_positive: 0.3018867924528302, rolling36_median_matched: -0.0035228049937552353, rolling36_median_qqq: -0.015471324448451562 }),
});
const p52 = Object.freeze({ implementation_delay_state: 'IMPLEMENTATION_CAUSALITY_WEAKNESS_NOT_MODEL_FAILURE', delay_5d_excess_vs_matched: 0.0132, delay_5d_positive_folds: 2, fold_count: 5 });
const parked = Object.freeze({
  P15: Object.freeze({ state: 'PARK', run_id: 34343553443, job_id: 102439714518, artifact_id: 10100740824, excess_vs_equal_sector_pp: -3.27, excess_vs_spy_pp: -5.28, excess_vs_qqq_pp: -10.45, positive_folds: 2, fold_count: 5, parameter_rescue: false }),
  P16: Object.freeze({ state: 'PARK', run_id: 34343594802, job_id: 102439846759, artifact_id: 10100749742, excess_vs_raw_pp: -6.01, positive_folds: 1, fold_count: 5, candidate_max_drawdown: -0.1922, raw_max_drawdown: -0.1496, parameter_rescue: false }),
});

test('bind exact private P82 chronology product head under review', () => {
  assert.equal(MM_HEAD, '81a8e42e5171d2e722df546d9e120a96ac3ab32f');
});

test('P64 keeps the specific timing gate rejected', () => {
  assert.equal(p64.product_state, 'DIVERSIFICATION_SLEEVE_SUPPORTED_QQQ200D_TIMING_GATE_REJECTED');
  assert.equal(p64.causal_gate_state, 'REJECTED_SPECIFIC_GATE_MODEL_RETAINED');
  assert.equal(p64.causal_gate.run_id, 34344785605);
  assert.ok(p64.causal_gate.from2015_excess_vs_matched_pp < 0);
  assert.ok(p64.causal_gate.from2015_excess_vs_qqq_pp < 0);
});

test('P82 keeps serial fragility beside positive recent evidence', () => {
  assert.equal(p82.bootstrap_state, 'REGIME_TEMPORAL_STATISTICAL_FRAGILITY');
  assert.equal(p82.bootstrap.run_id, 34344879240);
  assert.ok(p82.bootstrap.from2015_nonpositive_probability_vs_matched > 0.25);
  assert.ok(p82.bootstrap.from2015_nonpositive_probability_vs_qqq > 0.38);
});

test('P82 aggregate delayed edge stays positive while rolling chronology is weak', () => {
  assert.equal(p82.chronology_state, 'REGIME_CHRONOLOGY_WEAKNESS_CONFIDENCE_REDUCED_SURVIVOR_PRESERVED');
  assert.equal(p82.chronology.run_id, 34346766915);
  assert.equal(p82.chronology.job_id, 102450095558);
  assert.equal(p82.chronology.artifact_id, 10102018001);
  assert.ok(p82.chronology.aggregate_matched > 0 && p82.chronology.aggregate_qqq > 0);
  assert.ok(p82.chronology.rolling24_matched_positive < 0.5);
  assert.ok(p82.chronology.rolling36_matched_positive < 0.5);
  assert.ok(p82.chronology.rolling36_qqq_positive < 0.4);
  assert.ok(p82.chronology.rolling36_median_matched < 0);
  assert.ok(p82.chronology.rolling36_median_qqq < 0);
});

test('P52 delay weakness remains visible', () => {
  assert.equal(p52.implementation_delay_state, 'IMPLEMENTATION_CAUSALITY_WEAKNESS_NOT_MODEL_FAILURE');
  assert.ok(p52.delay_5d_excess_vs_matched > 0);
  assert.equal(p52.delay_5d_positive_folds, 2);
});

test('P15 and P16 exact failed sector formulations are parked, not tuning queues', () => {
  assert.equal(parked.P15.state, 'PARK');
  assert.equal(parked.P15.run_id, 34343553443);
  assert.equal(parked.P15.job_id, 102439714518);
  assert.equal(parked.P15.artifact_id, 10100740824);
  assert.ok(parked.P15.excess_vs_equal_sector_pp < 0);
  assert.ok(parked.P15.excess_vs_spy_pp < 0);
  assert.ok(parked.P15.excess_vs_qqq_pp < 0);
  assert.ok(parked.P15.positive_folds < 3);
  assert.equal(parked.P15.parameter_rescue, false);

  assert.equal(parked.P16.state, 'PARK');
  assert.equal(parked.P16.run_id, 34343594802);
  assert.equal(parked.P16.job_id, 102439846759);
  assert.equal(parked.P16.artifact_id, 10100749742);
  assert.ok(parked.P16.excess_vs_raw_pp < 0);
  assert.ok(parked.P16.positive_folds < 3);
  assert.ok(parked.P16.candidate_max_drawdown < parked.P16.raw_max_drawdown);
  assert.equal(parked.P16.parameter_rescue, false);
});

test('no portfolio or trading authority', () => {
  assert.deepEqual(Object.values({ranking:false,allocation:false,sizing:false,timing:false,promotion:false,strategy:false,runtime:false,data:false,broker:false,live:false}), Array(10).fill(false));
});
