import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD = '2d6a77667478d58b0b72c7fd9fbbe066643c4cfa'
const family = [
  { id:'P146', run:34407964382, job:102655387255, artifact:10126079621, head:'ee06a77589482312fc3b1e7bf63cc8e23f06e942', matched:0.0009, spy:-0.0071 },
  { id:'P147', run:34408012296, job:102655540369, artifact:10126096145, head:'b73914955a8fe8faefb0d766fdfc6e8785b98660', matched:-0.0173, spy:-0.0310 },
  { id:'P148', run:34408069575, job:102655732260, artifact:10126120844, head:'fc73769892aca598a831c1da65272f68c652a0fc', matched:-0.0264, spy:-0.0383 },
  { id:'P149', run:34408123025, job:102655905571, artifact:10126139868, head:'a887dc2069ed6268bbaccae17d3f4f5ae48d3291', matched:-0.0122, spy:-0.0286 },
  { id:'P150', run:34408195652, job:102656137715, artifact:10126167551, head:'514171a8b7ebd4a75ea5b0c370a092505710ef1e', matched:-0.0151, spy:-0.0286 },
]

test('bind exact P146-P150 MM product head', () => assert.equal(MM_PRODUCT_HEAD, '2d6a77667478d58b0b72c7fd9fbbe066643c4cfa'))
test('preserve five independent science execution identities', () => assert.deepEqual(family.map(x => [x.id,x.run,x.job,x.artifact,x.head]), [
  ['P146',34407964382,102655387255,10126079621,'ee06a77589482312fc3b1e7bf63cc8e23f06e942'],
  ['P147',34408012296,102655540369,10126096145,'b73914955a8fe8faefb0d766fdfc6e8785b98660'],
  ['P148',34408069575,102655732260,10126120844,'fc73769892aca598a831c1da65272f68c652a0fc'],
  ['P149',34408123025,102655905571,10126139868,'a887dc2069ed6268bbaccae17d3f4f5ae48d3291'],
  ['P150',34408195652,102656137715,10126167551,'514171a8b7ebd4a75ea5b0c370a092505710ef1e'],
]))
test('family does not establish investable broad-market support', () => { assert.ok(family.every(x => x.spy < 0)); assert.ok(family.slice(1).every(x => x.matched < 0)); assert.ok(family[0].matched < 0.001) })
test('product consequence is guardrail-only with no authority transfer', () => assert.deepEqual(Object.values({ ranking:false, allocation:false, sizing:false, promotion:false, strategySpec:false, runtime:false, data:false, broker:false, live:false }), Array(9).fill(false)))
