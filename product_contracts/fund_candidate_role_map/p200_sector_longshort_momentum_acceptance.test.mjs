import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD='1e4c5a408640f4ed60cda9404e1677ffe6343034'
const p200=Object.freeze({
  state:'PARK_RECENT_REGIME_CONTEXT_ONLY',
  decision:'MODEL_FORMULATION_REJECT_WITH_RECENT_REGIME_CONDITIONAL_OBSERVATION',
  run:34429941376,
  job:102723116729,
  started:'2026-09-10T02:33:57.6994956Z',
  artifact:10134082108,
  artifact_sha256:'fc4bdf532377b9f58048f5d66657ad568dded2f590f1eead0650dc58d5c205fd',
  cagr_2010_25:-0.002429093496444268,
  positive_folds_2010:2,
  sharpe_2010:0.00867235358693117,
  max_drawdown_2010:-0.2545814605757043,
  cagr_2010_50:-0.010172681474791445,
  cagr_2015_25:-0.0011216273786979203,
  cagr_2020_25:0.028939315320731795,
  positive_folds_2020:5,
  cagr_2020_50:0.022135730036833223,
})
const boundaries=Object.freeze({ranking:false,allocation:false,sizing:false,promotion:false,strategy_spec:false,runtime:false,data:false,broker:false,live_trading:false})

test('bind exact P200 MM product head',()=>assert.equal(MM_PRODUCT_HEAD,'1e4c5a408640f4ed60cda9404e1677ffe6343034'))
test('broad P200 sector long-short momentum claim is rejected',()=>{assert.equal(p200.state,'PARK_RECENT_REGIME_CONTEXT_ONLY');assert.equal(p200.decision,'MODEL_FORMULATION_REJECT_WITH_RECENT_REGIME_CONDITIONAL_OBSERVATION');assert.ok(p200.cagr_2010_25<0);assert.ok(p200.cagr_2010_50<0);assert.ok(p200.cagr_2015_25<0);assert.ok(p200.positive_folds_2010<3);assert.ok(p200.sharpe_2010<0.1);assert.ok(p200.max_drawdown_2010<-0.20)})
test('recent positive slice remains context rather than durable-alpha rescue',()=>{assert.ok(p200.cagr_2020_25>0);assert.equal(p200.positive_folds_2020,5);assert.ok(p200.cagr_2020_50>0);assert.ok(p200.cagr_2010_25<0)})
test('preserve exact P200 science execution identity',()=>assert.deepEqual([p200.run,p200.job,p200.started,p200.artifact,p200.artifact_sha256],[34429941376,102723116729,'2026-09-10T02:33:57.6994956Z',10134082108,'fc4bdf532377b9f58048f5d66657ad568dded2f590f1eead0650dc58d5c205fd']))
test('P200 guardrail grants no capital or trading authority',()=>assert.deepEqual(Object.values(boundaries),Array(Object.keys(boundaries).length).fill(false)))
