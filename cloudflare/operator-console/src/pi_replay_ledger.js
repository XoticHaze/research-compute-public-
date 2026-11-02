import { piReplayIdentity } from './pi_account_observation.js';
// Bounded Durable Object replay ledger for Pi read-only Git-outbox observations.
// Private Git identity is verified by the bridge; this ledger stores only opaque HMAC receipts.
export function nextPiReplayLedger(prior, envelope, nowMs = Date.now()) {
  const TTL_MS = 24 * 60 * 60 * 1000;
  const MAX_ENTRIES = 2048;
  if (!Number.isSafeInteger(nowMs) || nowMs < 0) throw new Error('pi_replay_clock_invalid');
  // The Worker supplies a fully validated versioned envelope. Direct callers of
  // this internal ledger helper may provide a prevalidated bare replay identity.
  const requestId = envelope?.schema ? piReplayIdentity(envelope) : envelope?.request_id;
  const receiptId = envelope?.source_receipt_id;
  if (typeof requestId !== 'string' || !/^[A-Za-z0-9._:-]{6,100}$/.test(requestId)
      || typeof receiptId !== 'string' || !/^[0-9a-f]{64}$/.test(receiptId)) {
    throw new Error('pi_replay_identity_invalid');
  }
  if (prior != null && (prior.schema !== 'mmibkr.pi_replay_ledger.v1'
      || !Array.isArray(prior.entries) || prior.entries.length > MAX_ENTRIES)) {
    throw new Error('pi_replay_ledger_invalid');
  }
  const entries = [];
  for (const row of prior?.entries || []) {
    if (!row || typeof row.request_id !== 'string'
        || !/^[A-Za-z0-9._:-]{6,100}$/.test(row.request_id)
        || typeof row.source_receipt_id !== 'string'
        || !/^[0-9a-f]{64}$/.test(row.source_receipt_id)
        || !Number.isSafeInteger(row.expires_at_ms) || row.expires_at_ms < 0) {
      throw new Error('pi_replay_ledger_invalid');
    }
    if (row.expires_at_ms > nowMs) entries.push(row);
  }
  if (entries.some(row => row.request_id === requestId || row.source_receipt_id === receiptId)) {
    throw new Error('pi_replay_detected');
  }
  if (entries.length >= MAX_ENTRIES) throw new Error('pi_replay_ledger_capacity_held');
  return {
    schema: 'mmibkr.pi_replay_ledger.v1',
    entries: [...entries, { request_id: requestId, source_receipt_id: receiptId,
      expires_at_ms: nowMs + TTL_MS }],
  };
}
