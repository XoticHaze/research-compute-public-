import test from 'node:test'
import assert from 'node:assert/strict'
const MM_PRODUCT_HEAD='68d3dc01d7fd164cf8ba7455a8c9db0b4069c353'
const r={run:34385713931,job:102581324155,artifact:10117618045,head:'d5e1736aa3491e05933450e658f440ebad290cc9',decision:'P46_MARKET_CONDITIONAL_ALPHA_BOOTSTRAP_INCONCLUSIVE',y2015:{qqqAlpha:0.0588,spyAlpha:0.0482,qqqMean:0.1822,spyMean:0.1820},y2020:{qqqAlpha:0.0526,spyAlpha:0.0442,qqqMean:0.1262,spyMean:0.1172}}
test('bind exact P46 bootstrap product head',()=>assert.equal(MM_PRODUCT_HEAD,'68d3dc01d7fd164cf8ba7455a8c9db0b4069c353'))
test('preserve inconclusive cross-control uncertainty',()=>{assert.equal(r.decision,'P46_MARKET_CONDITIONAL_ALPHA_BOOTSTRAP_INCONCLUSIVE');assert.ok(r.y2015.qqqAlpha>.05&&r.y2015.spyAlpha<.05);assert.ok(r.y2020.qqqAlpha>.05&&r.y2020.spyAlpha<.05);assert.ok(r.y2015.qqqMean>.18&&r.y2020.spyMean>.11)})
test('no significance-threshold rescue or portfolio authority',()=>assert.deepEqual(Object.values({ranking:false,allocation:false,sizing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,live:false}),Array(9).fill(false)))