import assert from 'node:assert/strict'
import { validatePiBotLiveEnvelope, piBotLiveOperatorView, verifyPiBotRootDigest } from '../cloudflare/operator-console/src/pi_bot_live_observation.js'
import { OperatorState } from '../cloudflare/operator-console/src/index.js'
import { createHash } from 'node:crypto'
const now=Date.parse('2026-11-01T04:20:00Z')
const stamp='2026-11-01T04:19:30Z',rid='pi-bot-live-status-202611010419'
const observation={
  schema:'commandcenter.pi.bot_live_status.v1',node_id:'cc-pi4',
  status:'LIVE_SWITCHES_ENABLED',live_switches_enabled:true,
  bot_running:true,gateway_running:true,gateway_network_namespace_matched:true,
  single_canonical_main:true,global_live_flags:{ENABLE_LIVE_TRADING:true,MM_ENABLE_LIVE_TRADING:true},
  selected_live_policies:{MNQ:true,AMAT:true,APH:true},
  stock_canary_enabled:true,private_network_attested_by_launcher:true,legacy_backtest_disabled:true,
  restart_persistent:true,gateway_readonly_api_configuration:'unknown',
  broker_submission_verified:false,broker_mutation_attempted:false,
  gateway_mutation_attempted:false,read_only:true,
}
function envelope(){
  return {schema:'mmibkr.pi_bot_live_observation_envelope.v1',node_id:'cc-pi4',
    source_repo:'XoticHaze/CommandCenter-gate-control',source_ref:'pi-node-outbox',
    source_path:'pi-node/bot-release-results/'+rid+'.json',
    result_commit_sha:'a'.repeat(40),result_blob_sha:'b'.repeat(40),
    receipt:{schema:'commandcenter.pi.bot_release_result.v1',node_id:'cc-pi4',
      request_id:rid,action:'pi.bot.live_status',source_sha:'c'.repeat(40),
      image_digest:'d'.repeat(64),request_sha256:'e'.repeat(64),
      status:'passed',message:'LIVE_SWITCHES_ENABLED',
      started_at:'2026-11-01T04:19:10Z',finished_at:stamp,
      broker_mutation_attempted:false,gateway_restart_attempted:false,
      bot_started:false,replay_allowed:false,live_status:structuredClone(observation)}}
}
const e=envelope()
assert.equal(validatePiBotLiveEnvelope(e,now).replayId,rid)
const record={schema:'mmibkr.pi_bot_live_store.v1',envelope:e,
  stored_at_utc:'2026-11-01T04:19:35Z'}
assert.equal(piBotLiveOperatorView(record,now).live_switches_enabled,true)
assert.equal(piBotLiveOperatorView(record,now).permission_mutation_attempted,false)
const fail=x=>assert.throws(()=>validatePiBotLiveEnvelope(x,now),/pi_bot_observation_rejected/)
fail({...envelope(),source_path:'pi-node/results/'+rid+'.json'})
fail({...envelope(),source_ref:'wrong'})
fail({...envelope(),receipt:{...e.receipt,action:'pi.bot.no_submit_start'}})
fail({...envelope(),receipt:{...e.receipt,bot_started:true}})
fail({...envelope(),receipt:{...e.receipt,live_status:{...observation,broker_submission_verified:true}}})
fail({...envelope(),receipt:{...e.receipt,live_status:{...observation,live_switches_enabled:false}}})
assert.throws(()=>piBotLiveOperatorView(record,now+12*60000),/pi_bot_observation_rejected/)
console.log('Authenticated Pi bot-origin public ingestion contract: PASS')


