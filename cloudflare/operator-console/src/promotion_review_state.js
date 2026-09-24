const CANDIDATE_SCHEMA = 'mmibkr.promotion_candidate_snapshot.v1';
const DECISION_SCHEMA = 'mmibkr.promotion_review_decision.v1';
const STATE_SCHEMA = 'mmibkr.promotion_review_state.v1';
const MAX_CANDIDATES = 200;
const MAX_DECISIONS = 500;
const MAX_NOTE_CHARS = 4000;
const MAX_APPROVAL_AGE_MS = 30 * 60 * 1000;
const MAX_FUTURE_SKEW_MS = 2 * 60 * 1000;

const STAGES = Object.freeze(['RESEARCH', 'ARENA', 'BROKER_PAPER', 'LIVE_ELIGIBLE']);
const NEXT_STAGE = Object.freeze({ RESEARCH: 'ARENA', ARENA: 'BROKER_PAPER', BROKER_PAPER: 'LIVE_ELIGIBLE' });
const ACTIONS = new Set(['APPROVE', 'DENY', 'FEEDBACK']);
const KINDS = new Set(['strategy', 'model', 'hybrid']);

function object(value, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(label + '_object_required');
  return value;
}
function text(value, label, max = 512) {
  const out = String(value || '').trim();
  if (!out || out.length > max) throw new Error(label + '_invalid');
  return out;
}
function stage(value, label = 'stage') {
  const out = text(value, label, 64).toUpperCase();
  if (!STAGES.includes(out)) throw new Error(label + '_unsupported');
  return out;
}
function finite(value) {
  if (value === null || value === undefined || value === '') return null;
  const number = Number(value);
  if (!Number.isFinite(number)) throw new Error('metric_nonfinite');
  return number;
}
function safeObject(value) { return value && typeof value === 'object' && !Array.isArray(value) ? value : {}; }
function utcTimestamp(value, label) {
  const raw = text(value, label, 128);
  if (!/(?:Z|[+-]00:00)$/i.test(raw)) throw new Error(label + '_utc_required');
  const parsed = Date.parse(raw);
  if (!Number.isFinite(parsed)) throw new Error(label + '_invalid');
  return { raw, parsed };
}

function canonicalCandidate(raw) {
  object(raw, 'candidate');
  const candidateId = text(raw.candidate_id, 'candidate_id', 512);
  const candidateKind = text(raw.candidate_kind, 'candidate_kind', 32).toLowerCase();
  if (!KINDS.has(candidateKind)) throw new Error('candidate_kind_unsupported');
  const candidateDigest = text(raw.candidate_digest, 'candidate_digest', 256).toLowerCase();
  const evidenceDigest = text(raw.evidence_digest, 'evidence_digest', 256).toLowerCase();
  const currentStage = stage(raw.current_stage, 'current_stage');
  const canonicalNext = NEXT_STAGE[currentStage] || null;
  const proposedStageRaw = String(raw.proposed_stage || '').trim().toUpperCase();
  const proposedStage = proposedStageRaw || canonicalNext;
  if (proposedStage !== canonicalNext) throw new Error('proposed_stage_mismatch');
  const normalizedMetrics = {};
  for (const [key, value] of Object.entries(safeObject(raw.metrics))) {
    normalizedMetrics[String(key)] = value === null || typeof value === 'string' || typeof value === 'boolean' ? value : finite(value);
  }
  const reasons = Array.isArray(raw.reasons) ? raw.reasons.slice(0, 30).map((value) => text(value, 'reason', 1000)) : [];
  const warnings = Array.isArray(raw.warnings) ? raw.warnings.slice(0, 30).map((value) => text(value, 'warning', 1000)) : [];
  return {
    candidate_id: candidateId, candidate_kind: candidateKind, candidate_digest: candidateDigest,
    evidence_digest: evidenceDigest, source: text(raw.source || 'UNKNOWN', 'source', 128).toUpperCase(),
    label: text(raw.label || candidateId, 'label', 512),
    symbol: raw.symbol == null ? null : text(raw.symbol, 'symbol', 64).toUpperCase(),
    universe: raw.universe == null ? null : text(raw.universe, 'universe', 256),
    timeframe: raw.timeframe == null ? null : text(raw.timeframe, 'timeframe', 64),
    current_stage: currentStage, proposed_stage: proposedStage, review_ready: raw.review_ready === true,
    sample: safeObject(raw.sample), metrics: normalizedMetrics, risk: safeObject(raw.risk),
    execution: safeObject(raw.execution), health: safeObject(raw.health), provenance: safeObject(raw.provenance), reasons, warnings,
  };
}

