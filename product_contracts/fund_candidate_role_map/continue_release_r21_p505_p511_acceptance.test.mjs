import test from 'node:test'
import assert from 'node:assert/strict'

const FOUNDRY_HEAD = 'c66b80a00810041596941bde454ff4d84f3c0404'
const claims = Object.freeze([
  Object.freeze({child:'P505_CORE_COMPLEMENTS_COMMON_SAMPLE_R2', run:34551915304, job:103116421378, artifact:10181125603, digest:'9902499d17c6c94d2a8ad06e088d089555e0c1bb230f6ce2cb638d585f508d87', classification:'P505_COMPLETED_MONTH_CORRECTION_CONFIRMS_CORE_RETURN_EDGE_AND_RISK_SHAPER_ROLES'}),
  Object.freeze({child:'P506_RWJ_INDEPENDENT_FF5_RESIDUAL_R1', run:34551493718, job:103115168402, artifact:10180976110, digest:'7f2b501ca0fcccd312f593e12c241e8183496a4e72cdc3c64a3aae3f35a84a5a', classification:'RWJ_DISTINCT_REVENUE_ALPHA_DOWNGRADED__INDEPENDENT_FF5_RESIDUAL_GATE_FAILED'}),
  Object.freeze({child:'P507_SHAREHOLDER_YIELD_ALPHA_R1', run:34551663388, job:103115676698, artifact:10181035014, digest:'1f72e06189661e6067f9c43c116386dc46a433fe8286dea44b1c83c09a8e3c34', classification:'SHAREHOLDER_YIELD_WRAPPER_ALPHA_REJECTED'}),
  Object.freeze({child:'P508_EQUITY_MOMENTUM_RESIDUAL_R1', run:34551717631, job:103115839857, artifact:10181055402, digest:'d14b50a899c229005fdfa85622bdc9324941a308b1241094753dd4f0a2290659', classification:'STOCK_LEVEL_MOMENTUM_WRAPPER_RESIDUAL_REJECTED__P266_INDUSTRY_SIGNAL_NOT_EXPLAINED_BY_GENERIC_WRAPPER_ALPHA'}),
  Object.freeze({child:'P509_INDUSTRY_MOMENTUM_UNIVERSE_TRANSPORT_R2', run:34551967903, job:103116572497, artifact:10181142668, digest:'b0e27421d1ad2c00b940938b07321de846536ac1a5ffbdb48efa9c9706453e22', classification:'P266_GAINS_INDEPENDENT_UNIVERSE_TRANSPORT_SUPPORT'}),
  Object.freeze({child:'P511_CALF_INDEPENDENT_FF5_R1', run:34552197615, job:103117254086, artifact:10181221615, digest:'4b8ebd61ab5275fa675b8ed038b808c0a3500ec2da8f977644315c398928339d', classification:'CALF_SCOPED_CANDIDATE_REJECTED_ON_INDEPENDENT_FF5_ATTRIBUTION'})
])
const protectedAuthority = Object.freeze({ranking:false, allocation:false, promotion:false, runtime:false, broker:false, live:false, foundryMain:false})

test('bind exact Foundry r21 continuation head',()=>assert.equal(FOUNDRY_HEAD,'c66b80a00810041596941bde454ff4d84f3c0404'))
test('retain exact terminal execution identities',()=>assert.equal(claims.length,6))
test('require exact source artifact digests',()=>claims.forEach(x=>assert.match(x.digest,/^[0-9a-f]{64}$/)))
test('preserve fail-closed classifications',()=>claims.forEach(x=>assert.ok(x.classification.length>20)))
test('release acceptance grants no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))
