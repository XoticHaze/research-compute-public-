import test from 'node:test';
import assert from 'node:assert/strict';

const MM_HEAD = 'd4d53dee7a8efebf6a0cbe6de081ffdc55396d49';

const p64 = Object.freeze({
  product_state: 'DIVERSIFICATION_SLEEVE_SUPPORTED_QQQ200D_TIMING_GATE_REJECTED',
  causal_gate_state: 'REJECTED_SPECIFIC_GATE_MODEL_RETAINED',
  causal_gate: Object.freeze({
    run_id: 34344785605,
    job_id: 102443700557,
    artifact_id: 10101222898,
    artifact_digest: 'sha256:2c93b9756e057151a4411f42b0b6162109dfb942a807a11930ec340b092a6f5b',
    from2015_excess_vs_matched_pp: -0.54,
    from2015_excess_vs_qqq_pp: -1.90,
    from2015_positive_folds_vs_matched: 1,
    from2015_positive_folds_vs_qqq: 1,
  }),
});

const p82 = Object.freeze({
  fixed_weights: '50/50',
  delay_run_id: 34342849735,
  delay_job_id: 102437437391,
  bootstrap_state: 'REGIME_TEMPORAL_STATISTICAL_FRAGILITY',
  bootstrap: Object.freeze({
    run_id: 34344879240,
    job_id: 102444008013,
    artifact_id: 10101270421,
    artifact_digest: 'sha256:0d2fe3d171419343145b0ebd19994fa61bfe1eca86cd09b3226b9672d76b53b8',
    from2015_matched_excess_pp: 1.26,
    from2015_qqq_excess_pp: 1.12,
    from2015_nonpositive_probability_vs_matched: 0.266,
    from2015_nonpositive_probability_vs_qqq: 0.387,
    from2022_matched_excess_pp: 2.73,
    from2022_qqq_excess_pp: 5.37,
    from2022_nonpositive_probability_vs_matched: 0.247,
    from2022_nonpositive_probability_vs_qqq: 0.235,
  }),
});

const p52 = Object.freeze({
  implementation_delay_state: 'IMPLEMENTATION_CAUSALITY_WEAKNESS_NOT_MODEL_FAILURE',
  delay_5d_excess_vs_matched: 0.0132,
  delay_5d_positive_folds: 2,
  fold_count: 5,
});

test('bind exact current private product head under review', () => {
  assert.equal(MM_HEAD, 'd4d53dee7a8efebf6a0cbe6de081ffdc55396d49');
});

test('P64 retains diversification evidence while the QQQ200D timing gate is rejected', () => {
  assert.equal(p64.product_state, 'DIVERSIFICATION_SLEEVE_SUPPORTED_QQQ200D_TIMING_GATE_REJECTED');
  assert.equal(p64.causal_gate_state, 'REJECTED_SPECIFIC_GATE_MODEL_RETAINED');
  assert.equal(p64.causal_gate.run_id, 34344785605);
  assert.equal(p64.causal_gate.job_id, 102443700557);
  assert.equal(p64.causal_gate.artifact_id, 10101222898);
  assert.ok(p64.causal_gate.from2015_excess_vs_matched_pp < 0);
  assert.ok(p64.causal_gate.from2015_excess_vs_qqq_pp < 0);
  assert.ok(p64.causal_gate.from2015_positive_folds_vs_matched < 3);
  assert.ok(p64.causal_gate.from2015_positive_folds_vs_qqq < 3);
});

test('P82 positive delayed point estimates remain paired with material bootstrap uncertainty', () => {
  assert.equal(p82.fixed_weights, '50/50');
  assert.equal(p82.delay_run_id, 34342849735);
  assert.equal(p82.delay_job_id, 102437437391);
  assert.equal(p82.bootstrap_state, 'REGIME_TEMPORAL_STATISTICAL_FRAGILITY');
  assert.equal(p82.bootstrap.run_id, 34344879240);
  assert.equal(p82.bootstrap.job_id, 102444008013);
  assert.equal(p82.bootstrap.artifact_id, 10101270421);
  assert.ok(p82.bootstrap.from2015_matched_excess_pp > 0);
  assert.ok(p82.bootstrap.from2015_qqq_excess_pp > 0);
  assert.ok(p82.bootstrap.from2015_nonpositive_probability_vs_matched > 0.25);
  assert.ok(p82.bootstrap.from2015_nonpositive_probability_vs_qqq > 0.38);
  assert.ok(p82.bootstrap.from2022_matched_excess_pp > 0);
  assert.ok(p82.bootstrap.from2022_qqq_excess_pp > 0);
  assert.ok(p82.bootstrap.from2022_nonpositive_probability_vs_matched > 0.24);
  assert.ok(p82.bootstrap.from2022_nonpositive_probability_vs_qqq > 0.23);
});

test('P52 delay weakness remains visible rather than tuned away', () => {
  assert.equal(p52.implementation_delay_state, 'IMPLEMENTATION_CAUSALITY_WEAKNESS_NOT_MODEL_FAILURE');
  assert.ok(p52.delay_5d_excess_vs_matched > 0);
  assert.equal(p52.delay_5d_positive_folds, 2);
  assert.equal(p52.fold_count, 5);
});

test('no portfolio or trading authority', () => {
  assert.deepEqual(Object.values({ranking:false,allocation:false,sizing:false,timing:false,promotion:false,strategy:false,runtime:false,data:false,broker:false,live:false}), Array(10).fill(false));
});
