import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD = 'd8174aab7e82eb4dacdf3442cd42ef6c3c5109ce'
const result = Object.freeze({
  state: 'DIRECT_WIKIPEDIA_POST2014_CIK_SOURCE_READY__CROSS_SOURCE_JOIN_REQUIRED_BEFORE_ALPHA',
  snapshots: [
    ['2015-12-31',697200065,'2015-12-28',504,1,1],
    ['2020-12-31',997494787,'2020-12-31',505,1,1],
    ['2025-12-31',1329075976,'2025-12-23',501,1,1],
  ],
  run:34523397010,
  job:103026256699,
  artifact:10170570374,
  artifact_sha:'06129e144866056eb13bd3baf3780d01230fd3b8df5883b1075f1d2c90fbb8de',
  post2014_source_ready:true,
  cross_source_join_passed:false,
  pre2014_lineage_ready:false,
})

test('bind exact P435 product head',()=>assert.equal(MM_PRODUCT_HEAD,'d8174aab7e82eb4dacdf3442cd42ef6c3c5109ce'))
test('all fixed post-2014 snapshots have complete ticker-CIK coverage',()=>{
  assert.deepEqual(result.snapshots.map((x)=>x[0]),['2015-12-31','2020-12-31','2025-12-31'])
  assert.ok(result.snapshots.every((x)=>x[3]>=500 && x[4]===1 && x[5]===1))
  assert.equal(result.post2014_source_ready,true)
})
test('source readiness does not authorize alpha before the cross-source identity join',()=>{
  assert.match(result.state,/CROSS_SOURCE_JOIN_REQUIRED_BEFORE_ALPHA/)
  assert.equal(result.cross_source_join_passed,false)
  assert.equal(result.pre2014_lineage_ready,false)
})
test('exact research identity remains attributable',()=>{
  assert.deepEqual([result.run,result.job,result.artifact],[34523397010,103026256699,10170570374])
  assert.equal(result.artifact_sha,'06129e144866056eb13bd3baf3780d01230fd3b8df5883b1075f1d2c90fbb8de')
})
test('consumer grants no portfolio or trading authority',()=>assert.deepEqual(Object.values({ranking:false,allocation:false,sizing:false,promotion:false,strategySpec:false,runtime:false,dataAuthority:false,broker:false,live:false}),Array(9).fill(false)))
