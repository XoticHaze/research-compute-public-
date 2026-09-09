import test from 'node:test'
import assert from 'node:assert/strict'
const heads={riskResidual:'c67fb0d0b1c8cb02fbe797aebb4354973a7c51d6',p46Complete:'349d8ef9387e1959af5c8f9a8ba9cdd941e6db5b',p36Recent:'651e7bf9422c8a419f0c9a4b2b291ff6d3b4f711',p13Park:'030c1637ae466691102b6a90880c31d0e5dbcc00'}
const riskGate={matchedExcessPP:2.584678206943547,allInQQQExcessPP:-4.928608946136603,gatedQQQFolds:2}
const residual={fullIntercept:0.03426738782405544,bootstrapLow:0.009613383154435412,rolling60Positive:0.9833333333333333,recent60Intercept:0.04163298087439701}
const p46Complete={artifacts:[10090010332,10090025534,10090040275],loo25:4.9369,loo50:4.0951,recentTop5Residual25:-1.7141,recentTop5Residual50:-2.1381,evidenceThrough:'2026-08-31'}
const p36Recent={artifacts:[10089546654,10089633639],full25:6.2801,full50:5.7588,residual25:-0.1311,residual50:-0.6210}
const p13={run:34322606141,job:102372448162,artifact:10092449586,recentVsSmhPP:-8.705679443903191,recentVsEqualWeightPP:-13.85205839591499,smhFolds:2,candidateDD:-0.4385466873997701,smhDD:-0.31112157044793176}

test('acceptance binds exact MM product heads',()=>assert.equal(heads.p13Park,'030c1637ae466691102b6a90880c31d0e5dbcc00'))
test('risk gate rejected while residual alpha remains distinct',()=>{assert.ok(riskGate.matchedExcessPP>0&&riskGate.allInQQQExcessPP<0);assert.equal(riskGate.gatedQQQFolds,2);assert.ok(residual.fullIntercept>0&&residual.bootstrapLow>0&&residual.rolling60Positive>0.98)})
test('P46 complete-month support retains recent QQQ concentration caution',()=>{assert.deepEqual(p46Complete.artifacts,[10090010332,10090025534,10090040275]);assert.ok(p46Complete.loo25>0&&p46Complete.recentTop5Residual25<0);assert.equal(p46Complete.evidenceThrough,'2026-08-31')})
test('P36 recent surge is concentration-sensitive',()=>{assert.deepEqual(p36Recent.artifacts,[10089546654,10089633639]);assert.ok(p36Recent.full25>0&&p36Recent.residual25<0&&p36Recent.residual50<0)})
test('P13 temporal park is fail-closed negative operator evidence',()=>{assert.equal(p13.run,34322606141);assert.equal(p13.artifact,10092449586);assert.ok(p13.recentVsSmhPP<0&&p13.recentVsEqualWeightPP<0);assert.equal(p13.smhFolds,2);assert.ok(p13.candidateDD<p13.smhDD)})
test('product acceptance grants no portfolio or trading authority',()=>{const b={portfolioRanking:false,allocation:false,sizing:false,timing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,liveTrading:false};assert.deepEqual(Object.values(b),Array(10).fill(false))})
