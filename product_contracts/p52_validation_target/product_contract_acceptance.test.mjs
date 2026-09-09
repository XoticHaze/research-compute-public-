import test from 'node:test'
import assert from 'node:assert/strict'

const MM_HEAD='ca5773740179280c451bf4f94c1726824ddac831'
const target={artifact:'d5a2a485af6932ce7d8731ba87c6ddd165fb54f05894ccfb51de0a454c1eeb9d',panel:'d329cf7adc85cc880f656f72a4caca4b67afc1a5bc63c58bcac9934c52fc308d',science:'fe1f946f64b4757880506a5a6d5686b9987f0547'}

test('P52 validation-target acceptance binds exact MM operator head',()=>assert.equal(MM_HEAD,'ca5773740179280c451bf4f94c1726824ddac831'))
test('operator target binds the exact science artifact, source panel, and science head',()=>{
  assert.equal(target.artifact.length,64); assert.equal(target.panel.length,64); assert.equal(target.science.length,40)
  assert.notEqual(target.artifact,target.panel)
})
test('stale target binding must remain fail closed',()=>{
  const supplied={...target,artifact:'0'.repeat(64)}
  assert.notEqual(supplied.artifact,target.artifact)
  assert.equal(supplied.panel,target.panel)
  assert.equal(supplied.science,target.science)
})
test('validation display grants no protected authority',()=>{
  const b={portfolioRanking:false,allocation:false,sizing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,liveTrading:false}
  assert.deepEqual(Object.values(b),Array(9).fill(false))
})
