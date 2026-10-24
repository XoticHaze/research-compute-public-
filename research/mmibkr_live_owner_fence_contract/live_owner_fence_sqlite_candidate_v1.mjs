// Candidate SQLite state adapter ONLY. No Worker route imports this module.
// Reuses the existing SQLite-backed Fleet SOURCE_EXCHANGE Durable Object storage
// contract, but does not deploy, authorize IBKR or infer closed broker sessions.
// A single globally addressed DO + independently VERIFIED broker evidence,
// server time, OIDC/session identity and canonical mutation boundary remain
// mandatory before operational deployment. Do not invoke with caller evidence.
import {
  initialFrozenFence, transitionFrozenFence,
} from './live_owner_fence_transition_v1.mjs';

const ACCOUNT_SHA = /^[0-9a-f]{64}$/;
const SCHEMA_SQL = "CREATE TABLE IF NOT EXISTS mmibkr_live_fence_candidate_v1 (account_digest TEXT PRIMARY KEY NOT NULL, state_json TEXT NOT NULL)";
const SELECT_SQL = "SELECT state_json FROM mmibkr_live_fence_candidate_v1 WHERE account_digest = ? LIMIT 2";
const UPSERT_SQL = "INSERT INTO mmibkr_live_fence_candidate_v1 (account_digest, state_json) VALUES (?, ?) ON CONFLICT(account_digest) DO UPDATE SET state_json=excluded.state_json";

const deny = (reason) => ({
  ok: false, status: reason, candidate_only: true,
  live_submit_authorized: false, broker_mutation_attempted: false,
});

/**
 * Perform one synchronous read/transition/write in the same SQLite transaction.
 *
 * The trusted argument must be constructed by a FUTURE independently audited
 * issuer (not caller JSON): serverNowMs plus verifiedEvidence.
 * This adapter cannot verify witness truth or revoke an IBKR session.
 * request may NOT supply its own server clock or evidence.
 *
 * The returned ok is ONLY "candidate state committed", NEVER a
 * broker-mutation authorization, even if the epoch is current.
 */
export function applyCandidateSqliteTransition({ storage, request, trusted } = {}) {
  try {
    if (!request || !ACCOUNT_SHA.test(request.accountDigest || ''))
      return deny('candidate_account_digest_required');
    if (Object.hasOwn(request, 'serverNowMs') ||
        Object.hasOwn(request, 'verifiedEvidence'))
      return deny('caller_clock_or_evidence_rejected');
    if (!trusted || !Number.isSafeInteger(trusted.serverNowMs) ||
        !trusted.verifiedEvidence || typeof trusted.verifiedEvidence !== 'object')
      return deny('trusted_transition_context_required');
    if (!storage || typeof storage.transactionSync !== 'function' ||
        typeof storage.sql?.exec !== 'function')
      return deny('candidate_sqlite_transaction_unavailable');

    return storage.transactionSync(() => {
      storage.sql.exec(SCHEMA_SQL);
      const raw = storage.sql.exec(SELECT_SQL, request.accountDigest).toArray();
      if (!Array.isArray(raw) || raw.length > 1)
        return deny('candidate_storage_row_count_invalid');
      let current = initialFrozenFence();
      if (raw.length === 1) {
        if (typeof raw[0]?.state_json !== 'string')
          return deny('candidate_stored_state_invalid');
        try { current = JSON.parse(raw[0].state_json); }
        catch { return deny('candidate_stored_state_invalid'); }
      }
      const proposal = transitionFrozenFence(current, {
        ...request,
        serverNowMs: trusted.serverNowMs,
        verifiedEvidence: trusted.verifiedEvidence,
      });
      if (!proposal.ok) return deny(proposal.status);
      // Never respond success before SQLite commits the transaction.
      storage.sql.exec(UPSERT_SQL, request.accountDigest, JSON.stringify(proposal.state));
      return {
        ok: true, status: proposal.status, candidate_only: true,
        epoch: proposal.state.epoch,
        live_submit_authorized: false, broker_mutation_attempted: false,
      };
    });
  } catch {
    // No SQL exception, account key, credentials or broker output escapes.
    return deny('candidate_sqlite_transaction_failed');
  }
}
