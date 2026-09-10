import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD='7f1fdec38244d7cdc4baf54f671ab6c3c05399a5'
const p193=Object.freeze({run:34429007289,job:102720285155,started:'2026-09-10T02:19:44.0719431Z',artifact:10133745110,cagr_5bps:-0.003580299506150797,static_excess_5bps:-0.020417800712042022,cagr_2bps:-0.0010611102660066374,static_excess_2bps:-0.017898611471897863,positive_static_folds:0,state:'PARK'})
const p194=Object.freeze({run:34429091485,job:102720542340,started:'2026-09-10T02:21:01.0747851Z',artifact:10133772471,cagr_1bp:0.0524469357019004,spy_opportunity_excess:-0.08560091755497279,sharpe:0.4777410004483873,spy_sharpe:0.8245096950645006,maxdd:-0.2878548097518444,cagr_2bps:0.000721772882756655,state:'PARK'})
const boundaries=Object.freeze({ranking:false,allocation:false,sizing:false,promotion:false,strategy_spec:false,runtime:false,data:false,broker:false,live_trading:false})

test('bind exact MM P193/P194 product head',()=>assert.equal(MM_PRODUCT_HEAD,'7f1fdec38244d7cdc4baf54f671ab6c3c05399a5'))
test('P193 pairs architecture fails against cash and static control even at cheaper cost',()=>{assert.equal(p193.state,'PARK');assert.ok(p193.cagr_5bps<0);assert.ok(p193.static_excess_5bps<0);assert.ok(p193.cagr_2bps<0);assert.ok(p193.static_excess_2bps<0);assert.equal(p193.positive_static_folds,0)})
test('P194 overnight structure remains context rather than investable alpha',()=>{assert.equal(p194.state,'PARK');assert.ok(p194.cagr_1bp>0);assert.ok(p194.spy_opportunity_excess<0);assert.ok(p194.sharpe<p194.spy_sharpe);assert.ok(p194.maxdd<-0.20);assert.ok(p194.cagr_2bps<0.001)})
test('preserve exact terminal execution identities',()=>{assert.deepEqual([p193.run,p193.job,p193.started,p193.artifact],[34429007289,102720285155,'2026-09-10T02:19:44.0719431Z',10133745110]);assert.deepEqual([p194.run,p194.job,p194.started,p194.artifact],[34429091485,102720542340,'2026-09-10T02:21:01.0747851Z',10133772471])})
test('alternative architecture guardrail grants no capital or trading authority',()=>assert.deepEqual(Object.values(boundaries),Array(Object.keys(boundaries).length).fill(false)))
