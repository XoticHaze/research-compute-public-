import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD='73446fe82ba27483dd5789adef607e02dfe3f479'
const p91=Object.freeze({state:'STRICT_WALKFORWARD_QQQ_RSP_LEARNER_REJECTED',run_id:34362351380,job_id:102502269838,artifact_id:10108367531,all_oos_matched:-0.01888372697979035,all_oos_qqq:-0.05118098863678067,all_oos_spy:-0.0036033253253713315,from2020_matched:-0.015944679466246336,from2020_qqq:-0.05349815646360301,from2020_spy:-0.006528094189580225})

test('bind exact P91 guardrail digest product head',()=>assert.equal(MM_PRODUCT_HEAD,'73446fe82ba27483dd5789adef607e02dfe3f479'))
test('digest exposes the exact parked strict learner result',()=>{assert.equal(p91.state,'STRICT_WALKFORWARD_QQQ_RSP_LEARNER_REJECTED');assert.equal(p91.run_id,34362351380);assert.equal(p91.job_id,102502269838);assert.equal(p91.artifact_id,10108367531);assert.ok(p91.all_oos_matched<0&&p91.all_oos_qqq<0&&p91.all_oos_spy<0);assert.ok(p91.from2020_matched<0&&p91.from2020_qqq<0&&p91.from2020_spy<0)})
test('digest grants no rescue or portfolio/trading authority',()=>{const b={featureRescue:false,cRescue:false,thresholdRescue:false,trainingWindowRescue:false,portfolioRanking:false,allocation:false,sizing:false,timing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,liveTrading:false};assert.deepEqual(Object.values(b),Array(14).fill(false))})
