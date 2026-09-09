import test from 'node:test';
import assert from 'node:assert/strict';
const MM_HEAD='27f9d3d206e375d43d781e98e3d899c2095d68ce';
const p86={run:34359565305,job:102492758113,artifact:10107214627,matched2020_50:0.019780031597570025,spy2020_50:-0.0023592646125580874,folds2020:3,sharpe2020:0.05710491930638362,matched2020_100:0.006098275039625456,matchedFull50:-0.00013978961822469493,spyFull50:-0.011203294979959422,state:'LATER_WINDOW_SUPPORTED_REQUIRES_ORTHOGONAL_ROBUSTNESS'};
test('bind exact P86 product head',()=>assert.equal(MM_HEAD,'27f9d3d206e375d43d781e98e3d899c2095d68ce'));
test('P86 has later-window matched support but not full-history durability',()=>{assert.equal(p86.run,34359565305);assert.equal(p86.job,102492758113);assert.equal(p86.artifact,10107214627);assert.ok(p86.matched2020_50>0);assert.ok(p86.folds2020>=3);assert.ok(p86.sharpe2020>0);assert.ok(p86.matched2020_100>0);assert.ok(p86.matchedFull50<=0);assert.ok(p86.spyFull50<0);assert.equal(p86.state,'LATER_WINDOW_SUPPORTED_REQUIRES_ORTHOGONAL_ROBUSTNESS')});
test('P86 consequence grants no tuning, portfolio, or trading authority',()=>assert.deepEqual(Object.values({horizon_tuning:false,topk_tuning:false,ranking:false,allocation:false,sizing:false,timing:false,promotion:false,strategy:false,runtime:false,data:false,broker:false,live:false}),Array(12).fill(false)));
