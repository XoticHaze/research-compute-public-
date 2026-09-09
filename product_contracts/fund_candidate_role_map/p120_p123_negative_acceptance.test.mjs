import test from 'node:test'
import assert from 'node:assert/strict'
const MM_PRODUCT_HEAD='f5340fff7e9b77d6280f2559c7ad43d30c6aeb74'
const rows=[
{run:34381577473,job:102567465443,artifact:10116057439,matched:2.80,spy:-11.96,folds:3},
{run:34381860517,job:102568407336,artifact:10116170289,matched:-0.07,spy:-12.36,folds:2},
{run:34382204861,job:102569559993,artifact:10116303257,matched:-5.44,spy:-7.45,folds:0},
{run:34382270520,job:102569779397,artifact:10116351006,matched:-2.17,spy:-6.89,folds:2}]
test('bind exact P120-P123 product head',()=>assert.equal(MM_PRODUCT_HEAD,'f5340fff7e9b77d6280f2559c7ad43d30c6aeb74'))
test('all four exact results remain non-promotional',()=>{assert.equal(rows.length,4);assert.ok(rows[0].matched>0&&rows[0].spy<0);for(const r of rows.slice(1))assert.ok(r.matched<0&&r.spy<0);assert.equal(rows[2].folds,0)})
test('protected authority remains false',()=>assert.deepEqual(Object.values({ranking:false,allocation:false,sizing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,live:false}),Array(9).fill(false)))
