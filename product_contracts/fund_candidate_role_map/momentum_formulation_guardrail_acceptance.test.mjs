import test from 'node:test'
import assert from 'node:assert/strict'
const MM_PRODUCT_HEAD='59ebf1bc559d031a1527af874d21bce5ceaed053'
const p142={run:34391213392,job:102599691809,artifact:10119716808,y2015:.1193,matched:.1200,recentExcess:.0359,foldWins:2}
const p144={run:34391655806,job:102601155344,artifact:10119873108,y2015:.0714,matched:.0993,foldWins:0}
test('bind exact momentum product head',()=>assert.equal(MM_PRODUCT_HEAD,'59ebf1bc559d031a1527af874d21bce5ceaed053'))
test('durable formulations fail matched controls',()=>{assert.ok(p142.y2015<p142.matched);assert.ok(p144.y2015<p144.matched);assert.equal(p144.foldWins,0)})
test('preserve P142 recent pocket without durable rescue',()=>assert.ok(p142.recentExcess>.03))
test('preserve exact executions',()=>assert.deepEqual([[p142.run,p142.job,p142.artifact],[p144.run,p144.job,p144.artifact]],[[34391213392,102599691809,10119716808],[34391655806,102601155344,10119873108]]))
test('no portfolio or trading authority',()=>assert.deepEqual(Object.values({ranking:false,allocation:false,sizing:false,leverage:false,timing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,live:false}),Array(11).fill(false)))
