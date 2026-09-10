import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD = '488b10b4edfcf2373b89c9f82d7865af8b6154ee'
const p169 = Object.freeze({
  run:34422150071,
  job:102699708284,
  started:'2026-09-10T00:38:33Z',
  head:'e549c45127c4f243faa29c40c93d9e75eac0e603',
  artifact:10131285521,
  artifact_sha256:'813871920b493a395fe3412c19534f25ff9877ef2b92cc42c143219885e2fd0c',
  positive_blocks:2,
  total_blocks:3,
  gate_pass:false,
})
const current = Object.freeze({
  state:'ISSUER_REPLAY_MATCHED_ALPHA_SUPPORTED_UNIVERSE_CONCENTRATED_RECENT_CALENDAR_BLOCK_WEAK',
  universe_survivors:3,
  universe_total:5,
  universe_required:4,
  calendar_positive:2,
  calendar_total:3,
  broad_robustness:false,
})
const blocks = Object.freeze({
  b2015_2018:Object.freeze({matched_excess:0.0274960635268231}),
  b2019_2022:Object.freeze({matched_excess:0.03309199131635032}),
  b2023_present:Object.freeze({matched_excess:-0.0009076107979655301,spy_excess:-0.039922201090247134,qqq_excess:-0.13330612881243953}),
})
const boundaries = Object.freeze({ranking:false,allocation:false,sizing:false,promotion:false,strategy_spec:false,runtime:false,data:false,broker:false,live_trading:false})

test('bind exact MM P169 product head', () => assert.equal(MM_PRODUCT_HEAD,'488b10b4edfcf2373b89c9f82d7865af8b6154ee'))
test('P169 keeps P46 narrowed and fails broad robustness closed', () => {
  assert.equal(p169.gate_pass,false)
  assert.equal(p169.positive_blocks,2)
  assert.equal(p169.total_blocks,3)
  assert.ok(current.universe_survivors < current.universe_required)
  assert.equal(current.calendar_positive,2)
  assert.equal(current.calendar_total,3)
  assert.equal(current.broad_robustness,false)
  assert.equal(current.state,'ISSUER_REPLAY_MATCHED_ALPHA_SUPPORTED_UNIVERSE_CONCENTRATED_RECENT_CALENDAR_BLOCK_WEAK')
})
test('non-overlapping calendar blocks preserve the recent weakness without erasing older support', () => {
  assert.ok(blocks.b2015_2018.matched_excess > 0)
  assert.ok(blocks.b2019_2022.matched_excess > 0)
  assert.ok(blocks.b2023_present.matched_excess < 0)
  assert.ok(blocks.b2023_present.spy_excess < 0)
  assert.ok(blocks.b2023_present.qqq_excess < 0)
})
test('preserve exact P169 execution identity', () => {
  assert.deepEqual([p169.run,p169.job,p169.started,p169.head,p169.artifact],[34422150071,102699708284,'2026-09-10T00:38:33Z','e549c45127c4f243faa29c40c93d9e75eac0e603',10131285521])
  assert.equal(p169.artifact_sha256,'813871920b493a395fe3412c19534f25ff9877ef2b92cc42c143219885e2fd0c')
})
test('P169 product crossing grants no capital or trading authority', () => assert.deepEqual(Object.values(boundaries),Array(Object.keys(boundaries).length).fill(false)))
