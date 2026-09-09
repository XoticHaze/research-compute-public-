import test from 'node:test'
import assert from 'node:assert/strict'
const MM_PRODUCT_HEAD='b904d564aebe7f59c1cc0dc3522001004f919565'
const p139={run:34390598417,job:102597671831,artifact:10119466245,y2015:.1148,matched:.1390,y2022:.1474,recentMatchedExcess:.0238,foldWins:1}
const p140={run:34390935212,job:102598779045,artifact:10119594434,y2015:.1281,matched:.1390,y2022:.0565,foldWins:2}
test('bind exact style timing product head',()=>assert.equal(MM_PRODUCT_HEAD,'b904d564aebe7f59c1cc0dc3522001004f919565'))
test('both competing signs fail durable matched chronology',()=>{assert.ok(p139.y2015<p139.matched);assert.ok(p140.y2015<p140.matched);assert.ok(p139.foldWins<=1);assert.ok(p140.foldWins<=2)})
test('preserve recent reversal pocket without durable rescue',()=>{assert.ok(p139.recentMatchedExcess>0);assert.ok(p139.y2022>p140.y2022)})
test('preserve exact execution identities',()=>assert.deepEqual([[p139.run,p139.job,p139.artifact],[p140.run,p140.job,p140.artifact]],[[34390598417,102597671831,10119466245],[34390935212,102598779045,10119594434]]))
test('no portfolio or trading authority',()=>assert.deepEqual(Object.values({ranking:false,allocation:false,sizing:false,leverage:false,timing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,live:false}),Array(11).fill(false)))
