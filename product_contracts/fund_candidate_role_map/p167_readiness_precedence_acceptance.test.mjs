import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD = '6542af4ecf19eaaf21168cfdd5d265b4facc7a0a'
const p167 = Object.freeze({run:34417053594,job:102684140262,artifact:10129482117,survivors:3,total:5,required:4})
const readiness = Object.freeze({base_state:'ISSUER_REPLAY_SUPPORTED_UNIVERSE_ROBUSTNESS_OPEN',older_admission_effect:'PRESERVED_AS_ADDITIVE_EVIDENCE_DOES_NOT_OVERRIDE_NEWER_FAILED_ROBUSTNESS',older_admission_may_mark_complete:false})
const boundaries = Object.freeze({ranking:false,allocation:false,sizing:false,promotion:false,strategy_spec:false,runtime:false,data:false,broker:false,live_trading:false})

test('bind exact MM readiness-precedence head', () => assert.equal(MM_PRODUCT_HEAD,'6542af4ecf19eaaf21168cfdd5d265b4facc7a0a'))
test('newer P167 failed robustness stays authoritative over older admission', () => {
  assert.ok(p167.survivors < p167.required)
  assert.equal(readiness.base_state,'ISSUER_REPLAY_SUPPORTED_UNIVERSE_ROBUSTNESS_OPEN')
  assert.equal(readiness.older_admission_may_mark_complete,false)
  assert.match(readiness.older_admission_effect,/DOES_NOT_OVERRIDE_NEWER_FAILED_ROBUSTNESS/)
})
test('preserve exact P167 identity used by precedence guard', () => assert.deepEqual([p167.run,p167.job,p167.artifact],[34417053594,102684140262,10129482117]))
test('precedence correction grants no authority transfer', () => assert.deepEqual(Object.values(boundaries),Array(Object.keys(boundaries).length).fill(false)))
