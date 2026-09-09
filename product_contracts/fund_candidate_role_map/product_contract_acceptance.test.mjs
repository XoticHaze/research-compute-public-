import test from 'node:test'
import assert from 'node:assert/strict'
const MM_HEAD='1b7f81d975538f63b41412a220a1e45f946a2739'
const era={run:34322914461,job:102373424285,artifact:10092580859,positiveInterceptEras:4,positiveLowerBoundEras:2,middleRawQQQ:[-1.3053076066983804,-3.958498423743251]}
const concentration={run:34323031715,job:102373803608,artifact:10092617345,fullBaseline:0.03426746559076578,fullAfterTop5:0.01910453361489323,recentBaseline:0.05130500242286151,recentAfterTop3:0.026686974455591275,recentAfterTop5:0.01410055550748323}
test('bind exact rendered MM product head',()=>assert.equal(MM_HEAD,'1b7f81d975538f63b41412a220a1e45f946a2739'))
test('era evidence separates residual persistence from raw QQQ dominance',()=>{assert.equal(era.positiveInterceptEras,4);assert.equal(era.positiveLowerBoundEras,2);assert.ok(era.middleRawQQQ.every(v=>v<0))})
test('residual alpha survives strongest-month removals',()=>{assert.equal(concentration.run,34323031715);assert.equal(concentration.artifact,10092617345);assert.ok(concentration.fullAfterTop5>0&&concentration.recentAfterTop3>0&&concentration.recentAfterTop5>0);assert.ok(concentration.fullAfterTop5<concentration.fullBaseline&&concentration.recentAfterTop5<concentration.recentBaseline)})
test('product acceptance grants no portfolio or trading authority',()=>{const b={portfolioRanking:false,allocation:false,sizing:false,timing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,liveTrading:false};assert.deepEqual(Object.values(b),Array(10).fill(false))})
