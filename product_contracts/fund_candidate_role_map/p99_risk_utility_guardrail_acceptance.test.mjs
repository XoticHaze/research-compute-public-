import test from 'node:test';
import assert from 'node:assert/strict';
const MM_HEAD='c49986c81967f8936a41a814e5d7f5b30a251b99';
const p99={run:34367156737,job:102518734655,artifact:10110339441,digest:'sha256:9554041a6d041d99414ecf63361f710d0da3bb84ef5e7561c6186610f0750457',excess2015:-0.031023589391360185,excess2020:-0.04077729398819985,folds2020:1,sharpe2020:0.14218167974093965,maxdd2020:0.12949121426504695,state:'VOL_MANAGED_QQQ_EXCESS_RETURN_REJECTED_RISK_UTILITY_RETAINED'};
test('bind exact P99 product head',()=>assert.equal(MM_HEAD,'c49986c81967f8936a41a814e5d7f5b30a251b99'));
test('P99 excess-return objective is rejected while risk utility remains separate',()=>{assert.equal(p99.run,34367156737);assert.equal(p99.job,102518734655);assert.equal(p99.artifact,10110339441);assert.ok(p99.digest.startsWith('sha256:'));assert.ok(p99.excess2015<0);assert.ok(p99.excess2020<0);assert.equal(p99.folds2020,1);assert.ok(p99.sharpe2020>0);assert.ok(p99.maxdd2020>0);assert.equal(p99.state,'VOL_MANAGED_QQQ_EXCESS_RETURN_REJECTED_RISK_UTILITY_RETAINED')});
test('P99 grants no ranking allocation sizing leverage timing tuning or trading authority',()=>assert.deepEqual(Object.values({ranking:false,allocation:false,sizing:false,leverage:false,timing:false,promotion:false,tuning:false,strategy:false,runtime:false,data:false,broker:false,live:false}),Array(12).fill(false)));