// Recurring root-approved immutable observation, independently versioned
// from the one-shot typed command. Test actual SHA256/ID binding with WebCrypto.
function canonical(value) {
  if (Array.isArray(value)) return '['+value.map(canonical).join(',')+']';
  if (value!==null && typeof value==='object') return '{'
    +Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}';
  return JSON.stringify(value);
}
const rootStatus = structuredClone(observation);
const rawDigest = createHash('sha256').update(canonical(rootStatus),'utf8').digest('hex');
const rootId = 'pibotobs-20261101041930-'+rawDigest.slice(0,16);
const rootRecord = {
  schema:'commandcenter.pi.bot_live_observation_outbox.v1',node_id:'cc-pi4',
  observation_id:rootId,observed_at:stamp,snapshot_sha256:rawDigest,snapshot:rootStatus,
  producer:'root_approved_fixed_pi_bot_inspection',read_only:true,
  broker_mutation_attempted:false,gateway_mutation_attempted:false,
};
const rootEnvelope = {
  schema:'mmibkr.pi_bot_live_observation_envelope.v2',node_id:'cc-pi4',
  source_repo:'XoticHaze/CommandCenter-gate-control',source_ref:'pi-node-outbox',
  source_path:'pi-node/bot-observations/'+rootId+'.json',
  result_commit_sha:'d'.repeat(40),result_blob_sha:'e'.repeat(40),record:rootRecord,
};
const validatedRoot=validatePiBotLiveEnvelope(rootEnvelope,now);
assert.equal(validatedRoot.replayId,'root:'+rootId);
assert.equal(validatedRoot.observedAt,stamp);
assert.equal(await verifyPiBotRootDigest(rootEnvelope),true);
const rootStored={
  schema:'mmibkr.pi_bot_live_store.v1',envelope:rootEnvelope,
  stored_at_utc:'2026-11-01T04:19:35Z',
};
const rootView=piBotLiveOperatorView(rootStored,now);
assert.equal(rootView.schema,'mmibkr.pi_bot_live_operator_view.v1');
assert.equal(rootView.source,'authenticated_root_bot_status');
assert.equal(rootView.live_switches_enabled,true);
assert.equal(rootView.broker_submission_verified,false);
const changedDigest=structuredClone(rootEnvelope);
changedDigest.record.snapshot.selected_live_policies.MNQ=false;
await assert.rejects(()=>verifyPiBotRootDigest(changedDigest),/pi_bot_observation_rejected/);
const changedId=structuredClone(rootEnvelope);
changedId.record.observation_id='pibotobs-20261101041930-'+'f'.repeat(16);
changedId.source_path='pi-node/bot-observations/'+changedId.record.observation_id+'.json';
assert.equal(validatePiBotLiveEnvelope(changedId,now).replayId,'root:'+changedId.record.observation_id);
await assert.rejects(()=>verifyPiBotRootDigest(changedId),/pi_bot_observation_rejected/);
const wrongSource=structuredClone(rootEnvelope);wrongSource.source_path='pi-node/results/forged.json';
assert.throws(()=>validatePiBotLiveEnvelope(wrongSource,now),/pi_bot_observation_rejected/);
const mutated=structuredClone(rootEnvelope);mutated.record.broker_mutation_attempted=true;
assert.throws(()=>validatePiBotLiveEnvelope(mutated,now),/pi_bot_observation_rejected/);
assert.throws(()=>validatePiBotLiveEnvelope(rootEnvelope,now+12*60*1000),/pi_bot_observation_rejected/);
console.log('Pi bot v2 recurring root outbox: SHA256, identity, freshness, source and no-mutation PASS')


// Recurring 2-minute root observations must remain accepted past the former
// fixed 256-entry replay-capacity ceiling. All observations are synthetic.
const memory=new Map();
const storage={
  transaction:async fn=>fn({get:async k=>memory.get(k),put:async(k,v)=>{memory.set(k,v)}}),
  get:async k=>memory.get(k)
};
const worker=new OperatorState({storage},{});
const originalNow=Date.now;
try {
  const firstTime=Date.parse('2026-11-01T00:00:00Z');
  for (let i=0;i<270;i++) {
    const observed=new Date(firstTime+i*120000).toISOString().replace('.000Z','Z');
    const tag=observed.slice(0,19).replace(/[-T:]/g,'');
    const rid='pibotobs-'+tag+'-'+rawDigest.slice(0,16);
    const incoming=structuredClone(rootEnvelope);
    incoming.record.observed_at=observed;
    incoming.record.observation_id=rid;
    incoming.source_path='pi-node/bot-observations/'+rid+'.json';
    incoming.result_commit_sha=(i+1).toString(16).padStart(40,'0');
    incoming.result_blob_sha=(i+501).toString(16).padStart(40,'0');
    const instant=firstTime+i*120000+30000;
    Date.now=()=>instant;
    const request=()=>new Request('https://operator-state.internal/pi-bot/store',{
      method:'POST',headers:{'content-type':'application/json'},
      body:JSON.stringify({envelope:incoming})
    });
    const response=await worker.fetch(request());
    assert.equal(response.status,201,'recurring observation '+i+' rejected: '+await response.clone().text());
    if (i===269) {
      const repeat=await worker.fetch(request());
      assert.equal(repeat.status,409,'same fresh observation must be replay rejected');
    }
  }
  const ledger=memory.get('pi_bot_live_ledger');
  assert.ok(ledger.length<256,'old entries not garbage collected');
  const read=await worker.fetch(new Request('https://operator-state.internal/pi-bot/latest'));
  assert.equal(read.status,200);
  const stored=await read.json();
  assert.equal(stored.schema,'mmibkr.pi_bot_live_store.v1');
  assert.equal(stored.envelope.receipt,undefined);
  assert.equal(stored.envelope.record.observation_id.startsWith('pibotobs-'),true);
} finally {
  Date.now=originalNow;
}
console.log('Pi bot root feed: >256 recurring observations, bounded replay and latest readback PASS');
