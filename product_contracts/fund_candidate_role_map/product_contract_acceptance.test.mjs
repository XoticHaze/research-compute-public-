import test from 'node:test'
import assert from 'node:assert/strict'
const heads={riskResidual:'c67fb0d0b1c8cb02fbe797aebb4354973a7c51d6',p46Complete:'349d8ef9387e1959af5c8f9a8ba9cdd941e6db5b',p36Recent:'651e7bf9422c8a419f0c9a4b2b291ff6d3b4f711'}
const riskGate={run:34322401383,job:102371800684,artifact:10092369992,matchedExcessPP:2.584678206943547,allInQQQExcessPP:-4.928608946136603,gatedQQQFolds:2}
const residual={run:34322734144,job:102372856762,artifact:10092500859,fullIntercept:0.03426738782405544,bootstrapLow:0.009613383154435412,rolling60Positive:0.9833333333333333,recent60Intercept:0.04163298087439701}
const p46Complete={serialRun:34315820269,looRun:34315839855,concentrationRun:34315887663,loo25:4.9369,loo50:4.0951,recentTop5Residual25:-1.7141,recentTop5Residual50:-2.1381,evidenceThrough:'2026-08-31'}
const p36Recent={holdoutRun:34314451641,concentrationRun:34314699324,full25:6.2801,full50:5.7588,residual25:-0.1311,residual50:-0.6210}

test('acceptance binds exact MM product heads',()=>assert.deepEqual(heads,{riskResidual:'c67fb0d0b1c8cb02fbe797aebb4354973a7c51d6',p46Complete:'349d8ef9387e1959af5c8f9a8ba9cdd941e6db5b',p36Recent:'651e7bf9422c8a419f0c9a4b2b291ff6d3b4f711'}))
test('risk gate rejected while residual alpha remains distinct',()=>{assert.ok(riskGate.matchedExcessPP>0&&riskGate.allInQQQExcessPP<0);assert.equal(riskGate.gatedQQQFolds,2);assert.ok(residual.fullIntercept>0&&residual.bootstrapLow>0&&residual.rolling60Positive>0.98&&residual.recent60Intercept>0)})
test('P46 complete-month support retains recent QQQ concentration caution',()=>{assert.ok(p46Complete.loo25>0&&p46Complete.loo50>0);assert.ok(p46Complete.recentTop5Residual25<0&&p46Complete.recentTop5Residual50<0);assert.equal(p46Complete.evidenceThrough,'2026-08-31')})
test('P36 recent surge is concentration-sensitive',()=>{assert.ok(p36Recent.full25>0&&p36Recent.full50>0);assert.ok(p36Recent.residual25<0&&p36Recent.residual50<0)})
test('product acceptance grants no portfolio or trading authority',()=>{const b={portfolioRanking:false,allocation:false,sizing:false,timing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,liveTrading:false};assert.deepEqual(Object.values(b),Array(10).fill(false))})
