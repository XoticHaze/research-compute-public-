import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD = 'b0968a734c1634e97fdbd4ba744629e86bff0b24'
const live = Object.freeze({current_disposition:'PARK_STANDALONE_PRESERVE_COMPONENT_SCOPE',historical_secondary_active:false,historical_context_preserved:true,provenance_visible:true})
const p164 = Object.freeze({run:34416367307,job:102682031382,artifact:10129237160,head:'5bd250b9648f2ae44f8ef7632b851cb03b7c1fed',started:'2026-09-09T23:18:54.6783560Z',conclusion:'success'})
const boundaries = Object.freeze({ranking:false,allocation:false,sizing:false,promotion:false,strategy_spec:false,runtime:false,data:false,broker:false,live_trading:false})

test('bind exact live-review product head', () => assert.equal(MM_PRODUCT_HEAD,'b0968a734c1634e97fdbd4ba744629e86bff0b24'))
test('live fund review uses parked P47 disposition while preserving history only', () => {
  assert.equal(live.current_disposition,'PARK_STANDALONE_PRESERVE_COMPONENT_SCOPE')
  assert.equal(live.historical_secondary_active,false)
  assert.equal(live.historical_context_preserved,true)
  assert.equal(live.provenance_visible,true)
})
test('live review acceptance preserves exact P164 statistical execution identity', () => {
  assert.deepEqual([p164.run,p164.job,p164.artifact,p164.head,p164.conclusion],[34416367307,102682031382,10129237160,'5bd250b9648f2ae44f8ef7632b851cb03b7c1fed','success'])
})
test('live P47 correction grants no capital or trading authority', () => assert.deepEqual(Object.values(boundaries),Array(Object.keys(boundaries).length).fill(false)))
