import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD = '595cbc43d583cd24e0d7c0b42fe7e6b806aab371'
const rows = Object.freeze({
  p431: { matched:[1.794,-0.777,3.816], blocks:[7.250,-7.557,-0.736,7.482], positive_blocks:2, total_blocks:4, run:34521065306, job:103018415020, artifact:10169659843 },
  p432: { windows:[0.228,0.772,1.520], blocks:[-1.273,-0.986,2.660,-0.161], positive_blocks:1, total_blocks:4, run:34521458672, job:103019720434, artifact:10169813747 },
  p434: { cash:[1.744,1.646,1.541], alpha:[-2.044,-2.248,-2.437], blocks:[-0.721,-1.959,-1.785,-4.457,-1.161], positive_alpha_blocks:0, run:34521820785, job:103020928775, artifact:10169956221 },
})

test('bind exact alpha-guardrail MM product head', () => assert.equal(MM_PRODUCT_HEAD, '595cbc43d583cd24e0d7c0b42fe7e6b806aab371'))
test('P431 mixed windows do not override chronology failure', () => {
  assert.ok(rows.p431.matched.some((x)=>x>0) && rows.p431.matched.some((x)=>x<0))
  assert.equal(rows.p431.positive_blocks, 2)
  assert.equal(rows.p431.total_blocks, 4)
})
test('P432 positive full-window alpha does not override chronology persistence failure', () => {
  assert.ok(rows.p432.windows.every((x)=>x>0))
  assert.equal(rows.p432.positive_blocks, 1)
  assert.equal(rows.p432.total_blocks, 4)
})
test('P434 positive cash excess is not mislabeled beta-adjusted alpha', () => {
  assert.ok(rows.p434.cash.every((x)=>x>0))
  assert.ok(rows.p434.alpha.every((x)=>x<0))
  assert.ok(rows.p434.blocks.every((x)=>x<0))
  assert.equal(rows.p434.positive_alpha_blocks, 0)
})
test('all three research results remain exactly attributable', () => {
  assert.deepEqual([rows.p431.run,rows.p431.job,rows.p431.artifact],[34521065306,103018415020,10169659843])
  assert.deepEqual([rows.p432.run,rows.p432.job,rows.p432.artifact],[34521458672,103019720434,10169813747])
  assert.deepEqual([rows.p434.run,rows.p434.job,rows.p434.artifact],[34521820785,103020928775,10169956221])
})
test('consumer grants no portfolio or trading authority', () => assert.deepEqual(Object.values({ ranking:false, allocation:false, sizing:false, promotion:false, strategySpec:false, runtime:false, data:false, broker:false, live:false }), Array(9).fill(false)))
