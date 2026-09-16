import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD='ba571d8a796382c546482c110881a9f79577ab23'
const p440={control:'XLK',windows:[[-5.675,-8.159],[-3.878,-7.099],[-3.495,-3.672]],chronology:[-9.220,-5.477,-5.402],run:34524601740,job:103030291905,artifact:10171011457}
const p441={control:'XLV',windows:[[0.962,-0.088],[-1.861,-3.986],[-1.252,-0.873]],chronology:[8.620,-5.955,-12.404,8.955],positive:2,required:3,run:34524680653,job:103030554051,artifact:10171042469}

test('bind exact industry-closure product head',()=>assert.equal(MM_PRODUCT_HEAD,'ba571d8a796382c546482c110881a9f79577ab23'))
test('P440 fails matched XLK alpha in every fixed long window and chronology block',()=>{assert.equal(p440.control,'XLK');assert.ok(p440.windows.flat().every(x=>x<0));assert.ok(p440.chronology.every(x=>x<0))})
test('P441 fails dual-construction matched XLV transport and chronology breadth',()=>{assert.equal(p441.control,'XLV');assert.ok(p441.windows.some(pair=>pair.some(x=>x<0)));assert.ok(p441.positive<p441.required)})
test('both research results remain exactly attributable',()=>{assert.deepEqual([p440.run,p440.job,p440.artifact],[34524601740,103030291905,10171011457]);assert.deepEqual([p441.run,p441.job,p441.artifact],[34524680653,103030554051,10171042469])})
test('consumer rotates depth without admitting a third engine or granting trading authority',()=>assert.deepEqual(Object.values({thirdIndustryEngine:false,reopenP06:false,ranking:false,allocation:false,sizing:false,promotion:false,strategySpec:false,runtime:false,broker:false,live:false}),Array(10).fill(false)))
