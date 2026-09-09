import test from 'node:test'
import assert from 'node:assert/strict'
const MM_PRODUCT_HEAD='f607ac9de4889c6c9573e76dcf5051334dedacb5'
const p={run:34391300241,job:102599976559,artifact:10119737624,head:'c2f3cb1e36c7d291fd52f0dbf68219349ca827a6',cagr:.0181,matched:.0437,spy:.1376,sharpe:.28,matchedSharpe:1.28,foldWins:1,totalFolds:5,fiveBpsMatchedExcess:-.0131,y2020MatchedExcess:-.0136}
test('bind exact P143 product head',()=>assert.equal(MM_PRODUCT_HEAD,'f607ac9de4889c6c9573e76dcf5051334dedacb5'))
test('calendar formulation fails matched value and utility',()=>{assert.ok(p.cagr<p.matched);assert.ok(p.cagr<p.spy);assert.ok(p.sharpe<p.matchedSharpe);assert.equal(p.foldWins,1);assert.equal(p.totalFolds,5);assert.ok(p.fiveBpsMatchedExcess<0);assert.ok(p.y2020MatchedExcess<0)})
test('preserve exact execution identity',()=>assert.deepEqual([p.run,p.job,p.artifact,p.head],[34391300241,102599976559,10119737624,'c2f3cb1e36c7d291fd52f0dbf68219349ca827a6']))
test('no portfolio or trading authority',()=>assert.deepEqual(Object.values({ranking:false,allocation:false,sizing:false,leverage:false,timing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,live:false}),Array(11).fill(false)))
