import test from 'node:test'
import assert from 'node:assert/strict'
const FOUNDRY_HEAD='ad196241f98c1f9f0af9d46053686e69052d5928'
const claims=Object.freeze([
  {child:'P388_PIT_ASSET_TURNOVER_R1',run:34595266783,job:103249446576,artifact:10262011782,classification:'NOT_SUPPORTED_NO_RESCUE'},
  {child:'MR_JAPAN_QUALITY_JPXN_R1',run:34595189108,job:103249192247,artifact:10261816721,classification:'NOT_SUPPORTED_NO_RESCUE'},
  {child:'MR_EM_SMALL_DIVIDEND_DGS_R1',run:34595464303,job:103250078680,artifact:10261886879,classification:'NOT_SUPPORTED_NO_RESCUE'},
  {child:'MR_DYNAMIC_MULTIFACTOR_OMFL_R1',run:34595576126,job:103250430955,artifact:10262516886,classification:'NOT_SUPPORTED_NO_RESCUE'}
])
const protectedAuthority=Object.freeze({ranking:false,allocation:false,promotion:false,runtime:false,broker:false,live:false,foundryMain:false})
test('bind exact Foundry r52 continuation head',()=>assert.equal(FOUNDRY_HEAD,'ad196241f98c1f9f0af9d46053686e69052d5928'))
test('retain exact terminal identities',()=>assert.deepEqual(claims.map(x=>[x.run,x.job,x.artifact]),[[34595266783,103249446576,10262011782],[34595189108,103249192247,10261816721],[34595464303,103250078680,10261886879],[34595576126,103250430955,10262516886]]))
test('preserve fail-closed classifications',()=>assert.ok(claims.every(x=>x.classification==='NOT_SUPPORTED_NO_RESCUE')))
test('grant no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))