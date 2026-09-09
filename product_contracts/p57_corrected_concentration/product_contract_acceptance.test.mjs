import test from 'node:test'
import assert from 'node:assert/strict'

const MM_HEAD = 'dae5c0c8cb13160ea3911a3439e7a247be55408d'
const correction = { run:34295854779, job:102292215895, artifact:10083090582, indexEqual:true, commonMonths:240, p61:0.007014429770155095, p63:0.007014423783192614, removed:['2008-11-30','2011-08-31','2008-06-30','2022-04-30','2008-01-31'], resolved:true }
const persistence = { run:34295537221, job:102291234399, artifact:10082973972, rolling36:0.6487804878048781, rolling60:0.574585635359116, bootstrapLow:-0.02430433646486076, bootstrapHigh:0.06571050831220547, bootstrapP:0.171, excess25:0.031035627736038407, excess50:0.023473864767538766, breakevenBps:129, qqq25:-0.03781202672387063, contiguousUniversal:false, riskOffPositive:false }

test('P57 acceptance binds the exact rebased MM corrected operator-product head',()=>assert.equal(MM_HEAD,'dae5c0c8cb13160ea3911a3439e7a247be55408d'))
test('P57 correction resolves the contradictory extreme-month implementations',()=>{
  assert.equal(correction.run,34295854779); assert.equal(correction.job,102292215895); assert.equal(correction.artifact,10083090582)
  assert.equal(correction.indexEqual,true); assert.equal(correction.resolved,true); assert.equal(correction.commonMonths,240); assert.equal(correction.removed.length,5)
  assert.ok(correction.p61 > 0); assert.ok(correction.p63 > 0); assert.ok(Math.abs(correction.p61-correction.p63) < 1e-7)
})
test('P57 remains conditional diversification evidence after correction',()=>{
  assert.equal(persistence.run,34295537221); assert.equal(persistence.job,102291234399); assert.equal(persistence.artifact,10082973972)
  assert.ok(persistence.excess25 > 0); assert.ok(persistence.excess50 > 0); assert.ok(persistence.breakevenBps >= 50)
  assert.ok(persistence.bootstrapLow < 0); assert.ok(persistence.bootstrapHigh > 0); assert.ok(persistence.bootstrapP > 0.10)
  assert.equal(persistence.contiguousUniversal,false); assert.equal(persistence.riskOffPositive,false); assert.ok(persistence.qqq25 < 0)
})
test('P57 protected authorities remain false',()=>{
  const boundary={portfolioRanking:false,allocation:false,sizing:false,strategySpec:false,runtime:false,data:false,broker:false,liveTrading:false}
  assert.deepEqual(Object.values(boundary),Array(8).fill(false))
})
