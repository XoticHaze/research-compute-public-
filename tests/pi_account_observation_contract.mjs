import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { OperatorState } from '../cloudflare/operator-console/src/index.js';
import {validatePiAccountObservation,validatePiObservationEnvelope,piOperatorView,verifyPiOutboxSnapshotDigest} from '../cloudflare/operator-console/src/pi_account_observation.js';
import {nextPiReplayLedger} from '../cloudflare/operator-console/src/pi_replay_ledger.js';
const now=Date.parse('2026-10-31T13:00:00.000Z');
function fixture() {
  return {schema:'commandcenter.pi.ibkr_account_readonly_snapshot.v1',node_id:'cc-pi4',
    observed_at:'2026-10-31T12:59:30+00:00',read_only:true,broker_mutation_attempted:false,
    historical_fills_complete:false,canonical_execution_writer_verified:false,account_numbers_emitted:false,
    status:'readback_complete',reason:null,expected_account_matched:true,
    managed_account_count:1,position_count_all_managed:4,open_order_count_all_managed:2,
    recent_execution_count_all_managed:0,expected_account_position_count:4,
    expected_account_open_order_count:2,expected_account_recent_execution_count:0,
    unattributed_record_count:0,foreign_account_record_count:0,
    expected_account_symbol_position_counts:{AMAT:1,APH:2,MNQ:1,OTHER:0},
    expected_account_symbol_open_order_counts:{AMAT:1,APH:0,MNQ:1,OTHER:0},
    selected_scope_authority:'symbol_only_diagnostic_not_strategy_ownership'};
}
function envelope(o=fixture()) {return {schema:'mmibkr.pi_account_observation_envelope.v1',
  node_id:'cc-pi4',command:'pi.ibkr_account_readonly',request_id:'ccpi-read-20261031',
  result_commit_sha:'a'.repeat(40),observation:o};}
function rejected(fn) {assert.throws(fn,/pi_/);}
assert.equal(validatePiAccountObservation(fixture(),now).expected_account_position_count,4);
assert.equal(validatePiObservationEnvelope(envelope(),now).request_id,'ccpi-read-20261031');
const view=piOperatorView({envelope:envelope(),stored_at_utc:'2026-10-31T13:00:00Z'},now);
assert.equal(view.position_count,4);
assert.equal(view.broker_mutation_authority,false);
assert.equal(view.canonical_execution_writer_verified,false);
for(const [key,value] of [['account','DUXXXXXX'],['token','secret'],['credentials','hidden'],
  ['orders',[{id:1}]],['symbol','MNQ']]) rejected(()=>validatePiAccountObservation({...fixture(),[key]:value},now));
for(const [key,value] of [['read_only',false],['broker_mutation_attempted',true],
  ['historical_fills_complete',true],['canonical_execution_writer_verified',true],
  ['account_numbers_emitted',true],['node_id','other']]) rejected(()=>validatePiAccountObservation({...fixture(),[key]:value},now));
rejected(()=>validatePiAccountObservation({...fixture(),observed_at:'2026-10-31T12:50:00Z'},now));
rejected(()=>validatePiAccountObservation({...fixture(),observed_at:'2026-10-31T13:02:00Z'},now));
rejected(()=>validatePiAccountObservation({...fixture(),observed_at:'2026-10-31T12:59:00'},now));
rejected(()=>validatePiAccountObservation({...fixture(),expected_account_symbol_position_counts:{AMAT:9,APH:2,MNQ:1,OTHER:0}},now));
rejected(()=>validatePiAccountObservation({...fixture(),expected_account_position_count:5},now));
// The actual root-owned Pi reader requires a single, fully attributed account.
// Do not weaken its sole-account provenance at the public ingest boundary.
rejected(()=>validatePiAccountObservation({...fixture(),managed_account_count:2},now));
rejected(()=>validatePiAccountObservation({...fixture(),foreign_account_record_count:1},now));
rejected(()=>validatePiAccountObservation({...fixture(),unattributed_record_count:1},now));
rejected(()=>validatePiAccountObservation({...fixture(),expected_account_position_count:3,
  expected_account_symbol_position_counts:{AMAT:1,APH:1,MNQ:1,OTHER:0}},now));
rejected(()=>validatePiAccountObservation({...fixture(),expected_account_position_count:NaN},now));
rejected(()=>validatePiObservationEnvelope({...envelope(),node_id:'other'},now));
rejected(()=>validatePiObservationEnvelope({...envelope(),result_commit_sha:'bad'},now));
rejected(()=>validatePiObservationEnvelope({...envelope(),request_id:'../path'},now));
const unbound=fixture();
unbound.status='readback_complete_unbound';unbound.reason='EXPECTED_ACCOUNT_NOT_CONFIGURED';
unbound.expected_account_matched=null;
for(const key of ['expected_account_position_count','expected_account_open_order_count',
  'expected_account_recent_execution_count','foreign_account_record_count',
  'expected_account_symbol_position_counts','expected_account_symbol_open_order_counts']) unbound[key]=null;
