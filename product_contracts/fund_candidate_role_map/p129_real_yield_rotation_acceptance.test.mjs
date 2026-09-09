import test from 'node:test'
import assert from 'node:assert/strict'
const MM_PRODUCT_HEAD='0262bf27b2ddd117ff736284e157da4175833376'
const r={run:34385151241,job:102579439439,artifact:10117406655,head:'1bad49fab11c761f7843f536a75400059eaeae52',decision:'P129_REAL_YIELD_ROTATION_NOT_SUPPORTED',y2010_50:{matched:-0.02766604072508816,qqq:-0.0744968514181259},y2015_50:{matched:-0.041625026485421435,qqq:-0.07089511643917867}}
test('bind exact P129 product head',()=>assert.equal(MM_PRODUCT_HEAD,'0262bf27b2ddd117ff736284e157da4175833376'))
test('preserve P129 rejection economics',()=>{assert.equal(r.decision,'P129_REAL_YIELD_ROTATION_NOT_SUPPORTED');assert.ok(r.y2010_50.matched<0&&r.y2010_50.qqq<0&&r.y2015_50.matched<0&&r.y2015_50.qqq<0)})
test('no nearby timing rescue authority',()=>assert.deepEqual(Object.values({ranking:false,allocation:false,sizing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,live:false}),Array(9).fill(false)))