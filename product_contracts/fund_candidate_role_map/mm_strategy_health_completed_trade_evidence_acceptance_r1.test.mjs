import test from 'node:test';
import assert from 'node:assert/strict';

const SOURCE = Object.freeze({
  repository: 'XoticHaze/mm-IBKR',
  pull_request: 572,
  head_commit: 'f1362ff71303b4b293e069aa24b95eed3ee17f89',
  source_file: 'strategy_health_evidence_pipeline.py',
  scope: 'sanitized deterministic acceptance of read-only completed_trade_evidence projection only',
});

function completedTradeEvidence(preview, availability) {
  const symbol = String(preview?.symbol || '').toUpperCase();
  const rows = availability && typeof availability === 'object' ? availability.symbols : null;
  const row = rows && typeof rows === 'object' ? rows[symbol] : null;

  if (!row || typeof row !== 'object') {
    return {
      state: 'UNKNOWN',
      symbol,
      bridge_ready_runs: 0,
      missing_evidence: ['paper_run_availability_audit_not_supplied'],
      source_ref: 'audit_survivor_paper_run_availability_v1:unavailable',
    };
  }

  const ready = Number(row.bridge_ready_runs || 0);
  const missing = Array.isArray(row.missing_evidence)
    ? row.missing_evidence.map((item) => String(item)).filter((item) => item.trim())
    : [];

  return {
    state: ready > 0 ? 'BRIDGE_READY' : 'INSUFFICIENT_EVIDENCE',
    symbol,
    bridge_ready_runs: ready,
    intent_only_runs: Number(row.intent_only_runs || 0),
    ledger_only_runs: Number(row.ledger_only_runs || 0),
    missing_evidence: missing,
    source_ref: String(availability.schema || 'audit_survivor_paper_run_availability_v1'),
  };
}

test('acceptance is pinned to mm-IBKR PR 572 head', () => {
  assert.equal(SOURCE.pull_request, 572);
  assert.equal(SOURCE.head_commit, 'f1362ff71303b4b293e069aa24b95eed3ee17f89');
});

test('missing availability audit remains operator-visible and fail-closed', () => {
  assert.deepEqual(completedTradeEvidence({ symbol: 'mnq' }, null), {
    state: 'UNKNOWN',
    symbol: 'MNQ',
    bridge_ready_runs: 0,
    missing_evidence: ['paper_run_availability_audit_not_supplied'],
    source_ref: 'audit_survivor_paper_run_availability_v1:unavailable',
  });
});

test('bridge-ready audit is exposed without implying attribution authority', () => {
  const gate = completedTradeEvidence(
    { symbol: 'MNQ' },
    {
      schema: 'survivor-paper-run-availability-audit-v1',
      symbols: {
        MNQ: {
          bridge_ready_runs: 2,
          intent_only_runs: 1,
          ledger_only_runs: 0,
          missing_evidence: [],
        },
      },
    },
  );

  assert.equal(gate.state, 'BRIDGE_READY');
  assert.equal(gate.bridge_ready_runs, 2);
  assert.equal(gate.intent_only_runs, 1);
  assert.equal(gate.ledger_only_runs, 0);
  assert.deepEqual(gate.missing_evidence, []);
  assert.equal(gate.source_ref, 'survivor-paper-run-availability-audit-v1');
});

test('zero ready runs preserve exact missing canonical evidence', () => {
  const gate = completedTradeEvidence(
    { symbol: 'MNQ' },
    {
      schema: 'survivor-paper-run-availability-audit-v1',
      symbols: {
        MNQ: {
          bridge_ready_runs: 0,
          intent_only_runs: 3,
          ledger_only_runs: 1,
          missing_evidence: ['paper_pnl_ledger.csv', 'matching producer pair'],
        },
      },
    },
  );

  assert.equal(gate.state, 'INSUFFICIENT_EVIDENCE');
  assert.equal(gate.bridge_ready_runs, 0);
  assert.equal(gate.intent_only_runs, 3);
  assert.equal(gate.ledger_only_runs, 1);
  assert.deepEqual(gate.missing_evidence, ['paper_pnl_ledger.csv', 'matching producer pair']);
});

test('availability projection cannot manufacture readiness for an absent symbol row', () => {
  const gate = completedTradeEvidence(
    { symbol: 'APH' },
    { schema: 'survivor-paper-run-availability-audit-v1', symbols: { MNQ: { bridge_ready_runs: 4 } } },
  );

  assert.equal(gate.state, 'UNKNOWN');
  assert.equal(gate.bridge_ready_runs, 0);
  assert.deepEqual(gate.missing_evidence, ['paper_run_availability_audit_not_supplied']);
});
