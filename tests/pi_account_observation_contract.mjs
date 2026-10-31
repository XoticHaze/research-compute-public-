import assert from 'node:assert/strict';
import {validatePiAccountObservation,validatePiObservationEnvelope,piOperatorView} from '../cloudflare/operator-console/src/pi_account_observation.js';
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
