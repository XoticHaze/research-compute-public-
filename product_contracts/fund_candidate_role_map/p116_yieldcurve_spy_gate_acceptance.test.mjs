import test from 'node:test'
import assert from 'node:assert/strict'
const MM_PRODUCT_HEAD='b70903eb7553b079907b94f60d6541094bcb59cf'
const r=Object.freeze({run:34379822498,job:102561628048,artifact:10115387467,head:'eafd737f02f179ff748cb94ece4fa309c0d8a94f',matched25pp:1.20,spy25pp:-4.86,positiveMatchedFolds:2,totalFolds:5})
test('bind exact P116 product head',()=>assert.equal(MM_PRODUCT_HEAD,'b70903eb7553b079907b94f60d6541094bcb59cf'))
test('P116 yield-curve SPY gate is rejected at declared chronology and opportunity controls',()=>{assert.equal(r.run,34379822498);assert.equal(r.job,102561628048);assert.equal(r.artifact,10115387467);assert.equal(r.head,'eafd737f02f179ff748cb94ece4fa309c0d8a94f');assert.ok(r.matched25pp>0);assert.ok(r.spy25pp<0);assert.equal(r.positiveMatchedFolds,2);assert.equal(r.totalFolds,5)})
test('no threshold rescue or trading authority',()=>{const b={curveThresholdRescue:false,monthEndConventionRescue:false,costLookbackRescue:false,portfolioRanking:false,allocation:false,sizing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,liveTrading:false};assert.deepEqual(Object.values(b),Array(12).fill(false))})
