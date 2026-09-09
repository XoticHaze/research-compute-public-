import test from 'node:test'
import assert from 'node:assert/strict'
const MM_PRODUCT_HEAD='227a0cc4b102b0d714500716fe97224a45cee430'
const p118=Object.freeze({run:34381129042,job:102565967623,artifact:10115883610,matched50pp:4.13,spy50pp:-2.55,folds:2})
const p119=Object.freeze({run:34381216208,job:102566260891,artifact:10115917924,matched50pp:-0.60,spy50pp:-2.05,folds:3})
test('bind exact P118/P119 product head',()=>assert.equal(MM_PRODUCT_HEAD,'227a0cc4b102b0d714500716fe97224a45cee430'))
test('P118 fails chronology and SPY opportunity control',()=>{assert.equal(p118.run,34381129042);assert.equal(p118.job,102565967623);assert.equal(p118.artifact,10115883610);assert.ok(p118.matched50pp>0&&p118.spy50pp<0);assert.equal(p118.folds,2)})
test('P119 fails matched and SPY controls',()=>{assert.equal(p119.run,34381216208);assert.equal(p119.job,102566260891);assert.equal(p119.artifact,10115917924);assert.ok(p119.matched50pp<0&&p119.spy50pp<0);assert.equal(p119.folds,3)})
test('no momentum rescue or trading authority',()=>{const b={lookbackRescue:false,topKRescue:false,defensiveHurdleRescue:false,portfolioRanking:false,allocation:false,sizing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,liveTrading:false};assert.deepEqual(Object.values(b),Array(12).fill(false))})
