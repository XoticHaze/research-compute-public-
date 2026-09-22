import assert from 'node:assert/strict'
import {
  machinePromotionProjection,
  readPromotionState,
  recordPromotionDecision,
  storePromotionCandidates,
  validatePromotionCandidateSnapshot,
} from '../cloudflare/operator-console/src/promotion_review_state.js'

class MemoryStorage {
  constructor() { this.values = new Map() }
  async put(key, value) { this.values.set(key, structuredClone(value)) }
  async get(key) {
    if (Array.isArray(key)) {
      return new Map(key.filter((item) => this.values.has(item)).map((item) => [item, structuredClone(this.values.get(item))]))
    }
    return this.values.has(key) ? structuredClone(this.values.get(key)) : undefined
  }
}

const candidate = {
  candidate_id: 'autotuner:mnq-crw-w96-entry-2.52:0123456789abcdef',
  candidate_kind: 'strategy',
  candidate_digest: '0123456789abcdef0123456789abcdef',
  evidence_digest: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
  source: 'AUTOTUNER',
  label: 'MNQ CRW W96 entry -2.52',
  symbol: 'MNQ',
  timeframe: '12Min',
  current_stage: 'RESEARCH',
  proposed_stage: 'ARENA',
  review_ready: true,
  sample: { trades: 22, prospective_start_utc: '2026-09-20T00:00:00Z' },
  metrics: { net_pnl: 900, excess_return: 0.03, max_drawdown: -0.08 },
  risk: { dca_evidence: 'existing_proof_indexed' },
  execution: {},
  health: { status: 'READY' },
  provenance: { strategy_spec_digest: '0123456789abcdef0123456789abcdef' },
  reasons: ['Decision-complete comparison evidence is present.'],
  warnings: [],
}

const snapshot = {
  schema: 'mmibkr.promotion_candidate_snapshot.v1',
  generated_at_utc: '2026-09-22T19:00:00Z',
  candidates: [candidate],
  safety: {
    broker_mutation_authority: false,
    live_execution_allowed: false,
    selected_runtime_write: false,
  },
}

const normalized = validatePromotionCandidateSnapshot(snapshot)
assert.equal(normalized.candidates.length, 1)
assert.equal(normalized.candidates[0].proposed_stage, 'ARENA')
assert.equal(normalized.policy.live_enable_manual_required, true)

const storage = new MemoryStorage()
const published = await storePromotionCandidates(storage, snapshot, {
  repository: 'XoticHaze/research-compute-public-',
  workflow_ref: 'publisher',
  run_id: '1234',
})
assert.equal(published.durable_readback_verified, true)

const state = await readPromotionState(storage)
assert.equal(state.candidates[0].candidate_id, candidate.candidate_id)
assert.equal(state.decisions.length, 0)

const operator = { email: 'operator@example.com', sub: 'operator-subject' }
const approved = await recordPromotionDecision(storage, {
  action: 'APPROVE',
  candidate_id: candidate.candidate_id,
  candidate_digest: candidate.candidate_digest,
  evidence_digest: candidate.evidence_digest,
  current_stage: 'RESEARCH',
  target_stage: 'ARENA',
  request_id: 'approve-1',
  operator_note: '',
}, operator)
assert.equal(approved.disposition, 'APPROVED_FOR_ARENA')
assert.equal(approved.authority.broker_mutation_authority, false)
assert.equal(approved.authority.live_execution_allowed, false)
assert.equal(approved.operator.authenticated, true)
assert.ok(/^[0-9a-f]{64}$/.test(approved.operator.identity_sha256))
assert.equal(JSON.stringify(approved).includes('operator@example.com'), false)

const replay = await recordPromotionDecision(storage, {
  action: 'APPROVE',
  candidate_id: candidate.candidate_id,
  candidate_digest: candidate.candidate_digest,
  evidence_digest: candidate.evidence_digest,
  current_stage: 'RESEARCH',
  target_stage: 'ARENA',
  request_id: 'approve-1',
  operator_note: '',
}, operator)
assert.equal(replay.idempotent_replay, true)

await assert.rejects(
  () => recordPromotionDecision(storage, {
    action: 'APPROVE',
    candidate_id: candidate.candidate_id,
    candidate_digest: candidate.candidate_digest,
    evidence_digest: candidate.evidence_digest,
    current_stage: 'RESEARCH',
    target_stage: 'ARENA',
    request_id: 'approve-2',
  }, operator),
  /stage_already_approved_pending_consumer/,
)

await assert.rejects(
  () => recordPromotionDecision(storage, {
    action: 'DENY',
    candidate_id: candidate.candidate_id,
    candidate_digest: candidate.candidate_digest,
    evidence_digest: candidate.evidence_digest,
    current_stage: 'RESEARCH',
    request_id: 'deny-1',
  }, operator),
  /operator_note_required/,
)

const liveSnapshot = structuredClone(snapshot)
liveSnapshot.candidates[0].candidate_id = 'paper-live-eligible'
liveSnapshot.candidates[0].current_stage = 'LIVE_ELIGIBLE'
liveSnapshot.candidates[0].proposed_stage = null
liveSnapshot.candidates[0].candidate_digest = 'bbbbbbbbbbbbbbbb'
liveSnapshot.candidates[0].evidence_digest = 'cccccccccccccccc'
await storePromotionCandidates(storage, liveSnapshot, {})
await assert.rejects(
  () => recordPromotionDecision(storage, {
    action: 'APPROVE',
    candidate_id: 'paper-live-eligible',
    candidate_digest: 'bbbbbbbbbbbbbbbb',
    evidence_digest: 'cccccccccccccccc',
    current_stage: 'LIVE_ELIGIBLE',
    target_stage: 'LIVE',
    request_id: 'live-1',
  }, operator),
  /live_enable_is_separate_manual_authority/,
)

const projected = machinePromotionProjection(await readPromotionState(storage))
assert.equal(projected.broker_mutation_authority, false)
assert.equal(projected.live_execution_allowed, false)
assert.equal(JSON.stringify(projected).includes('operator@example.com'), false)

console.log('MMIBKR_PROMOTION_REVIEW_STATE_CONTRACT=PASS')
