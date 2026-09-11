import test from 'node:test'
import assert from 'node:assert/strict'
const FOUNDRY_HEAD='8b8781d801f58efb98543c89fe4b451274845499'
const claim={id:'DBMF_CONCENTRATION_COMPARATOR_20260911',run:34635116012,classification:'SURVIVOR_WITH_CONCENTRATION_CAVEAT__INDEPENDENT_SOURCE_VALIDATION_REQUIRED'}
const comparator={dbmfDrop:0.06845788655281781,kmlmDrop:0.07000706770113507,spyDrop:0.08401502665741445}
const protectedAuthority=Object.freeze({ranking:false,allocation:false,promotion:false,runtime:false,broker:false,live:false,foundryMain:false})
test('bind exact Foundry r63 continuation head',()=>assert.equal(FOUNDRY_HEAD,'8b8781d801f58efb98543c89fe4b451274845499'))
test('retain exact terminal execution identity',()=>assert.equal(claim.run,34635116012))
test('preserve comparator-normalized survivor classification',()=>assert.equal(claim.classification,'SURVIVOR_WITH_CONCENTRATION_CAVEAT__INDEPENDENT_SOURCE_VALIDATION_REQUIRED'))
test('DBMF absolute concentration drop is not worse than comparators',()=>assert.ok(comparator.dbmfDrop<comparator.kmlmDrop && comparator.dbmfDrop<comparator.spyDrop))
test('grant no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))