export function validatePromotionCandidateSnapshot(node) {
  object(node, 'promotion_candidate_snapshot');
  if (node.schema !== CANDIDATE_SCHEMA) throw new Error('promotion_candidate_schema_rejected');
  if (!Array.isArray(node.candidates)) throw new Error('promotion_candidates_array_required');
  if (node.candidates.length > MAX_CANDIDATES) throw new Error('promotion_candidates_too_many');
  const safety = safeObject(node.safety);
  if (safety.broker_mutation_authority !== false || safety.live_execution_allowed !== false || safety.selected_runtime_write !== false) {
    throw new Error('promotion_candidate_authority_rejected');
  }
  const generated = utcTimestamp(node.generated_at_utc, 'generated_at_utc').raw;
  const candidates = node.candidates.map(canonicalCandidate);
  const ids = new Set(candidates.map((row) => row.candidate_id));
  if (ids.size !== candidates.length) throw new Error('promotion_candidate_id_duplicate');
  return {
    schema: CANDIDATE_SCHEMA, generated_at_utc: generated, candidates,
    policy: { research_to_arena_automatic_allowed: true, initial_calibration_broker_paper_review_required: true, live_enable_manual_required: true },
    safety: { broker_mutation_authority: false, live_execution_allowed: false, selected_runtime_write: false },
  };
}

async function sha256Hex(value) {
  const bytes = new TextEncoder().encode(String(value || ''));
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
  return Array.from(digest).map((value) => value.toString(16).padStart(2, '0')).join('');
}
async function operatorFingerprint(operator) {
  const email = String(operator?.email || '').trim().toLowerCase();
  const sub = String(operator?.sub || '').trim();
  if (!email && !sub) throw new Error('operator_identity_required');
  return sha256Hex(email + '\n' + sub);
}
function decisionCanonicalBody(body, candidate) {
  object(body, 'promotion_decision');
  const action = text(body.action, 'action', 32).toUpperCase();
  if (!ACTIONS.has(action)) throw new Error('promotion_action_unsupported');
  const note = String(body.operator_note || '').trim();
  if (note.length > MAX_NOTE_CHARS) throw new Error('operator_note_too_long');
  if ((action === 'DENY' || action === 'FEEDBACK') && !note) throw new Error('operator_note_required');
  const currentStage = stage(body.current_stage, 'current_stage');
  if (currentStage !== candidate.current_stage) throw new Error('current_stage_stale');
  let targetStage = currentStage;
  if (action === 'APPROVE') {
    if (candidate.review_ready !== true) throw new Error('candidate_not_review_ready');
    const canonicalTarget = NEXT_STAGE[currentStage] || null;
    if (!canonicalTarget) throw new Error('live_enable_is_separate_manual_authority');
    const requested = String(body.target_stage || '').trim().toUpperCase();
    if (requested && requested !== canonicalTarget) throw new Error('target_stage_mismatch');
    if (candidate.proposed_stage !== canonicalTarget) throw new Error('candidate_proposed_stage_invalid');
    targetStage = canonicalTarget;
  }
  return { action, current_stage: currentStage, target_stage: targetStage, operator_note: note };
}

