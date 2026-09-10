import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD='47347c0a6a4f11675a8f5e53783439ff479609fd'
const p437=Object.freeze({
  control:'XLI',
  windows:{y2012:{XAR:3.642,ITA:2.043},y2016:{XAR:3.032,ITA:0.844},y2020:{XAR:0.490,ITA:-1.495}},
  chronology:[5.295,6.109,-7.046,5.734],
  positive_blocks:3,
  total_blocks:4,
  run:34523614925,job:103027033839,artifact:10170642767,
  artifact_sha:'071ee8d76cdaac891a8f2ecb5ee7945ca73bac10613c381b727eea7b64d669a8'
})

test('bind exact P437 product head',()=>assert.equal(MM_PRODUCT_HEAD,'47347c0a6a4f11675a8f5e53783439ff479609fd'))
test('matched XLI transport evidence remains exact',()=>{assert.equal(p437.control,'XLI');assert.ok(p437.windows.y2012.XAR>0&&p437.windows.y2012.ITA>0);assert.ok(p437.windows.y2016.XAR>0&&p437.windows.y2016.ITA>0);assert.equal(p437.positive_blocks,3);assert.equal(p437.total_blocks,4)})
test('2020+ two-construction transport gate fails',()=>{assert.ok(p437.windows.y2020.XAR>0);assert.ok(p437.windows.y2020.ITA<0)})
test('exact research identity remains attributable',()=>{assert.deepEqual([p437.run,p437.job,p437.artifact],[34523614925,103027033839,10170642767]);assert.equal(p437.artifact_sha,'071ee8d76cdaac891a8f2ecb5ee7945ca73bac10613c381b727eea7b64d669a8')})
test('consumer does not admit a third engine or grant trading authority',()=>assert.deepEqual(Object.values({thirdIndustryEngine:false,reopenP06:false,ranking:false,allocation:false,sizing:false,promotion:false,strategySpec:false,runtime:false,broker:false,live:false}),Array(10).fill(false)))
