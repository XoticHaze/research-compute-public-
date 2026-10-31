// Bounded Durable Object replay ledger for Pi read-only Git-outbox observations.
// The independent issuer must still authenticate the actual private Git commit/blob.
export function nextPiReplayLedger(prior, envelope, nowMs = Date.now()) {
  const TTL_MS = 24 * 60 * 60 * 1000;
  const MAX_ENTRIES = 2048;
  if (!Number.isSafeInteger(nowMs) || nowMs < 0) throw new Error('pi_replay_clock_invalid');
  const requestId = envelope?.request_id;
  const commitSha = envelope?.result_commit_sha;
  if (typeof requestId !== 'string' || !/^[A-Za-z0-9._:-]{6,100}$/.test(requestId)
      || typeof commitSha !== 'string' || !/^[0-9a-f]{40}$/.test(commitSha)) {
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
        || typeof row.result_commit_sha !== 'string'
        || !/^[0-9a-f]{40}$/.test(row.result_commit_sha)
        || !Number.isSafeInteger(row.expires_at_ms) || row.expires_at_ms < 0) {
      throw new Error('pi_replay_ledger_invalid');
    }
    if (row.expires_at_ms > nowMs) entries.push(row);
  }
  if (entries.some(row => row.request_id === requestId || row.result_commit_sha === commitSha)) {
    throw new Error('pi_replay_detected');
  }
  if (entries.length >= MAX_ENTRIES) throw new Error('pi_replay_ledger_capacity_held');
  return {
    schema: 'mmibkr.pi_replay_ledger.v1',
    entries: [...entries, { request_id: requestId, result_commit_sha: commitSha,
      expires_at_ms: nowMs + TTL_MS }],
  };
}
