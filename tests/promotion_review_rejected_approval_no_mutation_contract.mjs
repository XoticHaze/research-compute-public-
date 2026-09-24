import assert from 'node:assert/strict'
import {
  readPromotionState,
  recordPromotionDecision,
  storePromotionCandidates,
} from '../cloudflare/operator-console/src/promotion_review_state.js'

class MemoryStorage {
  constructor() { this.values = new Map(); this.puts = [] }
  async put(key, value) {
    this.puts.push(key)
    this.values.set(key, structuredClone(value))
  }
  async get(key) {
    if (Array.isArray(key)) {
      return new Map(key.filter((item) => this.values.has(item)).map((item) => [item, structuredClone(this.values.get(item))]))
    }
    return this.values.has(key) ? structuredClone(this.values.get(key)) : undefined
  }
}

const storage = new MemoryStorage()
const generatedAt = new Date().toISOString()
const candidate = {
  candidate_id: 'strategy:mnq-crw:no-mutation-proof',
  candidate_kind: 'strategy',
  candidate_digest: '0123456789abcdef0123456789abcdef',
  evidence_digest: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
  source: 'AUTOTUNER',
  label: 'MNQ CRW no-mutation proof',
  symbol: 'MNQ',
  timeframe: '12Min',
  current_stage: 'RESEARCH',
  proposed_stage: 'ARENA',
  review_ready: true,
  sample: {}, metrics: {}, risk: {}, execution: {}, health: {}, provenance: {}, reasons: [], warnings: [],
}
await storePromotionCandidates(storage, {
  schema: 'mmibkr.promotion_candidate_snapshot.v1',
  generated_at_utc: generatedAt,
  candidates: [candidate],
  safety: { broker_mutation_authority: false, live_execution_allowed: false, selected_runtime_write: false },
}, {})

const before = await readPromotionState(storage)
const decisionPutsBefore = storage.puts.filter((key) => key.startsWith('promotion:decision')).length
const rejected = {
  action: 'APPROVE',
  candidate_id: candidate.candidate_id,
  candidate_kind: candidate.candidate_kind,
  candidate_digest: candidate.candidate_digest,
  evidence_digest: candidate.evidence_digest,
  candidate_snapshot_generated_at_utc: '2026-09-22T00:00:00Z',
  symbol: candidate.symbol,
  timeframe: candidate.timeframe,
  current_stage: 'RESEARCH',
  target_stage: 'ARENA',
  request_id: 'superseded-direct-request',
  operator_note: '',
}
await assert.rejects(
  () => recordPromotionDecision(storage, rejected, { email: 'operator@example.com', sub: 'operator-subject' }),
  /candidate_snapshot_superseded/,
)
const after = await readPromotionState(storage)
const decisionPutsAfter = storage.puts.filter((key) => key.startsWith('promotion:decision')).length
assert.equal(before.decisions.length, 0)
assert.equal(after.decisions.length, 0)
assert.deepEqual(after.latest_by_candidate, {})
assert.equal(decisionPutsAfter, decisionPutsBefore)
assert.equal(storage.values.has('promotion:decision-index'), false)
console.log('MMIBKR_PROMOTION_REJECTED_APPROVAL_NO_MUTATION_CONTRACT=PASS')
