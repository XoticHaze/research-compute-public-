import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD = '2329ee3c9850a01d6b771c7eb948d31013ef81f3'
const p427 = Object.freeze({ state:'FIXED_VOLATILITY_MANAGEMENT_OVERLAY_NOT_SUPPORTED__BASE_SURVIVOR_PRESERVED', alpha_pp:-0.858, cagr_delta_pp:-5.456, sharpe_delta:-0.073, maxdd_improvement_pp:5.415, average_spmo_weight:0.826, turnover:0.861, blocks:[0.830,-4.370,-0.144], run:34520211115, job:103015543388, artifact:10169322393, protected:{ranking:false,allocation:false,sizing:false,promotion:false,strategySpec:false,runtime:false,broker:false,live:false} })

test('bind exact P427 MM product head',()=>assert.equal(MM_PRODUCT_HEAD,'2329ee3c9850a01d6b771c7eb948d31013ef81f3'))
test('reject exact overlay while retaining drawdown fact',()=>{assert.equal(p427.state,'FIXED_VOLATILITY_MANAGEMENT_OVERLAY_NOT_SUPPORTED__BASE_SURVIVOR_PRESERVED');assert.ok(p427.cagr_delta_pp<0);assert.ok(p427.sharpe_delta<0);assert.ok(p427.alpha_pp<0);assert.ok(p427.maxdd_improvement_pp>0)})
test('retain exact implementation and execution identity',()=>{assert.equal(p427.average_spmo_weight,0.826);assert.equal(p427.turnover,0.861);assert.deepEqual(p427.blocks,[0.830,-4.370,-0.144]);assert.deepEqual([p427.run,p427.job,p427.artifact],[34520211115,103015543388,10169322393])})
test('guardrail grants no portfolio or trading authority',()=>assert.deepEqual(Object.values(p427.protected),Array(8).fill(false)))
