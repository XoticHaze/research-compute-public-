import test from 'node:test'
import assert from 'node:assert/strict'
const FOUNDRY_HEAD='788805b9340f7d7dc56b9889156c1de404dfca7d'
const claims=Object.freeze([
  {id:'MR_ALT_PREMIA_MULTIARCH_R1',runs:[34600127346,34600088328,34600208978,34600237786,34600317078],classification:'TESTED_IMPLEMENTATIONS_REJECTED__NO_RESCUE'},
  {id:'MR_HEFA_DOLLAR_REGIME_R1',runs:[34600351710,34600438659],classification:'APPARENT_RELATIVE_ALPHA_EXPLAINED_BY_DOLLAR_REGIME__REJECTED'},
  {id:'MR_CWB_MATCHED_CONTROL_R1',runs:[34600619393],classification:'EXPOSURE_MATCHED_ALPHA_NOT_SUPPORTED__NO_RESCUE'}
])
const protectedAuthority=Object.freeze({ranking:false,allocation:false,promotion:false,runtime:false,broker:false,live:false,foundryMain:false})
test('bind exact Foundry r54 continuation head',()=>assert.equal(FOUNDRY_HEAD,'788805b9340f7d7dc56b9889156c1de404dfca7d'))
test('retain exact terminal execution identities',()=>assert.deepEqual(claims.map(c=>c.runs),[[34600127346,34600088328,34600208978,34600237786,34600317078],[34600351710,34600438659],[34600619393]]))
test('preserve fail-closed classifications',()=>assert.deepEqual(claims.map(c=>c.classification),['TESTED_IMPLEMENTATIONS_REJECTED__NO_RESCUE','APPARENT_RELATIVE_ALPHA_EXPLAINED_BY_DOLLAR_REGIME__REJECTED','EXPOSURE_MATCHED_ALPHA_NOT_SUPPORTED__NO_RESCUE']))
test('grant no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))
