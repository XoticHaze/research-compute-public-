import test from 'node:test'
import assert from 'node:assert/strict'

const MM_HEAD='08f6ec15f44fb373e88d20d92fabc6b8241cafc4'
const p99={run:34303359334,job:102314825953,riskOff25:-0.018524001510564842,strongestRemoved25:-0.003136942343758528,riskOff50:-0.024340328041177087,strongestRemoved50:-0.011192497899314084}
const p100={run:34303359367,job:102314826839,p87Bootstrap:[-0.021027138870471137,0.03700956631673848],originalIncremental:-0.0008138339615242351,originalBootstrap:[-0.042330090236285894,0.029318846608003216]}
const p101={run:34303505049,job:102315254334,sameHash:false,maxCloseDiff:0.00018310546875,evalA:0.0008425010563348767,evalB:0.0008425169093397855}

test('acceptance is bound to exact MM posture head',()=>assert.equal(MM_HEAD,'08f6ec15f44fb373e88d20d92fabc6b8241cafc4'))
test('P95 park posture follows weak serial evidence and non-reproducible source materialization',()=>{
  assert.equal(p100.run,34303359367); assert.equal(p101.run,34303505049)
  assert.ok(p100.p87Bootstrap[0] < 0); assert.ok(p100.originalIncremental < 0); assert.ok(p100.originalBootstrap[0] < 0)
  assert.equal(p101.sameHash,false); assert.ok(p101.maxCloseDiff > 0); assert.ok(Math.abs(p101.evalA-p101.evalB) < 0.000001)
})
test('P96 matched-control alpha is concentrated rather than promotable',()=>{
  assert.equal(p99.run,34303359334)
  assert.ok(p99.riskOff25 < 0); assert.ok(p99.riskOff50 < 0); assert.ok(p99.strongestRemoved25 < 0); assert.ok(p99.strongestRemoved50 < 0)
})
test('protected authority remains false',()=>{
  const boundary={portfolioRanking:false,allocation:false,sizing:false,promotion:false,strategySpec:false,runtime:false,broker:false,liveTrading:false}
  assert.deepEqual(Object.values(boundary),Array(8).fill(false))
})
