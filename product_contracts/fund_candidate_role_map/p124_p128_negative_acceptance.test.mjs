import test from 'node:test'
import assert from 'node:assert/strict'
const MM_PRODUCT_HEAD='6fa3ae95af25ec79722323997dea28b7f36d4446'
const rows=[
{id:'P124',run:34382399512,job:102570210078,artifact:10116382890,decision:'P124_SECTOR_REVERSAL_NOT_SUPPORTED'},
{id:'P125',run:34382609389,job:102570916697,artifact:10116458962,decision:'P125_SPY_OVERNIGHT_NOT_SUPPORTED'},
{id:'P126',run:34382738767,job:102571337087,artifact:10116512866,decision:'P126_BREADTH_GATE_NOT_SUPPORTED'},
{id:'P127',run:34383169539,job:102572762167,artifact:10116684225,decision:'P127_INVERSE_VOL_MULTI_ASSET_NOT_SUPPORTED'},
{id:'P128',run:34383263555,job:102573072269,artifact:10116707903,decision:'P128_TIMESERIES_TREND_NOT_SUPPORTED'}]
test('bind exact P124-P128 product head',()=>assert.equal(MM_PRODUCT_HEAD,'6fa3ae95af25ec79722323997dea28b7f36d4446'))
test('science-owned decisions remain fail closed',()=>{assert.equal(rows.length,5);for(const r of rows){assert.ok(r.run>0&&r.job>0&&r.artifact>0);assert.ok(r.decision.endsWith('NOT_SUPPORTED'))}})
test('do not promote P124 from headline metrics alone',()=>assert.equal(rows[0].decision,'P124_SECTOR_REVERSAL_NOT_SUPPORTED'))
test('protected authority remains false',()=>assert.deepEqual(Object.values({ranking:false,allocation:false,sizing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,live:false}),Array(9).fill(false)))
