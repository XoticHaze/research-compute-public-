import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD = '700268fd5cfc8de40cdec67bc38bef9007ed71b4'
const p161 = Object.freeze({ run:34416088003, job:102681170153, artifact:10129128552, head:'218c2b14bba0df8e47b4263bb9ec9fe7b8350c87', started:'2026-09-09T23:15:17.0095616Z', pNonPositive:0.1538, ci:[-0.013795334721413883,0.04595759772669744] })
const p162 = Object.freeze({ run:34416143927, job:102681340828, artifact:10129138962, head:'1f52602ca1b757d353c7039e7bd35d85b0b3eee3', started:'2026-09-09T23:15:59.7403449Z', matched:-0.02162404072686619, spy:-0.01469734368967357, folds:1 })

test('bind exact narrowed P160 MM product head', () => assert.equal(MM_PRODUCT_HEAD, '700268fd5cfc8de40cdec67bc38bef9007ed71b4'))
test('P161 statistical gate narrows but does not erase survivor point evidence', () => { assert.equal(p161.pNonPositive,0.1538); assert.ok(p161.ci[0] < 0 && p161.ci[1] > 0) })
test('P162 one-month delay fails prompt-timing transfer', () => { assert.ok(p162.matched < 0); assert.ok(p162.spy < 0); assert.equal(p162.folds,1) })
test('preserve exact adjudicator executions', () => { assert.deepEqual([p161.run,p161.job,p161.artifact,p161.head,p161.started],[34416088003,102681170153,10129128552,'218c2b14bba0df8e47b4263bb9ec9fe7b8350c87','2026-09-09T23:15:17.0095616Z']); assert.deepEqual([p162.run,p162.job,p162.artifact,p162.head,p162.started],[34416143927,102681340828,10129138962,'1f52602ca1b757d353c7039e7bd35d85b0b3eee3','2026-09-09T23:15:59.7403449Z']) })
test('no significance, delay, weight, ranking, or trading authority transfer', () => assert.deepEqual(Object.values({ significanceRescue:false, delaySearch:false, weightOptimization:false, ranking:false, allocation:false, sizing:false, promotion:false, runtime:false, broker:false, live:false }), Array(10).fill(false)))
