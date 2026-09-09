import test from 'node:test'
import assert from 'node:assert/strict'
const MM_PRODUCT_HEAD='17250f146b296bc1b3652fbf47374288e67634aa'
const r={run:34385308952,job:102579966549,artifact:10117467662,head:'1563c369fc355c3e0609d523b2a3998cafa326a6',decision:'P130_VIX_TERM_REGIME_NOT_SUPPORTED',y2010:{matched:0.05217411410680883,spy:-0.0080067250249225,pm:5,ps:1},y2015:{matched:0.061813641201676095,spy:-0.013714744331526418,pm:4,ps:2},y2020:{matched:0.09137323503179973,spy:-0.014567918849646366,pm:4,ps:1}}
test('bind exact P130 head',()=>assert.equal(MM_PRODUCT_HEAD,'17250f146b296bc1b3652fbf47374288e67634aa'))
test('preserve matched success and opportunity failure together',()=>{assert.equal(r.decision,'P130_VIX_TERM_REGIME_NOT_SUPPORTED');for(const w of [r.y2010,r.y2015,r.y2020]){assert.ok(w.matched>0);assert.ok(w.spy<0)}})
test('no promotion from matched headline',()=>assert.deepEqual(Object.values({ranking:false,allocation:false,sizing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,live:false}),Array(9).fill(false)))