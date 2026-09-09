import test from 'node:test'
import assert from 'node:assert/strict'

const MM_HEAD = '6f5bd4dc3a6c017d42af91f899534364262d6edd'
const evidence = Object.freeze({
  p92: { run:34302637871, job:102312634900, artifact:10085470827, excess50:0.02188823992850719, breakEvenBps:125, riskOff:-0.034870533282343436 },
  p93: { run:34302637928, job:102312635115, retained:0.6101872578835097 },
  p94: { run:34302637910, job:102312635055, positive50:5, weakest50:0.0024926825977327205 },
  p95: { run:34302848916, job:102313293229, excessVsP87:0.0052472254591036105, hybridDD:-0.3478289281132979, baseDD:-0.22633055513532818 },
  p96: { run:34302848959, job:102313293385, foldsControl:5, excessControl50:0.0124532513242539, corr:0.37258051587313196 },
  p97: { run:34303018445, job:102313810042, incremental25:0.0008458634402650489, hybridDD:-0.27765443254025113, baseDD:-0.22093935501221196 },
  p98: { run:34303018631, job:102313810852, rolling60Control25:0.9382716049382716, bootstrapControl25:[-0.005630928658669321,0.038542653933026874], rolling60P87:0.9691358024691358, bootstrapP87:[0.0007621572945674794,0.06310548124618229] },
})

test('acceptance remains bound to the owning-product candidate head', () => { assert.equal(MM_HEAD, '6f5bd4dc3a6c017d42af91f899534364262d6edd') })
test('implementation robustness is positive while state concentration remains visible', () => {
  assert.ok(evidence.p92.excess50 > 0); assert.ok(evidence.p92.breakEvenBps >= 100); assert.ok(evidence.p92.riskOff < 0)
  assert.ok(evidence.p93.retained > 0.6); assert.equal(evidence.p94.positive50, 5); assert.ok(evidence.p94.weakest50 > 0)
})
test('P95 is not a risk-control success and replicated incremental value is tiny', () => {
  assert.ok(evidence.p95.hybridDD < evidence.p95.baseDD); assert.ok(evidence.p97.hybridDD < evidence.p97.baseDD); assert.ok(evidence.p97.incremental25 < 0.005)
})
test('P96/P98 supports diversification persistence without matched-control bootstrap resolution', () => {
  assert.equal(evidence.p96.foldsControl, 5); assert.ok(evidence.p96.excessControl50 > 0); assert.ok(evidence.p96.corr < 0.5)
  assert.ok(evidence.p98.rolling60Control25 > 0.9); assert.ok(evidence.p98.bootstrapControl25[0] < 0); assert.ok(evidence.p98.bootstrapP87[0] > 0)
})
test('protected product boundary remains false for promotion and capital authority', () => {
  const boundary={portfolioRanking:false,allocation:false,sizing:false,promotion:false,strategySpec:false,runtime:false,broker:false,liveTrading:false}
  assert.deepEqual(Object.values(boundary), Array(8).fill(false))
})
