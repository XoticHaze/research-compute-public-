import test from 'node:test'
import assert from 'node:assert/strict'
const FOUNDRY_HEAD='3ca9a54f5286ac1b2117d468407223ff2990f1a1'
const claims=Object.freeze({
  BIOTECH:{run:34589156190,job:103230199208,artifact:10194879320,classification:'BIOTECH_SELECTION_NOT_SUPPORTED__RECENT_XLV_RELATIVE_STRENGTH_PRESERVED'},
  CYBER:{run:34588938147,job:103229512027,artifact:10194787429,classification:'CYBERSECURITY_SELECTION_NOT_SUPPORTED_VERSUS_MATCHED_TECH_CONTROL'},
  HOME:{run:34588867934,job:103229290141,artifact:10194758990,classification:'HOMEBUILDER_PREMIUM_NOT_SUPPORTED__RECENT_XLY_RELATIVE_STRENGTH_PRESERVED'}
})
const protectedAuthority=Object.freeze({ranking:false,allocation:false,promotion:false,runtime:false,broker:false,live:false,foundryMain:false})
test('bind exact Foundry r46 continuation head',()=>assert.equal(FOUNDRY_HEAD,'3ca9a54f5286ac1b2117d468407223ff2990f1a1'))
test('retain source identities',()=>assert.deepEqual([claims.BIOTECH.run,claims.CYBER.run,claims.HOME.run],[34589156190,34588938147,34588867934]))
test('preserve terminal classifications',()=>assert.deepEqual([claims.BIOTECH.classification,claims.CYBER.classification,claims.HOME.classification],['BIOTECH_SELECTION_NOT_SUPPORTED__RECENT_XLV_RELATIVE_STRENGTH_PRESERVED','CYBERSECURITY_SELECTION_NOT_SUPPORTED_VERSUS_MATCHED_TECH_CONTROL','HOMEBUILDER_PREMIUM_NOT_SUPPORTED__RECENT_XLY_RELATIVE_STRENGTH_PRESERVED']))
test('grant no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))