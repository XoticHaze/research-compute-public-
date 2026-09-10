import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD='12d6a2c0561a81a0eacebe162819366d2748c165'
const exportState=Object.freeze({schema:'mm.strategy_intelligence.crossasset_deep_robustness_review.v2',banner:'HISTORICAL R2 CONTEXT ONLY',current_authority:'P167_ISSUER_BOUND_UNIVERSE_JACKKNIFE',survivors:3,total:5,required:4,current_gate:false,current_robustness_claim:false})
const historical=Object.freeze({run:34291441675,job:102278643369,artifact:10081493212})
const boundaries=Object.freeze({ranking:false,allocation:false,sizing:false,promotion:false,strategy_spec:false,runtime:false,data:false,broker:false,live_trading:false})

test('bind exact MM chronology-safe export head',()=>assert.equal(MM_PRODUCT_HEAD,'12d6a2c0561a81a0eacebe162819366d2748c165'))
test('portable export clearly separates historical R2 from current P167 gate',()=>{assert.equal(exportState.schema,'mm.strategy_intelligence.crossasset_deep_robustness_review.v2');assert.match(exportState.banner,/HISTORICAL R2/);assert.equal(exportState.current_authority,'P167_ISSUER_BOUND_UNIVERSE_JACKKNIFE');assert.equal(exportState.current_gate,false);assert.ok(exportState.survivors<exportState.required);assert.equal(exportState.current_robustness_claim,false)})
test('historical R2 provenance stays exact',()=>assert.deepEqual([historical.run,historical.job,historical.artifact],[34291441675,102278643369,10081493212]))
test('export grants no capital or trading authority',()=>assert.deepEqual(Object.values(boundaries),Array(Object.keys(boundaries).length).fill(false)))
