import test from 'node:test'
import assert from 'node:assert/strict'
const MM_PRODUCT_HEAD='2519a6d444622cdc5df44e8e359ae5f8517ffacc'
const rows=[
{id:'P46',run:34384151359,artifact:10117040207,matched_gap_pp:4.1851444892579304,qqq_gap_pp:-2.7385451598155974,vector:'a86493347faf3f64567c490eaa514761912557da5db029cdb13461790578ac5b'},
{id:'P64',run:34384489441,artifact:10117167468,matched_gap_pp:-0.22704530545865076,qqq_gap_pp:-5.785686137017265,vector:'16c823cca3f620463204b2a439f8400f0f51bb6c102b3286ba207c235a98f821'}]
test('bind exact operator review head',()=>assert.equal(MM_PRODUCT_HEAD,'2519a6d444622cdc5df44e8e359ae5f8517ffacc'))
test('preserve exact P46 P64 contrast',()=>{assert.equal(rows.length,2);assert.ok(rows[0].matched_gap_pp>0);assert.ok(rows[1].matched_gap_pp<0);for(const r of rows){assert.ok(r.qqq_gap_pp<0);assert.equal(r.vector.length,64)}})
test('stage only science-owned fixed utility chronology consumer',()=>assert.deepEqual(Object.values({ranking:false,allocation:false,sizing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,live:false}),Array(9).fill(false)))
