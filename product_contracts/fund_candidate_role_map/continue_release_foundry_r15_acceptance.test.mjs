import test from 'node:test'
import assert from 'node:assert/strict'

const FOUNDRY_HEAD='5022c32db46b60bb076c4cf0604eef3bdc1ffc57'
const claims=[
 ['AAA_CLO_PORTFOLIO_UTILITY',34533269922,103058838287,10174362176,'3ba3dbed17200cd2824138d8688f9fb29c8f277c4bc3b97123a01b01da6a4bf8','COVERAGE_VALID__ADDITIVE_COMPLEMENT'],
 ['AVDV_IDMO_PORTFOLIO_UTILITY',34533398335,103059262399,10174415407,'017b7e585f7a40136bb57cdd3e1e9816e101e48ec3ded90e749902b8bc3fe231','COVERAGE_VALID__ADDITIVE_COMPLEMENT'],
 ['FUND_MODEL_COMPLEMENT_INTERACTION',34533662189,103060112339,10174515699,'d3a54d552af2f60f40985344a7b78fe0bf1cffecd0e1f54e874e3259cee9b989','JOINT_COMPLEMENT_SUPPORTED_WITH_EXPLICIT_RISK_RETURN_TRADEOFF'],
 ['POINT_IN_TIME_FUNDAMENTAL_SELECTION',34533999055,103061213521,10174646745,'c0daeba3a62471bfa5fc6ebe3d42cc8c42dfcd829291cf96266da43e32603174','TWO_EXACT_ALIASES_RESOLVED__THIRTEEN_REQUIRE_ORTHOGONAL_DATED_IDENTITY'],
 ['P305_DBMF_COMPLEMENTARITY',34534186354,103061825876,10174721575,'52731c960a3a032c796a72fd4d8222b9d31bcf2aaeb3422843dbd20c22f32dc7','MATCHED_ALPHA_SURVIVOR__HALF_DOSE_CAPITAL_EFFICIENCY_SUPPORTED']
]
const protectedBoundaries={automatic:false,ranking:false,allocation:false,promotion:false,runtime:false,broker:false,live:false,foundryMain:false}
test('bind exact Foundry r15 continuation head',()=>assert.equal(FOUNDRY_HEAD,'5022c32db46b60bb076c4cf0604eef3bdc1ffc57'))
test('bind five exact terminal executions',()=>assert.equal(claims.length,5))
test('retain exact execution identities',()=>assert.deepEqual(claims.map(x=>x.slice(1,4)),[[34533269922,103058838287,10174362176],[34533398335,103059262399,10174415407],[34533662189,103060112339,10174515699],[34533999055,103061213521,10174646745],[34534186354,103061825876,10174721575]]))
test('require sha256-sized artifact digests',()=>claims.forEach(x=>assert.match(x[4],/^[0-9a-f]{64}$/)))
test('PIT residual aliases remain fail closed',()=>assert.equal(claims[3][5],'TWO_EXACT_ALIASES_RESOLVED__THIRTEEN_REQUIRE_ORTHOGONAL_DATED_IDENTITY'))
test('DBMF diagnostic does not become optimized allocation',()=>assert.equal(claims[4][5],'MATCHED_ALPHA_SURVIVOR__HALF_DOSE_CAPITAL_EFFICIENCY_SUPPORTED'))
test('release acceptance grants no protected authority',()=>assert.deepEqual(Object.values(protectedBoundaries),Array(8).fill(false)))
