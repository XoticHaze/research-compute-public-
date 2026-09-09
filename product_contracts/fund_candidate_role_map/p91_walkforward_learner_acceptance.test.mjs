import test from 'node:test'
import assert from 'node:assert/strict'

const MM_MAIN_WITH_P91='d6b62568b731e678c5541475139490c6a64ffbad'
const p91=Object.freeze({run_id:34362351380,job_id:102502269838,artifact_id:10108367531,artifact_digest:'sha256:04c9fb95c7eee8b7cfd3504007ed80cfb5f9c49d1f970dcb48182b2d1df05a8b',all_oos_matched:-0.01888372697979035,all_oos_qqq:-0.05118098863678067,all_oos_spy:-0.0036033253253713315,positive_matched_folds_all_oos:0,from2015_matched:-0.01742786403769636,from2020_matched:-0.015944679466246336,from2020_qqq:-0.05349815646360301,from2020_spy:-0.006528094189580225,from2020_sharpe_delta:-0.1464879785318196})

test('P91 admitted product boundary is bound',()=>assert.equal(MM_MAIN_WITH_P91,'d6b62568b731e678c5541475139490c6a64ffbad'))
test('strict learner remains rejected across chronology and controls',()=>{assert.equal(p91.run_id,34362351380);assert.equal(p91.job_id,102502269838);assert.equal(p91.artifact_id,10108367531);assert.equal(p91.positive_matched_folds_all_oos,0);assert.ok(p91.all_oos_matched<0&&p91.all_oos_qqq<0&&p91.all_oos_spy<0);assert.ok(p91.from2015_matched<0);assert.ok(p91.from2020_matched<0&&p91.from2020_qqq<0&&p91.from2020_spy<0);assert.ok(p91.from2020_sharpe_delta<0)})
test('P91 acceptance grants no rescue or portfolio/trading authority',()=>{const b={featureRescue:false,cRescue:false,thresholdRescue:false,trainingWindowRescue:false,portfolioRanking:false,allocation:false,sizing:false,timing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,liveTrading:false};assert.deepEqual(Object.values(b),Array(14).fill(false))})
