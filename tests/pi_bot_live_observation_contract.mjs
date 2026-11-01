import assert from 'node:assert/strict'
import { validatePiBotLiveEnvelope, piBotLiveOperatorView } from '../cloudflare/operator-console/src/pi_bot_live_observation.js'
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
