import test from 'node:test'
import assert from 'node:assert/strict'

const FOUNDRY_HEAD = 'c037687c92942b10161d400b96a3d01995bee32c'
const queue = Object.freeze({
  schema: 'foundry.release_acceptance_queue.v1',
  authority: 'RESEARCH_ONLY',
  claims: [
    { parent:'MARKET_NEUTRAL_EQUITY_ALPHA', run:34522010690, job:103021569828, artifact:10170032809, digest:'f13b3b5f75cfe7895c8a1e73ae890022a6cf2442c2aef693309683bc09c5456e', classification:'DATA_COVERAGE_FAILURE__FIXED_2024_PLUS_BLOCK_EMPTY' },
    { parent:'ALTERNATIVE_RISK_PREMIA_ALPHA', run:34521820785, job:103020928775, artifact:10169956221, digest:'7557b30cc419b90c30d52de3441c9e1a99e091c0cf581f6bd28172d4ca06e47b', classification:'ALT_RISK_PREMIA_ALPHA_NOT_SUPPORTED' }
  ],
  protected: { automatic:false, ranking:false, allocation:false, promotion:false, runtime:false, broker:false, live:false, foundryMain:false }
})

test('bind exact Foundry r12 continuation head',()=>assert.equal(FOUNDRY_HEAD,'c037687c92942b10161d400b96a3d01995bee32c'))
test('retain exact external execution identities',()=>assert.deepEqual(queue.claims.map(x=>[x.run,x.job,x.artifact]),[[34522010690,103021569828,10170032809],[34521820785,103020928775,10169956221]]))
test('preserve QMN as coverage failure rather than scientific rejection',()=>assert.equal(queue.claims[0].classification,'DATA_COVERAGE_FAILURE__FIXED_2024_PLUS_BLOCK_EMPTY'))
test('preserve QAI exact alpha rejection',()=>assert.equal(queue.claims[1].classification,'ALT_RISK_PREMIA_ALPHA_NOT_SUPPORTED'))
test('require sha256-sized artifact digests',()=>queue.claims.forEach(x=>assert.match(x.digest,/^[0-9a-f]{64}$/)))
test('release acceptance grants no protected authority',()=>assert.deepEqual(Object.values(queue.protected),Array(8).fill(false)))