export async function storePromotionCandidates(storage, snapshot, publisher = {}) {
  const normalized = validatePromotionCandidateSnapshot(snapshot);
  const record = {
    schema: 'mmibkr.promotion_candidate_state.v1', stored_at_utc: new Date().toISOString(), snapshot: normalized,
    publisher: { repository: publisher.repository || null, workflow_ref: publisher.workflow_ref || null, run_id: publisher.run_id || null },
  };
  await storage.put('promotion:candidates', record);
  const readback = await storage.get('promotion:candidates');
  if (!readback || readback.stored_at_utc !== record.stored_at_utc || readback.snapshot?.schema !== CANDIDATE_SCHEMA || readback.snapshot?.candidates?.length !== normalized.candidates.length) {
    throw new Error('promotion_candidate_readback_failed');
  }
  return { ok: true, schema: 'mmibkr.promotion_candidate_publish_receipt.v1', stored_at_utc: record.stored_at_utc, candidate_count: normalized.candidates.length, durable_readback_verified: true, broker_mutation_authority: false, live_execution_allowed: false };
}

async function readDecisionIndex(storage) {
  const value = await storage.get('promotion:decision-index');
  return Array.isArray(value) ? value.filter((item) => typeof item === 'string').slice(-MAX_DECISIONS) : [];
}
async function decisionRows(storage) {
  const ids = await readDecisionIndex(storage);
  if (!ids.length) return [];
  const keys = ids.map((id) => 'promotion:decision:' + id);
  const found = await storage.get(keys);
  return ids.map((id) => found.get('promotion:decision:' + id)).filter(Boolean);
}
export async function readPromotionState(storage) {
  const candidateRecord = await storage.get('promotion:candidates');
  const candidates = candidateRecord?.snapshot?.schema === CANDIDATE_SCHEMA ? candidateRecord.snapshot.candidates : [];
  const decisions = await decisionRows(storage);
  const latestByCandidate = {};
  for (const row of decisions) latestByCandidate[row.candidate_id] = row;
  return {
    ok: true, schema: STATE_SCHEMA,
    candidate_snapshot_generated_at_utc: candidateRecord?.snapshot?.generated_at_utc || null,
    candidate_snapshot_stored_at_utc: candidateRecord?.stored_at_utc || null,
    candidates, decisions, latest_by_candidate: latestByCandidate,
    policy: { research_to_arena_automatic_allowed: true, initial_calibration_broker_paper_review_required: true, live_enable_manual_required: true },
    authority: { decision_records_only: true, broker_mutation_authority: false, selected_runtime_write: false, live_execution_allowed: false },
  };
}
function candidateForDecision(state, body) {
  const candidateId = text(body.candidate_id, 'candidate_id', 512);
  const digest = text(body.candidate_digest, 'candidate_digest', 256).toLowerCase();
  const evidenceDigest = text(body.evidence_digest, 'evidence_digest', 256).toLowerCase();
  const candidate = state.candidates.find((row) => row.candidate_id === candidateId);
  if (!candidate) throw new Error('candidate_not_found');
  if (candidate.candidate_digest !== digest) throw new Error('candidate_digest_stale');
  if (candidate.evidence_digest !== evidenceDigest) throw new Error('candidate_evidence_stale');
  if (body.candidate_kind != null && text(body.candidate_kind, 'candidate_kind', 32).toLowerCase() !== candidate.candidate_kind) throw new Error('candidate_kind_stale');
  if (candidate.candidate_kind === 'strategy') {
    if (text(body.symbol, 'symbol', 64).toUpperCase() !== candidate.symbol) throw new Error('candidate_symbol_stale');
    if (text(body.timeframe, 'timeframe', 64) !== candidate.timeframe) throw new Error('candidate_timeframe_stale');
  }
  return candidate;
}
function admitApprovalSnapshot(state, body, nowMs = Date.now()) {
  const submitted = utcTimestamp(body.candidate_snapshot_generated_at_utc, 'candidate_snapshot_generated_at_utc');
  const current = utcTimestamp(state.candidate_snapshot_generated_at_utc, 'current_candidate_snapshot_generated_at_utc');
  if (submitted.raw !== current.raw) throw new Error('candidate_snapshot_superseded');
  const ageMs = nowMs - submitted.parsed;
  if (ageMs > MAX_APPROVAL_AGE_MS) throw new Error('candidate_snapshot_stale');
  if (ageMs < -MAX_FUTURE_SKEW_MS) throw new Error('candidate_snapshot_future');
  return submitted.raw;
}

