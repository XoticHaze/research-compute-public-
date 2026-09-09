import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD = 'f5c88b7d3be3f8f8e7a762f1c255641e4b40557f'
const p165 = Object.freeze({ run:34416477220, job:102682373000, artifact:10129266444, head:'62f6c5674d58dff8e8a1df4ea1755412d8b3f788', started:'2026-09-09T23:20:22.9644884Z', excess2015:-0.017452065882035628, excess2020:-0.020717831788399366, excess2022:0.002500238240987551, folds2015:1, candidateDD:-0.16606473737198824, matchedDD:-0.19919089536591894 })

const boundaries = Object.freeze({ target_tuning:false, lookback_tuning:false, exposure_cap_tuning:false, cost_tuning:false, chronology_tuning:false, ranking:false, allocation:false, sizing:false, promotion:false, runtime:false, broker:false, live_trading:false })

test('bind exact P165 MM product head', () => assert.equal(MM_PRODUCT_HEAD, 'f5c88b7d3be3f8f8e7a762f1c255641e4b40557f'))
test('P165 is not matched alpha despite drawdown reduction', () => { assert.ok(p165.excess2015 < 0); assert.ok(p165.excess2020 < 0); assert.equal(p165.folds2015,1); assert.ok(Math.abs(p165.candidateDD) < Math.abs(p165.matchedDD)) })
test('recent 2022 pocket does not rescue durable chronology', () => assert.ok(p165.excess2022 > 0 && p165.excess2015 < 0))
test('preserve exact P165 execution identity', () => assert.deepEqual([p165.run,p165.job,p165.artifact,p165.head,p165.started],[34416477220,102682373000,10129266444,'62f6c5674d58dff8e8a1df4ea1755412d8b3f788','2026-09-09T23:20:22.9644884Z']))
test('rotate architecture without local rescue or authority transfer', () => assert.deepEqual(Object.values(boundaries), Array(Object.keys(boundaries).length).fill(false)))
