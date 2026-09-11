import test from 'node:test'
import assert from 'node:assert/strict'
const FOUNDRY_HEAD='2d389f93089e93761410c8c9a3b0079bf5301575'
const claims=Object.freeze({
  P537:{run:34562760164,job:103148683955,artifact:10184904260,classification:'REJECTED_CHRONOLOGY_PERSISTENCE_FAILED'},
  P538:{run:34562793270,job:103148782813,artifact:10184916092,classification:'REJECTED_DURABLE_ALPHA_AND_CHRONOLOGY_FAILED'},
  P539:{run:34562859640,job:103148979754,artifact:10184938661,classification:'REJECTED_CHRONOLOGY_PERSISTENCE_FAILED',eventChronology:'QUARANTINED'}
})
const protectedAuthority=Object.freeze({ranking:false,allocation:false,promotion:false,runtime:false,broker:false,live:false,foundryMain:false})
test('bind exact Foundry r31 continuation head',()=>assert.equal(FOUNDRY_HEAD,'2d389f93089e93761410c8c9a3b0079bf5301575'))
test('retain exact P537 terminal identity',()=>assert.deepEqual([claims.P537.run,claims.P537.job,claims.P537.artifact],[34562760164,103148683955,10184904260]))
test('retain exact P538 terminal identity',()=>assert.deepEqual([claims.P538.run,claims.P538.job,claims.P538.artifact],[34562793270,103148782813,10184916092]))
test('retain exact P539 terminal identity',()=>assert.deepEqual([claims.P539.run,claims.P539.job,claims.P539.artifact],[34562859640,103148979754,10184938661]))
test('preserve terminal classifications',()=>assert.deepEqual([claims.P537.classification,claims.P538.classification,claims.P539.classification],['REJECTED_CHRONOLOGY_PERSISTENCE_FAILED','REJECTED_DURABLE_ALPHA_AND_CHRONOLOGY_FAILED','REJECTED_CHRONOLOGY_PERSISTENCE_FAILED']))
test('quarantine P539 ledger chronology',()=>assert.equal(claims.P539.eventChronology,'QUARANTINED'))
test('grant no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))
