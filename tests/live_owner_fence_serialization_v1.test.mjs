// Brokerless contract: serializing the reducer is a separately required
// system property; a correct pure transition function is NOT itself a lease.
// Synthetic proof booleans below are test fixtures, not attestations.
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  initialFrozenFence, transitionFrozenFence,
} from '../cloudflare/fleet-authority/src/live_owner_fence_transition_v1.mjs';

const account = 'a'.repeat(64);
const owner = (id) => `${40000000000 + id}:1`;
const evidence = Object.freeze({
  operatorAttested: true, predecessorGatewayTerminated: true,
  predecessorWriterQuiesced: true, brokerJournalReconciled: true,
  allBrokerWriteSessionsExcluded: true,
});
const request = (id, overrides = {}) => ({
  operation: 'acquire', accountDigest: account, ownerRunAttempt: owner(id),
  serverNowMs: 1_000, expectedEpoch: 0, ttlMs: 30_000,
  verifiedEvidence: evidence, ...overrides,
});

// Fake store intentionally exists only in tests: no Cloudflare binding,
// production endpoint, credentials, broker session or live authorization.
class SerialTestStore {
  constructor() {
    this.state = initialFrozenFence();
    this.tail = Promise.resolve();
    this.failNextCommit = false;
  }
  async submit(next) {
    let unlock;
    const nextTurn = new Promise((resolve) => { unlock = resolve; });
    const prior = this.tail;
    this.tail = nextTurn;
    await prior;
    try {
      const priorState = this.state;
      const proposal = transitionFrozenFence(priorState, next);
      if (proposal.ok) {
        if (this.failNextCommit) {
          this.failNextCommit = false;
          return { ok: false, status: 'synthetic_commit_io_failed', state: priorState };
        }
        // Model the only admissible success boundary: commit, then reply.
        this.state = structuredClone(proposal.state);
      }
      return proposal;
    } finally {
      unlock();
    }
  }
}

test('two concurrent GitHub/host candidates: one serialized winner', async () => {
  const s = new SerialTestStore();
  const [a, b] = await Promise.all([s.submit(request(1)), s.submit(request(2))]);
  assert.equal([a,b].filter(x=>x.ok).length, 1);
  assert.equal([a,b].filter(x=>x.status === 'stale_fencing_epoch').length, 1);
  assert.equal(s.state.epoch, 1);
  assert.equal(s.state.holder, owner(1));
});
test('32 same-epoch contenders never create a second serialized writer', async () => {
  const s = new SerialTestStore();
  const attempts = await Promise.all(
    Array.from({length:32}, (_,i)=>s.submit(request(i+1)))
  );
  assert.equal(attempts.filter(a=>a.ok).length, 1);
  assert.equal(attempts.filter(a=>!a.ok).length, 31);
  assert.equal(s.state.epoch, 1);
});
test('an expired still-connected predecessor remains a takeover blocker', async () => {
  const s = new SerialTestStore();
  assert.equal((await s.submit(request(1))).ok, true);
  const second = await s.submit(request(2, {
    expectedEpoch:1, serverNowMs:31_000,
    verifiedEvidence:{...evidence,predecessorWriterQuiesced:false}
  }));
  assert.equal(second.status,'takeover_evidence_incomplete');
  assert.equal(s.state.epoch,1);
  const third = await s.submit(request(2, {
    expectedEpoch:1, serverNowMs:31_000, verifiedEvidence:evidence
  }));
  assert.equal(third.ok,true);
  assert.equal(s.state.epoch,2);
  const stale = await s.submit(request(1, {
    operation:'renew', expectedEpoch:1, serverNowMs:31_001,
    verifiedEvidence:{sameBrokerSession:true,ownerStillAuthenticated:true}
  }));
  assert.equal(stale.status,'stale_fencing_epoch');
});
test('failed durable write cannot leak a successful acquisition reply', async () => {
  const s = new SerialTestStore();
  s.failNextCommit = true;
  const lost = await s.submit(request(1));
  assert.equal(lost.ok,false);
  assert.equal(lost.status,'synthetic_commit_io_failed');
  assert.equal(s.state.epoch,0);
  const retry = await s.submit(request(2));
  assert.equal(retry.ok,true);
  assert.equal(s.state.epoch,1);
  assert.equal(s.state.holder,owner(2));
});
test('isolated reducer invocations can both yield candidate success: not a real lease', () => {
  const initial = initialFrozenFence();
  // This intentionally illustrates the production race a shared serialized
  // authority must prevent. NEVER use this reducer alone for broker mutations.
  const a = transitionFrozenFence(initial,request(1));
  const b = transitionFrozenFence(initial,request(2));
  assert.equal(a.ok,true);
  assert.equal(b.ok,true);
  assert.notEqual(a.state.holder,b.state.holder);
});
test('raw synthetic true booleans are not a trust signature or broker permission', () => {
  const candidate = transitionFrozenFence(initialFrozenFence(),request(1));
  assert.equal(candidate.ok,true);
  assert.match(candidate.status,/not_broker_authorized/);
  assert.equal(Object.hasOwn(candidate,'live_submit_authorized'),false);
  assert.equal(Object.hasOwn(candidate.state,'write_capability'),false);
});