export async function recordPromotionDecision(storage, body, operator) {
  const state = await readPromotionState(storage);
  const candidate = candidateForDecision(state, body);
  const canonical = decisionCanonicalBody(body, candidate);
  const snapshotIdentity = canonical.action === 'APPROVE'
    ? admitApprovalSnapshot(state, body)
    : (body.candidate_snapshot_generated_at_utc ? utcTimestamp(body.candidate_snapshot_generated_at_utc, 'candidate_snapshot_generated_at_utc').raw : state.candidate_snapshot_generated_at_utc);
  const requestId = text(body.request_id, 'request_id', 512);
  const operatorHash = await operatorFingerprint(operator);
  const idMaterial = JSON.stringify({ request_id: requestId, candidate_id: candidate.candidate_id, candidate_digest: candidate.candidate_digest, evidence_digest: candidate.evidence_digest, candidate_snapshot_generated_at_utc: snapshotIdentity, operator_hash: operatorHash, ...canonical });
  const decisionId = await sha256Hex(idMaterial);
  const existing = await storage.get('promotion:decision:' + decisionId);
  if (existing) return { ...existing, ok: true, idempotent_replay: true };
  for (const row of state.decisions) {
    if (row.request_id === requestId && row.decision_id !== decisionId) throw new Error('request_id_conflict');
    if (canonical.action === 'APPROVE' && row.candidate_id === candidate.candidate_id && row.candidate_digest === candidate.candidate_digest && row.action === 'APPROVE' && row.current_stage === canonical.current_stage && row.target_stage === canonical.target_stage) {
      throw new Error('stage_already_approved_pending_consumer');
    }
  }
  const receipt = {
    ok: true, schema: DECISION_SCHEMA, decision_id: decisionId, request_id: requestId, created_at_utc: new Date().toISOString(),
    candidate_id: candidate.candidate_id, candidate_kind: candidate.candidate_kind, candidate_digest: candidate.candidate_digest,
    evidence_digest: candidate.evidence_digest, candidate_snapshot_generated_at_utc: snapshotIdentity,
    symbol: candidate.symbol, timeframe: candidate.timeframe, source: candidate.source, ...canonical,
    disposition: canonical.action === 'APPROVE' ? 'APPROVED_FOR_' + canonical.target_stage : canonical.action === 'DENY' ? 'DENIED' : 'FEEDBACK_RECORDED',
    operator: { identity_sha256: operatorHash, authenticated: true },
    authority: { decision_recorded: true, promotion_consumer_required: canonical.action === 'APPROVE', broker_mutation_authority: false, selected_runtime_write: false, live_execution_allowed: false },
  };
  await storage.put('promotion:decision:' + decisionId, receipt);
  const index = await readDecisionIndex(storage);
  index.push(decisionId);
  await storage.put('promotion:decision-index', Array.from(new Set(index)).slice(-MAX_DECISIONS));
  const readback = await storage.get('promotion:decision:' + decisionId);
  if (!readback || readback.decision_id !== decisionId || readback.candidate_snapshot_generated_at_utc !== snapshotIdentity) throw new Error('promotion_decision_readback_failed');
  return receipt;
}

export function machinePromotionProjection(state) {
  object(state, 'promotion_state');
  return {
    ok: true, schema: 'mmibkr.promotion_review_machine_read.v1',
    candidate_snapshot_generated_at_utc: state.candidate_snapshot_generated_at_utc || null,
    candidates: Array.isArray(state.candidates) ? state.candidates : [],
    decisions: Array.isArray(state.decisions) ? state.decisions.map((row) => ({ ...row, operator: row.operator?.identity_sha256 ? { identity_sha256: row.operator.identity_sha256, authenticated: true } : { authenticated: false } })) : [],
    policy: state.policy || {}, broker_mutation_authority: false, selected_runtime_write: false, live_execution_allowed: false,
  };
}
export const promotionReviewContract = Object.freeze({ candidate_schema: CANDIDATE_SCHEMA, decision_schema: DECISION_SCHEMA, state_schema: STATE_SCHEMA, stages: STAGES, next_stage: NEXT_STAGE, approval_max_age_ms: MAX_APPROVAL_AGE_MS, approval_max_future_skew_ms: MAX_FUTURE_SKEW_MS });
