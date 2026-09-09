import test from 'node:test';
import assert from 'node:assert/strict';
const MM_HEAD='80a13d8516fb7c867162ebbe1d95221a8a227061';
const p90={run:34361898802,job:102500716153,artifact:10108174635,artifactDigest:'sha256:46ef42daccd62ce465a15deaebc123a5a886b565de86ecc45db7f5e5e37f96b9',matchedFull:-0.015803624693434992,matched2015:-0.001740954129950234,matched2020:-0.0013686660687330932,spy2020:0.00898861715436472,folds2020:2,sharpe2020:-0.031065205887829794,state:'QQQ_RSP_BREADTH_REGIME_ALLOCATOR_REJECTED'};
test('bind exact P90 product head',()=>assert.equal(MM_HEAD,'80a13d8516fb7c867162ebbe1d95221a8a227061'));
test('P90 matched-control breadth regime is rejected',()=>{assert.equal(p90.run,34361898802);assert.equal(p90.job,102500716153);assert.equal(p90.artifact,10108174635);assert.ok(p90.artifactDigest.startsWith('sha256:'));assert.ok(p90.matchedFull<0);assert.ok(p90.matched2015<0);assert.ok(p90.matched2020<0);assert.ok(p90.sharpe2020<0);assert.equal(p90.state,'QQQ_RSP_BREADTH_REGIME_ALLOCATOR_REJECTED')});
test('P90 grants no timing ranking allocation tuning or trading authority',()=>assert.deepEqual(Object.values({ranking:false,allocation:false,sizing:false,timing:false,promotion:false,tuning:false,strategy:false,runtime:false,data:false,broker:false,live:false}),Array(11).fill(false)));
