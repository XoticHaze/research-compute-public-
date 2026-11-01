// Dedicated public Access-locked bot-origin observation contract.
// A trusted pinned OIDC publisher must independently verify the PRIVATE Git
// commit/blob and root receipt before calling ingest. This file never talks
// to the Pi, Gateway, broker, account reader, or mutable owner request slot.
const NOW_SKEW_MS = 60000;
const MAX_AGE_MS = 420000;
const ids = new Set(['MNQ', 'AMAT', 'APH']);
const flags = new Set(['ENABLE_LIVE_TRADING', 'MM_ENABLE_LIVE_TRADING']);
const keys = (x, expected) => x && typeof x === 'object' && !Array.isArray(x)
  && Object.keys(x).length === expected.size && Object.keys(x).every(k => expected.has(k));
const hex40 = x => typeof x === 'string' && /^[0-9a-f]{40}$/.test(x);
const hex64 = x => typeof x === 'string' && /^[0-9a-f]{64}$/.test(x);
const utc = x => typeof x === 'string' && x.length <= 48
  && /(Z|\+00:00)$/.test(x) && Number.isFinite(Date.parse(x)) ? Date.parse(x) : NaN;
const ek = new Set(['schema','node_id','source_repo','source_ref','source_path','result_commit_sha','result_blob_sha','receipt']);
const rootEnvelopeKeys = new Set(['schema','node_id','source_repo','source_ref','source_path','result_commit_sha','result_blob_sha','record']);
const rootRecordKeys = new Set(['schema','node_id','observation_id','observed_at','snapshot_sha256','snapshot','producer','read_only','broker_mutation_attempted','gateway_mutation_attempted']);
const rootProducer = 'root_approved_fixed_pi_bot_inspection';
const rk = new Set(['schema','node_id','request_id','action','source_sha','image_digest','request_sha256','status','message','started_at','finished_at','broker_mutation_attempted','gateway_restart_attempted','bot_started','replay_allowed','live_status']);
const ok = new Set(['schema','node_id','status','live_switches_enabled','bot_running','gateway_running','gateway_network_namespace_matched','single_canonical_main','global_live_flags','selected_live_policies','stock_canary_enabled','private_network_attested_by_launcher','legacy_backtest_disabled','restart_persistent','gateway_readonly_api_configuration','broker_submission_verified','broker_mutation_attempted','gateway_mutation_attempted','read_only']);
const requiredIfEnabled = ['bot_running','gateway_running','gateway_network_namespace_matched','single_canonical_main','stock_canary_enabled','private_network_attested_by_launcher','legacy_backtest_disabled','restart_persistent'];
function reject() { throw new Error('pi_bot_observation_rejected') }
export function validatePiBotLiveEnvelope(input, now = Date.now()) {
  if (input?.schema === 'mmibkr.pi_bot_live_observation_envelope.v2') {
    if (!keys(input,rootEnvelopeKeys) || input.node_id!=='cc-pi4'
        || input.source_repo!=='XoticHaze/CommandCenter-gate-control'
        || input.source_ref!=='pi-node-outbox'
        || !hex40(input.result_commit_sha) || !hex40(input.result_blob_sha)
        || !keys(input.record,rootRecordKeys)) reject();
    const r=input.record, o=r.snapshot;
    if (r.schema!=='commandcenter.pi.bot_live_observation_outbox.v1'
        || r.node_id!=='cc-pi4' || !/^pibotobs-[0-9]{14}-[0-9a-f]{16}$/.test(r.observation_id)
        || input.source_path!=='pi-node/bot-observations/'+r.observation_id+'.json'
        || r.producer!==rootProducer
        || r.read_only!==true || r.broker_mutation_attempted!==false
        || r.gateway_mutation_attempted!==false || !hex64(r.snapshot_sha256)
        || !keys(o,ok) || o.schema!=='commandcenter.pi.bot_live_status.v1'
        || o.node_id!=='cc-pi4' || o.read_only!==true
        || o.broker_submission_verified!==false || o.broker_mutation_attempted!==false
        || o.gateway_mutation_attempted!==false
        || !['LIVE_SWITCHES_ENABLED','LIVE_NOT_CONFIRMED'].includes(o.status)
        || !keys(o.global_live_flags,flags) || !keys(o.selected_live_policies,ids)
        || !Object.values(o.global_live_flags).every(x=>typeof x==='boolean')
        || !Object.values(o.selected_live_policies).every(x=>typeof x==='boolean')
        || !requiredIfEnabled.concat(['live_switches_enabled']).every(k=>typeof o[k]==='boolean')
        || !['yes','no','unknown'].includes(o.gateway_readonly_api_configuration)) reject();
    const enabled = requiredIfEnabled.every(k=>o[k]===true)
      && Object.values(o.global_live_flags).every(Boolean)
      && Object.values(o.selected_live_policies).every(Boolean);
    // Root also checks a private owner-mode prerequisite not in this sanitized view.
    // Only positive root readiness requires all exposed flags; a signed negative
    // may have every exposed flag true without authorizing any live claim.
    if ((o.live_switches_enabled && !enabled)
        || (o.status==='LIVE_SWITCHES_ENABLED')!==o.live_switches_enabled) reject();
    const t=utc(r.observed_at);
    if (!Number.isFinite(t) || t>now+NOW_SKEW_MS || now-t>MAX_AGE_MS) reject();
    return {receipt:null,observation:o,observedAt:r.observed_at,observedAtMs:t,
      replayId:'root:'+r.observation_id,resultCommitSha:input.result_commit_sha};
  }

  if (!keys(input,ek) || input.schema !== 'mmibkr.pi_bot_live_observation_envelope.v1'
      || input.node_id !== 'cc-pi4' || input.source_repo !== 'XoticHaze/CommandCenter-gate-control'
      || input.source_ref !== 'pi-node-outbox'
      || !hex40(input.result_commit_sha) || !hex40(input.result_blob_sha)
      || !keys(input.receipt,rk)) reject();
  const receipt=input.receipt, status=receipt.live_status;
  if (receipt.schema !== 'commandcenter.pi.bot_release_result.v1'
      || receipt.node_id !== 'cc-pi4'
      || receipt.action !== 'pi.bot.live_status'
      || typeof receipt.request_id !== 'string'
      || !/^[A-Za-z0-9._:-]{6,100}$/.test(receipt.request_id)
      || input.source_path !== 'pi-node/bot-release-results/'+receipt.request_id+'.json'
      || !hex40(receipt.source_sha) || !hex64(receipt.image_digest) || !hex64(receipt.request_sha256)
      || receipt.status !== 'passed'
      || receipt.broker_mutation_attempted !== false
      || receipt.gateway_restart_attempted !== false
      || receipt.bot_started !== false || receipt.replay_allowed !== false
      || !keys(status,ok) || status.schema !== 'commandcenter.pi.bot_live_status.v1'
      || status.node_id !== 'cc-pi4' || receipt.message !== status.status
      || !['LIVE_SWITCHES_ENABLED','LIVE_NOT_CONFIRMED'].includes(status.status)
      || status.read_only !== true || status.broker_submission_verified !== false
      || status.broker_mutation_attempted !== false || status.gateway_mutation_attempted !== false
      || !keys(status.global_live_flags,flags) || !keys(status.selected_live_policies,ids)
      || !Object.values(status.global_live_flags).every(x=>typeof x==='boolean')
      || !Object.values(status.selected_live_policies).every(x=>typeof x==='boolean')
      || !requiredIfEnabled.concat(['live_switches_enabled']).every(k=>typeof status[k]==='boolean')
      || !['yes','no','unknown'].includes(status.gateway_readonly_api_configuration)) reject();
  const enabled = requiredIfEnabled.every(k=>status[k]===true)
    && Object.values(status.global_live_flags).every(Boolean)
    && Object.values(status.selected_live_policies).every(Boolean);
  if ((status.live_switches_enabled && !enabled)
      || (status.status==='LIVE_SWITCHES_ENABLED')!==status.live_switches_enabled) reject();
  const started=utc(receipt.started_at), finished=utc(receipt.finished_at);
  if (!Number.isFinite(started) || !Number.isFinite(finished)
      || started > finished || finished - started > 1200000
      || finished > now + NOW_SKEW_MS || now - finished > MAX_AGE_MS) reject();
  return { receipt, observation:status, observedAt:receipt.finished_at,
    observedAtMs: finished, replayId: receipt.request_id,
    resultCommitSha: input.result_commit_sha };
}
export function piBotLiveOperatorView(record, now = Date.now()) {
  if (!record || record.schema !== 'mmibkr.pi_bot_live_store.v1') reject();
  const v=validatePiBotLiveEnvelope(record.envelope,now);
  const stored=utc(record.stored_at_utc);
  if (!Number.isFinite(stored) || stored > now + NOW_SKEW_MS || now - stored > MAX_AGE_MS) reject();
  const o=v.observation;
  return {
    schema: 'mmibkr.pi_bot_live_operator_view.v1', node_id: 'cc-pi4',
    source: 'authenticated_root_bot_status', observed_at: v.observedAt,
    stored_at_utc: record.stored_at_utc, receipt_sha: v.resultCommitSha,
    status: o.status, live_switches_enabled: o.live_switches_enabled,
    bot_running: o.bot_running, gateway_running: o.gateway_running,
    global_live_flags: { ...o.global_live_flags },
    selected_live_policies: { ...o.selected_live_policies },
    gateway_readonly_api_configuration: o.gateway_readonly_api_configuration,
    broker_submission_verified: false, read_only: true,
    broker_mutation_attempted: false, gateway_mutation_attempted: false,
    permission_mutation_attempted: false,
  };
}

function canonical(value) {
  if (Array.isArray(value)) return '['+value.map(canonical).join(',')+']';
  if (value!==null && typeof value==='object') return '{'
    +Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}';
  return JSON.stringify(value);
}
export async function verifyPiBotRootDigest(envelope) {
  if (envelope?.schema!=='mmibkr.pi_bot_live_observation_envelope.v2') return true;
  const record=envelope.record;
  if (!record || !record.snapshot || !hex64(record.snapshot_sha256)) reject();
  const bytes=new TextEncoder().encode(canonical(record.snapshot));
  const hash=await crypto.subtle.digest('SHA-256',bytes);
  const actual=[...new Uint8Array(hash)].map(x=>x.toString(16).padStart(2,'0')).join('');
  if (actual!==record.snapshot_sha256) reject();
  const observed=new Date(utc(record.observed_at));
  if (!Number.isFinite(observed.getTime())) reject();
  const stamp=observed.toISOString().slice(0,19).replace(/[-T:]/g,'');
  if (record.observation_id!==`pibotobs-${stamp}-${actual.slice(0,16)}`) reject();
  return true;
}
