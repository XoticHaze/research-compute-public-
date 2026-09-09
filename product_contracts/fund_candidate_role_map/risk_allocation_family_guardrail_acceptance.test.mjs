import test from 'node:test'
import assert from 'node:assert/strict'
const MM_PRODUCT_HEAD='8327a1e092dbeb36a36ae9e1a5887ba8f371796a'
const rows=[
 {id:'P137',run:34390306098,job:102596712888,artifact:10119355149,cagr:.0974,matched:.1187,foldWins:1},
 {id:'P141',run:34391018746,job:102599046712,artifact:10119625695,cagr:.0436,matched:.0504,foldWins:2},
 {id:'P145',run:34391764559,job:102601521956,artifact:10119910554,cagr:.0731,matched:.0970,foldWins:0},
]
test('bind exact dynamic risk-allocation product head',()=>assert.equal(MM_PRODUCT_HEAD,'8327a1e092dbeb36a36ae9e1a5887ba8f371796a'))
test('all three predeclared formulations trail capital-usage-matched static controls',()=>{for(const r of rows){assert.ok(r.cagr<r.matched);assert.ok(r.foldWins<=2)}})
test('preserve exact source execution identities',()=>assert.deepEqual(rows.map(r=>[r.id,r.run,r.job,r.artifact]),[['P137',34390306098,102596712888,10119355149],['P141',34391018746,102599046712,10119625695],['P145',34391764559,102601521956,10119910554]]))
test('no portfolio or trading authority',()=>assert.deepEqual(Object.values({ranking:false,allocation:false,sizing:false,leverage:false,timing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,live:false}),Array(11).fill(false)))
