import test from 'node:test'
import assert from 'node:assert/strict'
const FOUNDRY_HEAD='9c8cedc5ed765b1fa70fdad28b5aac7c4a821fd2'
const claims=Object.freeze({
  P545:{run:34575346699,job:103186430696,artifact:10189389206,classification:'UMICH_SENTIMENT_TREND_ALPHA_NOT_SUPPORTED'},
  P546:{run:34575360589,job:103186476602,artifact:10189413263,classification:'SLOOS_CREDIT_STANDARDS_SURVIVES_NOT_PROMOTED'}
})
const protectedAuthority=Object.freeze({ranking:false,allocation:false,promotion:false,runtime:false,broker:false,live:false,foundryMain:false})
test('bind exact Foundry r34 continuation head',()=>assert.equal(FOUNDRY_HEAD,'9c8cedc5ed765b1fa70fdad28b5aac7c4a821fd2'))
test('retain exact P545 terminal identity',()=>assert.deepEqual([claims.P545.run,claims.P545.job,claims.P545.artifact],[34575346699,103186430696,10189389206]))
test('retain exact P546 terminal identity',()=>assert.deepEqual([claims.P546.run,claims.P546.job,claims.P546.artifact],[34575360589,103186476602,10189413263]))
test('preserve terminal classifications',()=>assert.deepEqual([claims.P545.classification,claims.P546.classification],['UMICH_SENTIMENT_TREND_ALPHA_NOT_SUPPORTED','SLOOS_CREDIT_STANDARDS_SURVIVES_NOT_PROMOTED']))
test('grant no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))