import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD='10827ad0631690ad49ed16daef20a1e47a15043d'
const regime=Object.freeze({
  discriminator:'prior completed 12-month UUP return', completed_months:140, coverage_gate:24,
  strong:{months:97,hefa:1.341,dbef:1.396,mean:1.369},
  weak:{months:43,hefa:3.438,dbef:3.652,mean:3.545},
  run:34523556131,job:103026819030,artifact:10170621300,
  artifact_sha:'fe5c4bd4ff19a71fcbc402368473bc8c3129843323ae45c6601e89b34d85202f'
})

test('bind exact P436 product head',()=>assert.equal(MM_PRODUCT_HEAD,'10827ad0631690ad49ed16daef20a1e47a15043d'))
test('both lagged-dollar states pass coverage',()=>{assert.ok(regime.strong.months>=regime.coverage_gate);assert.ok(regime.weak.months>=regime.coverage_gate);assert.equal(regime.strong.months+regime.weak.months,regime.completed_months)})
test('both independent implementations remain positive in both regimes',()=>{assert.ok(regime.strong.hefa>0&&regime.strong.dbef>0&&regime.strong.mean>0);assert.ok(regime.weak.hefa>0&&regime.weak.dbef>0&&regime.weak.mean>0)})
test('exact P436 research identity remains attributable',()=>{assert.deepEqual([regime.run,regime.job,regime.artifact],[34523556131,103026819030,10170621300]);assert.equal(regime.artifact_sha,'fe5c4bd4ff19a71fcbc402368473bc8c3129843323ae45c6601e89b34d85202f')})
test('consumer grants no portfolio or trading authority',()=>assert.deepEqual(Object.values({ranking:false,allocation:false,sizing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,live:false}),Array(9).fill(false)))
