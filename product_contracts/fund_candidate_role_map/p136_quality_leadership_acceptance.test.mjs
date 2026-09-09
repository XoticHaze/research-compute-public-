import test from 'node:test'
import assert from 'node:assert/strict'
const MM_PRODUCT_HEAD='4ad3e30a79397aa73a46a6637c0e414e667f9dac'
const r={repository:'XoticHaze/research-compute-public-',workflow:'.github/workflows/p136-quality-leadership-qual-spy-r1.yml',run:34387359361,job:102586891128,artifact:10118214840,artifactDigest:'sha256:6e22afd2b8660d7f95763c200e0857cd1086092cce901c03716219690b2aa828',head:'f2099d2ca7fb406536ef0caf589b3cdf7d304400',decision:'REJECT_P136_R1_AND_ROTATE_NO_PARAMETER_RESCUE',matched50:-.0075,spy50:-.0105}
test('bind exact P136 product head',()=>assert.equal(MM_PRODUCT_HEAD,'4ad3e30a79397aa73a46a6637c0e414e667f9dac'))
test('preserve exact rejection economics',()=>{assert.match(r.decision,/REJECT_P136/);assert.ok(r.matched50<0);assert.ok(r.spy50<0)})
test('preserve exact execution identity',()=>assert.deepEqual([r.run,r.job,r.artifact,r.head,r.artifactDigest],[34387359361,102586891128,10118214840,'f2099d2ca7fb406536ef0caf589b3cdf7d304400','sha256:6e22afd2b8660d7f95763c200e0857cd1086092cce901c03716219690b2aa828']))
test('no local rescue or portfolio/trading authority',()=>assert.deepEqual(Object.values({ranking:false,allocation:false,sizing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,live:false}),Array(9).fill(false)))