assert.equal(validatePiAccountObservation(unbound,now).status,'readback_complete_unbound');
const blocked=fixture();blocked.status='blocked';blocked.reason='BROKER_READ_ONLY_REQUEST_FAILED';blocked.expected_account_matched=null;
for(const key of ['managed_account_count','position_count_all_managed','open_order_count_all_managed',
  'recent_execution_count_all_managed','expected_account_position_count','expected_account_open_order_count',
  'expected_account_recent_execution_count','unattributed_record_count','foreign_account_record_count',
  'expected_account_symbol_position_counts','expected_account_symbol_open_order_counts']) blocked[key]=null;
assert.equal(validatePiAccountObservation(blocked,now).status,'blocked');
console.log('pi account observation contract: bounded source assertions passed');

// A duplicate request or private Git commit cannot be accepted by the durable
// state writer merely by changing the caller-supplied observation timestamp.
const replayFirst={request_id:'ccpi-read-20261031',result_commit_sha:'a'.repeat(40)};
const replaySecond={request_id:'ccpi-read-20261031-next',result_commit_sha:'b'.repeat(40)};
const replayNow=1793455200000;
const replayLedger=nextPiReplayLedger(null,replayFirst,replayNow);
assert.equal(replayLedger.entries.length,1);
assert.throws(()=>nextPiReplayLedger(replayLedger,replayFirst,replayNow+1),/pi_replay_detected/);
assert.throws(()=>nextPiReplayLedger(replayLedger,{...replaySecond,result_commit_sha:replayFirst.result_commit_sha},replayNow+1),/pi_replay_detected/);
assert.throws(()=>nextPiReplayLedger(replayLedger,{...replaySecond,request_id:replayFirst.request_id},replayNow+1),/pi_replay_detected/);
assert.equal(nextPiReplayLedger(replayLedger,replaySecond,replayNow+1).entries.length,2);
assert.throws(()=>nextPiReplayLedger({schema:'wrong',entries:[]},replayFirst,replayNow),/pi_replay_ledger_invalid/);
assert.equal(nextPiReplayLedger(null,{request_id:'ccpi:read:20261031',result_commit_sha:'c'.repeat(40)},replayNow).entries.length,1);
assert.throws(()=>nextPiReplayLedger(null,{request_id:'../path',result_commit_sha:'d'.repeat(40)},replayNow),/pi_replay_identity_invalid/);

 
// A root-approved periodic snapshot is a DISTINCT immutable-outbox producer.
// It must never be relabeled as a typed request, and never inherit broker rights.
function independentlyCanonicalForTest(value) {
  if (Array.isArray(value)) return '[' + value.map(independentlyCanonicalForTest).join(',') + ']';
  if (value !== null && typeof value === 'object') {
    return '{' + Object.entries(value).sort(([a],[b]) => a.localeCompare(b))
      .map(([k,v]) => JSON.stringify(k) + ':' + independentlyCanonicalForTest(v)).join(',') + '}';
  }
  return JSON.stringify(value);
}
function outboxEnvelope() {
  const digest = createHash('sha256').update(independentlyCanonicalForTest(fixture())).digest('hex');
  const observationId = 'piobs-20261031125930-' + digest.slice(0,16);
  return {
    schema: 'mmibkr.pi_account_observation_envelope.v2',
    node_id: 'cc-pi4',
    producer_kind: 'root_approved_existing_agent_snapshot_reader',
    observation_id: observationId,
    source_path: 'pi-node/observations/' + observationId + '.json',
    result_commit_sha: 'e'.repeat(40),
    record: {
      schema: 'commandcenter.pi.account_observation_outbox.v1',
      node_id: 'cc-pi4',
      observation_id: observationId,
      observed_at: fixture().observed_at,
      snapshot_sha256: digest,
      snapshot: fixture(),
      producer: 'root_approved_existing_agent_snapshot_reader',
      read_only: true,
      broker_mutation_attempted: false,
    },
  };
}
const outbox = outboxEnvelope();
const normalizedOutbox = validatePiObservationEnvelope(outbox,now);
assert.equal(await verifyPiOutboxSnapshotDigest(outbox),true);
assert.equal(normalizedOutbox.observation.expected_account_position_count,4);
assert.equal(normalizedOutbox.observation_id,outbox.observation_id);
assert.equal(normalizedOutbox.command,undefined);
assert.equal(normalizedOutbox.request_id,undefined);
const outboxView=piOperatorView({envelope:outbox,stored_at_utc:'2026-10-31T13:00:00Z'},now);
assert.equal(outboxView.source,'root_observation_outbox');
assert.equal(outboxView.strategy_authority,false);
assert.equal(outboxView.live_execution_allowed,false);
assert.equal(outboxView.canonical_execution_writer_verified,false);
const outboxReplay=nextPiReplayLedger(null,normalizedOutbox,now);
assert.equal(outboxReplay.entries[0].request_id,'outbox:'+outbox.observation_id);
assert.throws(()=>nextPiReplayLedger(outboxReplay,normalizedOutbox,now+1),/pi_replay_detected/);
assert.throws(()=>nextPiReplayLedger(outboxReplay,validatePiObservationEnvelope({
  ...outbox, observation_id:'piobs-20261031125931-'+outbox.record.snapshot_sha256.slice(0,16),
  source_path:'pi-node/observations/piobs-20261031125931-'+outbox.record.snapshot_sha256.slice(0,16)+'.json',
  record:{...outbox.record,observation_id:'piobs-20261031125931-'+outbox.record.snapshot_sha256.slice(0,16)},
},now),now+1),/pi_replay_detected/);
rejected(()=>validatePiObservationEnvelope({...outbox,command:'pi.ibkr_account_readonly'},now));
rejected(()=>validatePiObservationEnvelope({...outbox,request_id:'fake-command'},now));
rejected(()=>validatePiObservationEnvelope({...outbox,source_path:'pi-node/results/fake.json'},now));
rejected(()=>validatePiObservationEnvelope({...outbox,producer_kind:'pi.ibkr_account_readonly'},now));
rejected(()=>validatePiObservationEnvelope({...outbox,record:{...outbox.record,producer:'unapproved'}},now));
rejected(()=>validatePiObservationEnvelope({...outbox,record:{...outbox.record,read_only:false}},now));
rejected(()=>validatePiObservationEnvelope({...outbox,record:{...outbox.record,snapshot_sha256:'0'.repeat(64)}},now));
rejected(()=>validatePiObservationEnvelope({...outbox,record:{...outbox.record,observed_at:'2026-10-31T12:00:00+00:00'}},now));
rejected(()=>validatePiObservationEnvelope({...outbox,record:{...outbox.record,snapshot:{...fixture(),account:'DUXXXX'}}},now));
rejected(()=>validatePiObservationEnvelope({...outbox,record:{...outbox.record,snapshot:{...fixture(),observed_at:'2026-10-31T12:50:00+00:00'}}},now));
console.log('Pi immutable root-outbox contract: producer separation, replay and fail-close verified');

