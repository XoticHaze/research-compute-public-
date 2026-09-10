import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD = '1f7c4389441439411d5ee7ac39a0c63c77983375'
const p426 = Object.freeze({ state:'CURRENCY_HEDGE_INITIAL_SURVIVOR_SUPPORTED__EARLY_REGIME_WEAKNESS_PRESERVED', matched:[2.456,3.207,4.314], chronology:[-0.113,0.486,7.298,2.077], breadth:[3,4], run:34520090360, job:103015151296, artifact:10169274781, protected:{ranking:false,allocation:false,sizing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,live:false} })

test('bind exact P426 MM product head',()=>assert.equal(MM_PRODUCT_HEAD,'1f7c4389441439411d5ee7ac39a0c63c77983375'))
test('support scoped HEFA matched-control survivor',()=>{assert.equal(p426.state,'CURRENCY_HEDGE_INITIAL_SURVIVOR_SUPPORTED__EARLY_REGIME_WEAKNESS_PRESERVED');assert.ok(p426.matched.every((x)=>x>0));assert.deepEqual(p426.breadth,[3,4])})
test('preserve early regime weakness rather than erase it',()=>{assert.ok(p426.chronology[0]<0);assert.ok(p426.chronology.slice(1).every((x)=>x>0))})
test('retain exact research execution identity',()=>assert.deepEqual([p426.run,p426.job,p426.artifact],[34520090360,103015151296,10169274781]))
test('review grants no portfolio or trading authority',()=>assert.deepEqual(Object.values(p426.protected),Array(9).fill(false)))
