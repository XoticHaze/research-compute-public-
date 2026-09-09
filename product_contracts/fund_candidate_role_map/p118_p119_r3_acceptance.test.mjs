import test from 'node:test'
import assert from 'node:assert/strict'
const MM_PRODUCT_HEAD='d06cdb030c2037267452e6dfc7aa78eded0b2a4f'
const p118={run:34381129042,job:102565967623,artifact:10115883610,matched:4.13,spy:-2.55,folds:2}
const p119={run:34381216208,job:102566260891,artifact:10115917924,matched:-0.60,spy:-2.05,folds:3}
test('bind replayed exact product head',()=>assert.equal(MM_PRODUCT_HEAD,'d06cdb030c2037267452e6dfc7aa78eded0b2a4f'))
test('P118 chronology and SPY gate fail',()=>{assert.ok(p118.matched>0&&p118.spy<0);assert.equal(p118.folds,2);assert.equal(p118.artifact,10115883610)})
test('P119 matched and SPY gates fail',()=>{assert.ok(p119.matched<0&&p119.spy<0);assert.equal(p119.folds,3);assert.equal(p119.artifact,10115917924)})
test('protected authority remains false',()=>assert.deepEqual(Object.values({ranking:false,allocation:false,sizing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,live:false}),Array(9).fill(false)))
