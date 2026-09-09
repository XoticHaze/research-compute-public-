import test from 'node:test'
import assert from 'node:assert/strict'

const MM_HEAD='82cce5bd568f217b9ffdc97ea127c938a493b239'
const rows=[
  {id:'P46',role:'CURRENT_CROSS_ASSET_FUND_CANDIDATE'},
  {id:'P64',role:'DIVERSIFICATION_SLEEVE_EVIDENCE',matched25:0.023073173358661325,matched50:0.014621772350719597,qqq25:-0.03383249594227222},
  {id:'P57',role:'CORRECTED_LINEAGE_AND_FRAGILITY_CONTEXT',matched25:0.031035627736038407,matched50:0.023473864767538766,qqq25:-0.03781202672387063},
  {id:'P52',role:'DISTINCT_INDUSTRY_CANDIDATE_VALIDATION_OPEN',matched25:0.02122037582851788,matched50:0.013102782265948187,lag50:0.0005941989556903504,lagFolds:2,totalFolds:5},
]

test('role-map acceptance binds exact MM operator head',()=>assert.equal(MM_HEAD,'82cce5bd568f217b9ffdc97ea127c938a493b239'))
test('role map keeps surviving evidence in distinct non-ranking roles',()=>{
  assert.deepEqual(rows.map(r=>r.id),['P46','P64','P57','P52'])
  assert.equal(new Set(rows.map(r=>r.role)).size,4)
  assert.ok(rows[1].matched25>0&&rows[1].matched50>0&&rows[1].qqq25<0)
  assert.ok(rows[2].matched25>0&&rows[2].matched50>0&&rows[2].qqq25<0)
  assert.ok(rows[3].matched25>0&&rows[3].matched50>0&&rows[3].lag50<0.001&&rows[3].lagFolds<rows[3].totalFolds/2+0.5)
})
test('co-location grants no portfolio or trading authority',()=>{
  const boundary={portfolioRanking:false,allocation:false,sizing:false,timing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,liveTrading:false}
  assert.deepEqual(Object.values(boundary),Array(10).fill(false))
})