await assert.rejects(async()=>verifyPiOutboxSnapshotDigest({...outbox,record:{...outbox.record,snapshot:{...fixture(),expected_account_position_count:3}}}),/pi_outbox_snapshot_digest_rejected/);

// Pi durable-store end-to-end: the actual v2 outbox record must survive both
// validation stages and round-trip through the same Durable Object contract.
const previousDateNow = Date.now;
const durable = new Map();
const memoryStorage = {
  transaction: async (callback) => callback({
    get: async (key) => durable.get(key),
    put: async (key,value) => { durable.set(key,value); },
  }),
  get: async (key) => durable.get(key),
};
try {
  Date.now = () => now;
  const worker = new OperatorState({storage:memoryStorage},{});
  const request = () => new Request('https://operator-state.internal/pi/store',{
    method:'POST',
    headers:{'content-type':'application/json'},
    body:JSON.stringify({envelope:outbox,publisher:{workflow_ref:'not_real_auth'}}),
  });
  const initial = await worker.fetch(request());
  assert.equal(initial.status,201,JSON.stringify(await initial.clone().json()));
  const acknowledged = await initial.json();
  assert.equal(acknowledged.durable_readback_verified,true);
  const latest = await worker.fetch(new Request('https://operator-state.internal/pi/latest'));
  assert.equal(latest.status,200);
  const stored = await latest.json();
  assert.equal(stored.envelope.schema,outbox.schema);
  assert.equal(stored.envelope.record.snapshot_sha256,outbox.record.snapshot_sha256);
  assert.equal(piOperatorView(stored,now).source,'root_observation_outbox');
  const replay = await worker.fetch(request());
  assert.equal(replay.status,409);
  assert.equal((await replay.json()).error,'pi_observation_replay_or_ledger_held');
} finally {
  Date.now = previousDateNow;
}
console.log('Pi durable-store end-to-end: v2 record preserved, replay and readback PASS');
