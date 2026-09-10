import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD='5d3e0c1b7ca0fc63a5f918fb3d69c87de24bc972'
const p205={run:34431071287,job:102726521706,started:'2026-09-10T02:51:34Z',head:'a20568cf17b785e09bacb881a5337e749f803f6f',artifact:10134499361,sha:'aa13efcf3f0725bcd890cbe23f9e44d5faa6aedac0a30bcdff36728a84c05aa4',rmw2014:0.025549668874172177,rmw2020:0.03399493670886075,mom2014:0.02869668874172186,mom2020:0.03603037974683544}
const p206={run:34431227945,job:102726971165,started:'2026-09-10T02:54:15Z',head:'7b3900c6b4e1d2fbb630718617add7048fc6fc20',artifact:10134562011,sha:'d5e7f53c01c701ced7a534eda25eb1e4b66a0bb2f155ca6c5126b7f2012aaf9a',qmomMinusMtum:-362,qmomMinusIwf:-532,foldsMtum:1,foldsIwf:1}
const authority={ranking:false,allocation:false,sizing:false,promotion:false,strategy_spec:false,runtime:false,data:false,broker:false,live_trading:false}

test('bind exact product head',()=>assert.equal(MM_PRODUCT_HEAD,'5d3e0c1b7ca0fc63a5f918fb3d69c87de24bc972'))
test('academic factor signal remains present',()=>{assert.ok(p205.rmw2014>0);assert.ok(p205.rmw2020>0);assert.ok(p205.mom2014>0);assert.ok(p205.mom2020>0)})
test('QMOM live wrapper transport fails',()=>{assert.ok(p206.qmomMinusMtum<0);assert.ok(p206.qmomMinusIwf<0);assert.ok(p206.foldsMtum<3);assert.ok(p206.foldsIwf<3)})
test('preserve science identities',()=>{assert.equal(p205.run,34431071287);assert.equal(p205.job,102726521706);assert.equal(p205.artifact,10134499361);assert.equal(p206.run,34431227945);assert.equal(p206.job,102726971165);assert.equal(p206.artifact,10134562011)})
test('no capital or trading authority',()=>assert.deepEqual(Object.values(authority),Array(Object.keys(authority).length).fill(false)))
