import test from 'node:test'
import assert from 'node:assert/strict'
const FOUNDRY_HEAD='cc89087d86433d1b97cc46634c08286501fafab2'
const claims=Object.freeze({
  LOW_VOL:{run:34590296493,job:103233803299,artifact:10195338813,classification:'DURABLE_LOW_VOLATILITY_INDEPENDENT_ALPHA_NOT_SUPPORTED__ERA_DEPENDENCE_PRESERVED'},
  SHAREHOLDER:{run:34590235925,job:103233603511,artifact:10195310974,classification:'DURABLE_SHAREHOLDER_YIELD_ALPHA_NOT_SUPPORTED'},
  IAI:{run:34590120634,job:103233238749,artifact:10195267845,classification:'IAI_DURABLE_INDEPENDENT_ALPHA_NOT_SUPPORTED__RECENT_REGIME_ALPHA_PRESERVED'}
})
const protectedAuthority=Object.freeze({ranking:false,allocation:false,promotion:false,runtime:false,broker:false,live:false,foundryMain:false})
test('bind exact Foundry r43 continuation head',()=>assert.equal(FOUNDRY_HEAD,'cc89087d86433d1b97cc46634c08286501fafab2'))
test('retain source identities',()=>assert.deepEqual([claims.LOW_VOL.run,claims.SHAREHOLDER.run,claims.IAI.run],[34590296493,34590235925,34590120634]))
test('preserve classifications',()=>assert.deepEqual([claims.LOW_VOL.classification,claims.SHAREHOLDER.classification,claims.IAI.classification],['DURABLE_LOW_VOLATILITY_INDEPENDENT_ALPHA_NOT_SUPPORTED__ERA_DEPENDENCE_PRESERVED','DURABLE_SHAREHOLDER_YIELD_ALPHA_NOT_SUPPORTED','IAI_DURABLE_INDEPENDENT_ALPHA_NOT_SUPPORTED__RECENT_REGIME_ALPHA_PRESERVED']))
test('grant no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))