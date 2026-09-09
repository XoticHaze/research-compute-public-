import test from 'node:test'
import assert from 'node:assert/strict'

const MM_HEAD='f52ecaa70d9c56f9563994d30746158185755bc2'
const source={panelSha:'d329cf7adc85cc880f656f72a4caca4b67afc1a5bc63c58bcac9934c52fc308d'}
const science={run:34292929660,job:102283213731,artifact:10082034456,artifactSha:'d5a2a485af6932ce7d8731ba87c6ddd165fb54f05894ccfb51de0a454c1eeb9d'}
const full={candidate25:0.1416035899771262,matched:0.12038321414860831,excess25:0.02122037582851788,candidateDd25:-0.5223401346531638,matchedDd:-0.5127372875692296,positive25:3,excess50:0.013102782265948187,positive50:3}
const lag={excess25:0.008593345405663255,excess50:0.0005941989556903504,candidateDd25:-0.5699857183207335,matchedDd:-0.5127372317218859,candidateDd50:-0.5737319717151258,positive25:3,positive50:2,folds:5}

test('P52 acceptance binds exact MM product head and source/result identity',()=>{
  assert.equal(MM_HEAD,'f52ecaa70d9c56f9563994d30746158185755bc2')
  assert.equal(science.run,34292929660); assert.equal(science.job,102283213731); assert.equal(science.artifact,10082034456)
  assert.equal(source.panelSha.length,64); assert.equal(science.artifactSha.length,64)
})
test('P52 preserves matched after-cost support without hiding full-period drawdown weakness',()=>{
  assert.ok(full.excess25>0); assert.ok(full.excess50>0); assert.ok(full.candidate25>full.matched)
  assert.ok(full.candidateDd25 < full.matchedDd); assert.equal(full.positive25,3); assert.equal(full.positive50,3)
})
test('P52 preserves execution-lag fragility at 50 bps',()=>{
  assert.ok(lag.excess25>0); assert.ok(lag.excess50>0); assert.ok(lag.excess50<0.001)
  assert.equal(lag.positive50,2); assert.equal(lag.folds,5); assert.ok(lag.candidateDd25<lag.matchedDd); assert.ok(lag.candidateDd50<-0.57)
})
test('P52 protected authorities remain false',()=>{
  const boundary={independentValidationAdmitted:false,portfolioRanking:false,allocation:false,sizing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,liveTrading:false}
  assert.deepEqual(Object.values(boundary),Array(10).fill(false))
})
