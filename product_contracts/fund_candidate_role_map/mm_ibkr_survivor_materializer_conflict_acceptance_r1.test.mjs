import test from 'node:test';
import assert from 'node:assert/strict';

const SOURCE = Object.freeze({
  repository: 'XoticHaze/mm-IBKR',
  pr: 554,
  merge_commit: '5257dcfeba6920a12daf27dba1280e42ed71fbf4',
  source_file: 'scripts/operator/audit_survivor_paper_trade_acceptance_v1.py',
  acceptance_scope: 'sanitized deterministic contract for materializer pairing admission only',
});

function materializerPairingGap(row) {
  const fields = [
    'producer_evidence_state',
    'producer_evidence_conflicts',
    'producer_evidence_inference',
  ];
  const hasMaterializerMetadata = fields.some((field) => Object.hasOwn(row, field));
  if (!hasMaterializerMetadata) return [];

  if (
    row.producer_evidence_state === 'EXPLICIT_MATCH' &&
    Array.isArray(row.producer_evidence_conflicts) &&
    row.producer_evidence_conflicts.length === 0 &&
    row.producer_evidence_inference === false
  ) {
    return [];
  }
  return ['producer_pairing_not_explicit_conflict_free'];
}

test('source identity is pinned to merged mm-IBKR PR 554', () => {
  assert.equal(SOURCE.merge_commit, '5257dcfeba6920a12daf27dba1280e42ed71fbf4');
});

test('direct canonical producer row remains admissible without materializer metadata', () => {
  assert.deepEqual(materializerPairingGap({ symbol: 'AMAT' }), []);
});

test('explicit conflict-free materialized row is admissible', () => {
  assert.deepEqual(materializerPairingGap({
    producer_evidence_state: 'EXPLICIT_MATCH',
    producer_evidence_conflicts: [],
    producer_evidence_inference: false,
  }), []);
});

test('CONFLICT state cannot be masked by otherwise complete evidence', () => {
  assert.deepEqual(materializerPairingGap({
    producer_evidence_state: 'CONFLICT',
    producer_evidence_conflicts: ['runtime_id'],
    producer_evidence_inference: false,
  }), ['producer_pairing_not_explicit_conflict_free']);
});

test('PAIR_NOT_FOUND cannot be masked by otherwise complete evidence', () => {
  assert.deepEqual(materializerPairingGap({
    producer_evidence_state: 'PAIR_NOT_FOUND',
    producer_evidence_conflicts: [],
    producer_evidence_inference: false,
  }), ['producer_pairing_not_explicit_conflict_free']);
});

test('inferred producer pairing remains fail-closed', () => {
  assert.deepEqual(materializerPairingGap({
    producer_evidence_state: 'EXPLICIT_MATCH',
    producer_evidence_conflicts: [],
    producer_evidence_inference: true,
  }), ['producer_pairing_not_explicit_conflict_free']);
});
