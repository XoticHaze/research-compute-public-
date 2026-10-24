// Source-only, pure reducer for a proposed IBKR sole-writer protocol.
// NOT a deployed lease, broker authorization, trusted evidence verifier, or order gate.
// A future single serialized durable authority must supply trusted server time, persist
// every transition atomically, attest external evidence, and prevent stale IB sessions.
export const FENCE_SCHEMA = 'mmibkr-live-owner-fence-transition.v1';
const ACCOUNT_SHA = /^[a-f0-9]{64}$/;
const OWNER_ID = /^[0-9]{4,24}:[1-9][0-9]{0,5}$/;
const MAX_TTL_MS = 30_000;

export function initialFrozenFence() {
  return Object.freeze({
    schema: FENCE_SCHEMA, epoch: 0, accountDigest: null,
    holder: null, expiresAtMs: null, lastServerMs: 0,
  });
}

const denied = (state, reason) => ({ ok: false, status: reason, state });
const admitted = (state, status) => ({ ok: true, status, state });
const safeClock = (value) => Number.isSafeInteger(value) && value >= 0;
const goodTtl = (value) => Number.isSafeInteger(value) && value > 0 && value <= MAX_TTL_MS;
const goodOwner = (value) => typeof value === 'string' && OWNER_ID.test(value);
const goodAccount = (value) => typeof value === 'string' && ACCOUNT_SHA.test(value);

// All proof booleans are placeholders for *independently verified* evidence,
// NEVER for caller-supplied claims. Fail closed unless a trusted adapter verifies.
const takeoverProof = (p) => Boolean(
  p?.operatorAttested === true &&
  p?.predecessorGatewayTerminated === true &&
  p?.predecessorWriterQuiesced === true &&
  p?.brokerJournalReconciled === true &&
  p?.allBrokerWriteSessionsExcluded === true
);

export function transitionFrozenFence(state, request) {
  if (!state || state.schema !== FENCE_SCHEMA ||
      !safeClock(state.epoch) || !safeClock(state.lastServerMs) ||
      (state.accountDigest !== null && !goodAccount(state.accountDigest)) ||
      (state.holder !== null && !goodOwner(state.holder)) ||
      (state.expiresAtMs !== null && !safeClock(state.expiresAtMs)) ||
      ((state.holder === null) !== (state.expiresAtMs === null)) ||
      (state.epoch === 0 && state.accountDigest !== null) ||
      (state.epoch > 0 && state.accountDigest === null)) {
    return denied(state, 'invalid_persisted_state');
  }
  const now = request?.serverNowMs;
  if (!safeClock(now) || now < state.lastServerMs)
    return denied(state, 'untrusted_or_regressing_clock');
  if (!safeClock(request?.expectedEpoch) || request.expectedEpoch !== state.epoch)
    return denied(state, 'stale_fencing_epoch');
  const account = request?.accountDigest;
  if (!goodAccount(account) || (state.accountDigest && state.accountDigest !== account))
    return denied(state, 'account_scope_mismatch');
  const who = request?.ownerRunAttempt;
  if (!goodOwner(who)) return denied(state, 'owner_identity_invalid');

  if (request.operation === 'acquire') {
    if (!goodTtl(request.ttlMs)) return denied(state, 'ttl_invalid');
    if (now > Number.MAX_SAFE_INTEGER - request.ttlMs)
      return denied(state, 'clock_range_overflow');
    if (state.holder && now < state.expiresAtMs)
      return denied(state, 'incumbent_not_expired');
    // Expiry does not imply takeover safety. An expired still-connected
    // predecessor may write to the broker until proven quiescent.
    if (!takeoverProof(request.verifiedEvidence))
      return denied(state, 'takeover_evidence_incomplete');
    if (state.epoch === Number.MAX_SAFE_INTEGER)
      return denied(state, 'epoch_exhausted');
    return admitted({
      schema: FENCE_SCHEMA, epoch: state.epoch + 1,
      accountDigest: account, holder: who,
      expiresAtMs: now + request.ttlMs, lastServerMs: now,
    }, 'candidate_lease_recorded_not_broker_authorized');
  }
  if (request.operation === 'renew') {
    if (!goodTtl(request.ttlMs)) return denied(state, 'ttl_invalid');
    if (now > Number.MAX_SAFE_INTEGER - request.ttlMs)
      return denied(state, 'clock_range_overflow');
    if (state.holder !== who || !state.expiresAtMs || now >= state.expiresAtMs)
      return denied(state, 'not_current_unexpired_holder');
    if (request.verifiedEvidence?.sameBrokerSession === true &&
        request.verifiedEvidence?.ownerStillAuthenticated === true) {
      return admitted({ ...state, expiresAtMs: now + request.ttlMs, lastServerMs: now },
        'candidate_lease_renewed_not_broker_authorized');
    }
    return denied(state, 'renew_evidence_incomplete');
  }
  if (request.operation === 'retire') {
    if (state.holder !== who) return denied(state, 'retire_not_holder');
    if (request.verifiedEvidence?.allBrokerWriteSessionsExcluded !== true)
      return denied(state, 'retire_session_not_excluded');
    if (state.epoch === Number.MAX_SAFE_INTEGER)
      return denied(state, 'epoch_exhausted');
    return admitted({
      ...state, epoch: state.epoch + 1, holder: null,
      expiresAtMs: null, lastServerMs: now,
    }, 'candidate_retired_wait_for_fresh_takeover_proof');
  }
  return denied(state, 'unsupported_transition');
}

// IMPORTANT: There is deliberately NO isAllowedToPlaceOrder() here.
// A state reducer and remote lease check cannot fence a stale connected
// IBKR writer between check and placeOrder. Broker-session exclusion and
// canonical mutation-boundary integration require independent implementation.
