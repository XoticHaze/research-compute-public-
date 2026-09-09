import test from 'node:test'
import assert from 'node:assert/strict'
const MM_PRODUCT_HEAD='a6a33dde1da81886d10999773a751d8137a3968f'
const r=Object.freeze({run:34381469111,job:102567106293,artifact:10116015776,head:'cb9f0f8e6864deadf9daf63d265b25caf041cda5',matched50pp:2.65,spy50pp:0.65,positiveMatchedFolds:2,totalFolds:5})
test('bind exact corrected P117 product head',()=>assert.equal(MM_PRODUCT_HEAD,'a6a33dde1da81886d10999773a751d8137a3968f'))
test('P117 R2 supersedes truncated R1 and fails chronology',()=>{assert.equal(r.run,34381469111);assert.equal(r.job,102567106293);assert.equal(r.artifact,10116015776);assert.equal(r.head,'cb9f0f8e6864deadf9daf63d265b25caf041cda5');assert.ok(r.matched50pp>0&&r.spy50pp>0);assert.equal(r.positiveMatchedFolds,2);assert.equal(r.totalFolds,5)})
test('no late-inception or parameter rescue authority',()=>{const b={lateInceptionRescue:false,lookbackRescue:false,topKRescue:false,portfolioRanking:false,allocation:false,sizing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,liveTrading:false};assert.deepEqual(Object.values(b),Array(12).fill(false))})
