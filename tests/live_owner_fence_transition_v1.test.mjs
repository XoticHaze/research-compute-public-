import test from 'node:test';
import assert from 'node:assert/strict';
import {
  FENCE_SCHEMA, initialFrozenFence, transitionFrozenFence,
} from '../cloudflare/fleet-authority/src/live_owner_fence_transition_v1.mjs';

const account = 'a'.repeat(64);
const otherAccount = 'b'.repeat(64);
const ownerA = '40000000001:1';
const ownerB = '40000000002:1';
const full = {
  operatorAttested: true,
  predecessorGatewayTerminated: true,
  predecessorWriterQuiesced: true,
  brokerJournalReconciled: true,
  allBrokerWriteSessionsExcluded: true,
};
const req = (operation, overrides = {}) => ({
  operation, serverNowMs: 1_000, expectedEpoch: 0,
  accountDigest: account, ownerRunAttempt: ownerA,
  ttlMs: 10_000, verifiedEvidence: full, ...overrides,
});
const acquire = (overrides = {}) =>
  transitionFrozenFence(initialFrozenFence(), req('acquire', overrides));

test('default frozen state carries no holder or implicit broker permission', () => {
  const state = initialFrozenFence();
  assert.equal(state.schema, FENCE_SCHEMA);
  assert.equal(state.epoch, 0);
  assert.equal(state.holder, null);
  assert.equal(typeof state.allowedToPlaceOrder, 'undefined');
});
test('initial acquisition denies every independently necessary evidence item', () => {
  for (const key of Object.keys(full)) {
    const res = acquire({ verifiedEvidence: { ...full, [key]: false } });
    assert.equal(res.ok, false, key);
    assert.equal(res.status, 'takeover_evidence_incomplete');
    assert.equal(res.state.epoch, 0);
  }
  assert.equal(acquire({ verifiedEvidence: {} }).ok, false);
});
test('valid evidence admits only candidate lease epoch, never broker order', () => {
  const r = acquire();
  assert.equal(r.ok, true);
  assert.equal(r.state.epoch, 1);
  assert.equal(r.state.holder, ownerA);
  assert.match(r.status, /not_broker_authorized/);
  assert.equal(typeof r.state.allowedToPlaceOrder, 'undefined');
});
test('a second host cannot acquire before incumbent expires', () => {
  const first = acquire().state;
  const r = transitionFrozenFence(first, req('acquire', {
    serverNowMs: 2_000, expectedEpoch: 1, ownerRunAttempt: ownerB,
  }));
  assert.equal(r.status, 'incumbent_not_expired');
  assert.strictEqual(r.state, first);
});
test('expiration never grants takeover without fresh predecessor quiescence', () => {
  const first = acquire().state;
  const r = transitionFrozenFence(first, req('acquire', {
    serverNowMs: 12_000, expectedEpoch: 1,
    ownerRunAttempt: ownerB, verifiedEvidence: { ...full, predecessorWriterQuiesced: false },
  }));
  assert.equal(r.status, 'takeover_evidence_incomplete');
  const accepted = transitionFrozenFence(first, req('acquire', {
    serverNowMs: 12_000, expectedEpoch: 1, ownerRunAttempt: ownerB,
  }));
  assert.equal(accepted.ok, true);
  assert.equal(accepted.state.epoch, 2);
  assert.equal(accepted.state.holder, ownerB);
});
test('stale owner cannot renew or retire after successor epoch', () => {
  const first = acquire().state;
  const successor = transitionFrozenFence(first, req('acquire', {
    serverNowMs: 12_000, expectedEpoch: 1, ownerRunAttempt: ownerB,
  })).state;
  for (const operation of ['renew','retire']) {
    const r = transitionFrozenFence(successor, req(operation, {
      serverNowMs: 12_500, expectedEpoch: 1,
      verifiedEvidence: { ...full, sameBrokerSession: true, ownerStillAuthenticated: true },
    }));
    assert.equal(r.status, 'stale_fencing_epoch');
    assert.strictEqual(r.state, successor);
  }
});
test('same-epoch wrong account and wrong holder are rejected', () => {
  const first = acquire().state;
  const wrongAccount = transitionFrozenFence(first, req('renew', {
    expectedEpoch: 1, serverNowMs: 1_500, accountDigest: otherAccount,
    verifiedEvidence: { sameBrokerSession: true, ownerStillAuthenticated: true },
  }));
  assert.equal(wrongAccount.status, 'account_scope_mismatch');
  const wrongHolder = transitionFrozenFence(first, req('renew', {
    expectedEpoch: 1, serverNowMs: 1_500, ownerRunAttempt: ownerB,
    verifiedEvidence: { sameBrokerSession: true, ownerStillAuthenticated: true },
  }));
  assert.equal(wrongHolder.status, 'not_current_unexpired_holder');
});
test('renew requires live session evidence and cannot revive expired owner', () => {
  const first = acquire().state;
  assert.equal(transitionFrozenFence(first, req('renew', {
    expectedEpoch: 1, serverNowMs: 1_500, verifiedEvidence: {},
  })).status, 'renew_evidence_incomplete');
  assert.equal(transitionFrozenFence(first, req('renew', {
    expectedEpoch: 1, serverNowMs: 11_000,
    verifiedEvidence: { sameBrokerSession: true, ownerStillAuthenticated: true },
  })).status, 'not_current_unexpired_holder');
  const good = transitionFrozenFence(first, req('renew', {
    expectedEpoch: 1, serverNowMs: 1_500,
    verifiedEvidence: { sameBrokerSession: true, ownerStillAuthenticated: true },
  }));
  assert.equal(good.ok, true);
  assert.equal(good.state.epoch, 1);
  assert.equal(good.state.expiresAtMs, 11_500);
});
test('retirement revokes holder with new epoch and blocks stale retry', () => {
  const first = acquire().state;
  assert.equal(transitionFrozenFence(first, req('retire', {
    expectedEpoch: 1, serverNowMs: 2_000, verifiedEvidence: {},
  })).status, 'retire_session_not_excluded');
  const retired = transitionFrozenFence(first, req('retire', {
    expectedEpoch: 1, serverNowMs: 2_000,
  }));
  assert.equal(retired.ok, true);
  assert.equal(retired.state.epoch, 2);
  assert.equal(retired.state.holder, null);
  assert.equal(transitionFrozenFence(retired.state, req('renew', {
    expectedEpoch: 1, serverNowMs: 2_500,
  })).status, 'stale_fencing_epoch');
});
test('input corruption, clock regression, invalid TTL, forged run id deny closed', () => {
  assert.equal(acquire({ ttlMs: 30_001 }).status, 'ttl_invalid');
  assert.equal(acquire({ ownerRunAttempt: 'not-a-run' }).status, 'owner_identity_invalid');
  assert.equal(acquire({ accountDigest: 'live-account-number' }).status, 'account_scope_mismatch');
  const first = acquire().state;
  assert.equal(transitionFrozenFence(first, req('renew', {
    expectedEpoch: 1, serverNowMs: 999,
  })).status, 'untrusted_or_regressing_clock');
  assert.equal(transitionFrozenFence({ ...first, epoch: -1 }, req('renew')).status, 'invalid_persisted_state');
});
