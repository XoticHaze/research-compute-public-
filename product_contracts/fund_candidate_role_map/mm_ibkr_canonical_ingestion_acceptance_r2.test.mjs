import test from 'node:test';
import assert from 'node:assert/strict';

const SOURCE = Object.freeze({
  repository: 'XoticHaze/mm-IBKR',
  pairing_pr: 556,
  pairing_merge_commit: '6f396254c119608e5bfec1c734384e4b02fbfaaa',
  provenance_pr: 557,
  provenance_merge_commit: '925762878e610910c95b0d0af1138b3d5d40c847',
  source_file: 'strategy_health_canonical_trade_consumer.py',
  acceptance_scope: 'sanitized deterministic contract for canonical ingestion pairing and producer source provenance only',
});

function text(value) {
  if (value == null) return null;
  const normalized = String(value).trim();
  return normalized || null;
}

function requireExplicitMaterializerPairing(row) {
  const fields = [
    'producer_evidence_state',
    'producer_evidence_conflicts',
    'producer_evidence_inference',
  ];
  if (!fields.some((field) => Object.hasOwn(row, field))) return;
  if (!(
    row.producer_evidence_state === 'EXPLICIT_MATCH' &&
    Array.isArray(row.producer_evidence_conflicts) &&
    row.producer_evidence_conflicts.length === 0 &&
    row.producer_evidence_inference === false
  )) {
    throw new Error('producer_pairing_not_explicit_conflict_free:0');
  }
}

function projectSourceRef(row, fallback = 'canonical_backtest_completed_trade_ledger') {
  const sourceRef = text(row.source_ref);
  const provenance = {
    complete: sourceRef !== null,
    missing: sourceRef === null ? ['source_ref'] : [],
    source_ref: sourceRef,
  };
  return {
    source_ref: provenance.source_ref || fallback,
    producer_provenance_attribution: {
      complete: provenance.complete,
      missing: [...provenance.missing],
    },
  };
}

test('source authority is pinned to merged mm-IBKR PRs 556 and 557', () => {
  assert.equal(SOURCE.pairing_merge_commit, '6f396254c119608e5bfec1c734384e4b02fbfaaa');
  assert.equal(SOURCE.provenance_merge_commit, '925762878e610910c95b0d0af1138b3d5d40c847');
});

test('direct canonical producer row remains admissible', () => {
  assert.doesNotThrow(() => requireExplicitMaterializerPairing({ symbol: 'MNQ' }));
});

test('explicit conflict-free materialized row remains admissible', () => {
  assert.doesNotThrow(() => requireExplicitMaterializerPairing({
    producer_evidence_state: 'EXPLICIT_MATCH',
    producer_evidence_conflicts: [],
    producer_evidence_inference: false,
  }));
});

for (const [name, row] of [
  ['conflict', { producer_evidence_state: 'CONFLICT', producer_evidence_conflicts: ['runtime_id'], producer_evidence_inference: false }],
  ['missing pair', { producer_evidence_state: 'PAIR_NOT_FOUND', producer_evidence_conflicts: [], producer_evidence_inference: false }],
  ['inferred pair', { producer_evidence_state: 'EXPLICIT_MATCH', producer_evidence_conflicts: [], producer_evidence_inference: true }],
]) {
  test(`${name} fails closed at canonical ingestion`, () => {
    assert.throws(() => requireExplicitMaterializerPairing(row), /producer_pairing_not_explicit_conflict_free:0/);
  });
}

test('exact canonical producer source reference survives projection', () => {
  const projected = projectSourceRef({ source_ref: 'immutable:trade:mnq:exact' });
  assert.equal(projected.source_ref, 'immutable:trade:mnq:exact');
  assert.deepEqual(projected.producer_provenance_attribution, { complete: true, missing: [] });
});

test('missing producer source reference uses canonical fallback while attribution stays incomplete', () => {
  const projected = projectSourceRef({ source_ref: '   ' });
  assert.equal(projected.source_ref, 'canonical_backtest_completed_trade_ledger');
  assert.deepEqual(projected.producer_provenance_attribution, { complete: false, missing: ['source_ref'] });
});
