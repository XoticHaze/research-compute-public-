import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD = 'cb063174fb0118e5b0fb82f967f663d3e01ab742'
const p189 = Object.freeze({run:34428640732,job:102719168350,started:'2026-09-10T02:14:15.3114258Z',artifact:10133611524,matched_excess_2015:0.015367403175660765,matched_excess_2020:-0.002326460578370604,positive_folds_2020:2,maxdd:-0.2572904590755435,matched_maxdd:-0.23052625101930846,state:'PARK'})
const p190 = Object.freeze({run:34428685350,job:102719300584,started:'2026-09-10T02:14:55.3993028Z',artifact:10133628656,matched_excess_2015:-0.029242437827194045,spy_excess_2015:-0.007021016740196728,positive_folds:0,sharpe:0.8938890658076144,matched_sharpe:1.059114280420538,maxdd:-0.1975403605544599,matched_maxdd:-0.2305261305496451,state:'PARK'})
const boundaries = Object.freeze({ranking:false,allocation:false,sizing:false,promotion:false,strategy_spec:false,runtime:false,data:false,broker:false,live_trading:false})

test('bind exact MM P189/P190 product head',()=>assert.equal(MM_PRODUCT_HEAD,'cb063174fb0118e5b0fb82f967f663d3e01ab742'))
test('P189 positive old-period alpha does not override failed risk and persistence gates',()=>{assert.equal(p189.state,'PARK');assert.ok(p189.matched_excess_2015>0);assert.ok(p189.matched_excess_2020<0);assert.ok(p189.positive_folds_2020<3);assert.ok(p189.maxdd<p189.matched_maxdd)})
test('P190 drawdown shaping does not masquerade as alpha',()=>{assert.equal(p190.state,'PARK');assert.ok(p190.maxdd>p190.matched_maxdd);assert.ok(p190.matched_excess_2015<0);assert.ok(p190.spy_excess_2015<0);assert.equal(p190.positive_folds,0);assert.ok(p190.sharpe<p190.matched_sharpe)})
test('preserve exact terminal execution identities',()=>{assert.deepEqual([p189.run,p189.job,p189.started,p189.artifact],[34428640732,102719168350,'2026-09-10T02:14:15.3114258Z',10133611524]);assert.deepEqual([p190.run,p190.job,p190.started,p190.artifact],[34428685350,102719300584,'2026-09-10T02:14:55.3993028Z',10133628656])})
test('park guardrail grants no capital or trading authority',()=>assert.deepEqual(Object.values(boundaries),Array(Object.keys(boundaries).length).fill(false)))
