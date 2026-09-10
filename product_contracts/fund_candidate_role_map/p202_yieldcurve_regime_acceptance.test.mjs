import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD='dd0e56fe3b6bf1d8b492512d028a90f045d5c623'
const p202=Object.freeze({
  state:'PARK',
  decision:'MODEL_FORMULATION_REJECT',
  run:34430384287,
  job:102724476639,
  started:'2026-09-10T02:40:48Z',
  head:'a52fd632907224cd6cb82a21997c15181f37e241',
  artifact:10134251196,
  artifact_sha256:'2067f3a1e0ea7176c195d58e4834dfb4db9c99cb39bbd43ea714fbb7596db643',
  result:'P202_YIELDCURVE_REGIME_REJECT',
})
const guardrail='Reject P202 as specified. Do not rescue with alternate curve thresholds, lookbacks, assets, costs, or chronology. This failure does not invalidate the separately caveated P36/P64/P82 survivors; rotate away from this simple binary yield-curve timing formulation.'
const boundaries=Object.freeze({ranking:false,allocation:false,sizing:false,promotion:false,strategy_spec:false,runtime:false,data:false,broker:false,live_trading:false})

test('bind exact P202 MM product head',()=>assert.equal(MM_PRODUCT_HEAD,'dd0e56fe3b6bf1d8b492512d028a90f045d5c623'))
test('P202 exact frozen formulation is rejected',()=>{assert.equal(p202.state,'PARK');assert.equal(p202.decision,'MODEL_FORMULATION_REJECT');assert.match(guardrail,/Do not rescue/);assert.match(guardrail,/P36\/P64\/P82/)})
test('preserve exact P202 science execution identity',()=>assert.deepEqual([p202.run,p202.job,p202.started,p202.head,p202.artifact,p202.artifact_sha256,p202.result],[34430384287,102724476639,'2026-09-10T02:40:48Z','a52fd632907224cd6cb82a21997c15181f37e241',10134251196,'2067f3a1e0ea7176c195d58e4834dfb4db9c99cb39bbd43ea714fbb7596db643','P202_YIELDCURVE_REGIME_REJECT']))
test('P202 guardrail grants no capital or trading authority',()=>assert.deepEqual(Object.values(boundaries),Array(Object.keys(boundaries).length).fill(false)))
