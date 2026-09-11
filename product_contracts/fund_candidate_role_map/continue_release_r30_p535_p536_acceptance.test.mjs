import test from 'node:test'
import assert from 'node:assert/strict'
const FOUNDRY_HEAD='8cce665f6b25070430ca05175d6613c9d86a3d2d'
const claims=Object.freeze({
  P535:{run:34559234129,job:103138353165,artifact:10183706925,classification:'REJECTED_CHRONOLOGY_PERSISTENCE_FAILED_AFTER_FIXED_WINDOW_STRENGTH'},
  P536:{run:34559275848,job:103138475922,artifact:10183722090,classification:'REJECTED_EXPOSURE_MATCHED_OPPORTUNITY_COST_FAILED'}
})
const protectedAuthority=Object.freeze({ranking:false,allocation:false,promotion:false,runtime:false,broker:false,live:false,foundryMain:false})
test('bind exact Foundry r30 continuation head',()=>assert.equal(FOUNDRY_HEAD,'8cce665f6b25070430ca05175d6613c9d86a3d2d'))
test('retain exact P535 terminal identity',()=>assert.deepEqual([claims.P535.run,claims.P535.job,claims.P535.artifact],[34559234129,103138353165,10183706925]))
test('retain exact P536 terminal identity',()=>assert.deepEqual([claims.P536.run,claims.P536.job,claims.P536.artifact],[34559275848,103138475922,10183722090]))
test('preserve terminal classifications',()=>assert.deepEqual([claims.P535.classification,claims.P536.classification],['REJECTED_CHRONOLOGY_PERSISTENCE_FAILED_AFTER_FIXED_WINDOW_STRENGTH','REJECTED_EXPOSURE_MATCHED_OPPORTUNITY_COST_FAILED']))
test('grant no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))
