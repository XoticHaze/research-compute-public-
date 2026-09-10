import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD = '936bc2fcdd9875b1ee4bcbadfd30bf9c877863aa'
const result = Object.freeze({
  state: 'POST2014_ALL_TARGET_IDENTITY_JOIN_NOT_READY__2015_DISAGREEMENT_LOCALIZED',
  snapshots: [
    ['2015-12-31',97.018,94.304,18,15,'FAIL'],
    ['2020-12-31',99.605,99.254,3,2,'PASS'],
    ['2025-12-31',99.206,99.793,1,4,'PASS'],
  ],
  run:34524508319,
  job:103029980936,
  artifact:10170975866,
  artifact_sha:'f6ae9d260751983792f509be8dbceaca55b2675d7472c220005222b95da653ae',
  post2014_source_ready:true,
  cross_source_identity_adjudicated:true,
  all_target_identity_join_ready:false,
  alpha_blocked:true,
  pre2014_lineage_ready:false,
})

test('bind exact P439 product head',()=>assert.equal(MM_PRODUCT_HEAD,'936bc2fcdd9875b1ee4bcbadfd30bf9c877863aa'))
test('P439 localizes the remaining post-2014 identity failure to 2015',()=>{
  assert.equal(result.snapshots[0][5],'FAIL')
  assert.equal(result.snapshots[0][3],18)
  assert.equal(result.snapshots[0][4],15)
  assert.deepEqual(result.snapshots.slice(1).map((x)=>x[5]),['PASS','PASS'])
  assert.equal(result.cross_source_identity_adjudicated,true)
  assert.equal(result.all_target_identity_join_ready,false)
})
test('exact research identity remains attributable',()=>{
  assert.deepEqual([result.run,result.job,result.artifact],[34524508319,103029980936,10170975866])
  assert.equal(result.artifact_sha,'f6ae9d260751983792f509be8dbceaca55b2675d7472c220005222b95da653ae')
})
test('localized representation failure does not authorize fundamental alpha',()=>{
  assert.equal(result.post2014_source_ready,true)
  assert.equal(result.alpha_blocked,true)
  assert.equal(result.pre2014_lineage_ready,false)
})
test('consumer grants no portfolio or trading authority',()=>assert.deepEqual(Object.values({ranking:false,allocation:false,sizing:false,promotion:false,strategySpec:false,runtime:false,dataAuthority:false,broker:false,live:false}),Array(9).fill(false)))
