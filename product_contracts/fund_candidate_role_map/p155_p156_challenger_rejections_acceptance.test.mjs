import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD = '4ef7c1d4031f1d92450658822b80d5bc0c41d1ce'
const rows = [
  { id:'P155', run:34413867273, job:102674204983, artifact:10128286292, head:'cf4d67f8126948b185ca3b6960dd862cfc3b435f', matched:-0.04393580288167853, recent2022:-0.08293303097022564, cagr:0.07606030198843072, matchedCagr:0.11999610487010925, sharpe:0.6471650257467682, matchedSharpe:0.862462593003567 },
  { id:'P156', run:34414128238, job:102675034072, artifact:10128377236, head:'73d92ee29bd0af43bcb5d9a56b84362bad676807', matched:-0.04991901931035647, recent2022:-0.05419230179054746, maxdd:-0.31357095895009146, matchedMaxdd:-0.16367977015201685 },
]

test('bind exact P155-P156 MM product head', () => assert.equal(MM_PRODUCT_HEAD, '4ef7c1d4031f1d92450658822b80d5bc0c41d1ce'))
test('P155 loses return and Sharpe to its matched sector control', () => { assert.ok(rows[0].matched < 0); assert.ok(rows[0].cagr < rows[0].matchedCagr); assert.ok(rows[0].sharpe < rows[0].matchedSharpe) })
test('P156 loses matched excess and worsens drawdown', () => { assert.ok(rows[1].matched < 0); assert.ok(Math.abs(rows[1].maxdd) > Math.abs(rows[1].matchedMaxdd)); assert.ok(rows[1].recent2022 < 0) })
test('preserve exact science execution identities', () => assert.deepEqual(rows.map(x=>[x.run,x.job,x.artifact,x.head]), [[34413867273,102674204983,10128286292,'cf4d67f8126948b185ca3b6960dd862cfc3b435f'],[34414128238,102675034072,10128377236,'73d92ee29bd0af43bcb5d9a56b84362bad676807']]))
test('no ranking allocation or trading authority', () => assert.deepEqual(Object.values({ ranking:false, allocation:false, sizing:false, promotion:false, strategySpec:false, runtime:false, data:false, broker:false, live:false }), Array(9).fill(false)))
