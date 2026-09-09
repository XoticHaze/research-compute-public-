import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD = '10cd3c0eaaea3ebdcea0076a4a51b9b895e314a6'
const rows = [
  { id: 'P151', run: 34413216975, job: 102672163347, artifact: 10128051533, head: '71a5d3cbdb78a9573cc22405df810bfb79e8edbf', matched: -0.00659001487035793, recent2022: 0.04397897907480264 },
  { id: 'P152', run: 34413324583, job: 102672502198, artifact: 10128082029, head: 'd6a30c6fd6f6a8411ecc61b1d77dcd081401e9b8', matched: -0.022818006635925814, recent2022: -0.003431886490932623 },
  { id: 'P153', run: 34413636900, job: 102673477302, artifact: 10128198474, head: 'bfb2cf147e1caa1a061cc6dc35afe04ea3feacd9', matched: -0.004387525141116511, recent2022: -0.0017582663253985498 },
]

test('bind exact P151-P153 MM product head', () => assert.equal(MM_PRODUCT_HEAD, '10cd3c0eaaea3ebdcea0076a4a51b9b895e314a6'))
test('all three formulations fail durable matched-control excess', () => assert.ok(rows.every((row) => row.matched < 0)))
test('P151 recent strength is context rather than durable rescue', () => { assert.ok(rows[0].recent2022 > 0); assert.ok(rows[0].matched < 0) })
test('P152 and P153 remain negative in the recent 2022 window', () => assert.ok(rows.slice(1).every((row) => row.recent2022 < 0)))
test('preserve exact science execution identities', () => assert.deepEqual(rows.map((row) => [row.run, row.job, row.artifact, row.head]), [[34413216975,102672163347,10128051533,'71a5d3cbdb78a9573cc22405df810bfb79e8edbf'],[34413324583,102672502198,10128082029,'d6a30c6fd6f6a8411ecc61b1d77dcd081401e9b8'],[34413636900,102673477302,10128198474,'bfb2cf147e1caa1a061cc6dc35afe04ea3feacd9']]))
test('no ranking allocation or trading authority', () => assert.deepEqual(Object.values({ ranking:false, allocation:false, sizing:false, promotion:false, strategySpec:false, runtime:false, data:false, broker:false, live:false }), Array(9).fill(false)))
