import test from 'node:test'
import assert from 'node:assert/strict'
const MM_PRODUCT_HEAD='8079337d38bd382cf302704186ca813e2c0ff571'
const r={run:34390444881,job:102597170517,artifact:10119412492,head:'b451ab1e5d8c22d563bb7f48f93c3dddd8f9cc3b',cagr:.1147,matched:.1340,spy:.1380,foldWins:2,totalFolds:5,meanSpyExposure:.96,noSearch:true}
test('bind exact P138 product head',()=>assert.equal(MM_PRODUCT_HEAD,'8079337d38bd382cf302704186ca813e2c0ff571'))
test('learned timing fails matched value despite causal no-search design',()=>{assert.ok(r.cagr<r.matched);assert.ok(r.cagr<r.spy);assert.equal(r.foldWins,2);assert.equal(r.totalFolds,5);assert.equal(r.meanSpyExposure,.96);assert.equal(r.noSearch,true)})
test('preserve exact execution identity',()=>assert.deepEqual([r.run,r.job,r.artifact,r.head],[34390444881,102597170517,10119412492,'b451ab1e5d8c22d563bb7f48f93c3dddd8f9cc3b']))
test('no portfolio or trading authority',()=>assert.deepEqual(Object.values({ranking:false,allocation:false,sizing:false,leverage:false,timing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,live:false}),Array(11).fill(false)))
