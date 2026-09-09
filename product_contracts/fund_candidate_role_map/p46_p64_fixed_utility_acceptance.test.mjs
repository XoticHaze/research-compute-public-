import test from 'node:test'
import assert from 'node:assert/strict'
const MM_PRODUCT_HEAD='9e852910f6280525854140a7a05b80d1779302bc'
const r={run:34384647065,job:102577757443,artifact:10117232863,head:'6e2ccecd37322f907bae07f5c9c45d5de28f9ea5',decision:'P46_P64_FIXED_UTILITY_NOT_SUPPORTED',y2015:{matched:0.00015499825864129235,qqq:-0.07344807306856183,positiveMatched:2,positiveQqq:0},y2020:{matched:0.015327206068237675,qqq:-0.05449644164368417,positiveMatched:3,positiveQqq:0},y2022:{matched:0.012881521162223075,qqq:-0.016902874401980572,positiveMatched:3,positiveQqq:2}}
test('bind exact fixed utility product head',()=>assert.equal(MM_PRODUCT_HEAD,'9e852910f6280525854140a7a05b80d1779302bc'))
test('science decision remains not supported',()=>{assert.equal(r.decision,'P46_P64_FIXED_UTILITY_NOT_SUPPORTED');assert.equal(r.y2015.positiveMatched,2);assert.equal(r.y2015.positiveQqq,0);assert.equal(r.y2020.positiveQqq,0);assert.equal(r.y2022.positiveQqq,2)})
test('no nearby rescue or portfolio authority',()=>assert.deepEqual(Object.values({ranking:false,allocation:false,sizing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,live:false}),Array(9).fill(false)))
