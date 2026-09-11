import test from 'node:test'
import assert from 'node:assert/strict'
const FOUNDRY_HEAD='a6a4d9a1596d620a1728e4b900c65463a910ffce'
const rejected={id:'STAGEA_TRANSPORT_AND_CFTC_REJECTIONS_20260911',runs:[34628935384,34629218195,34629363802,34629552876],classification:'FOUR_TERMINAL_REJECTIONS_FAIL_CLOSED'}
const advance={id:'METALS_MINING_STAGEA_DEVELOPMENT_ADVANCE_20260911',runs:[34629597921],classification:'MIXED_METALS_MINING_ADVANCE_RESEARCH_ONLY'}
const protectedAuthority=Object.freeze({ranking:false,allocation:false,promotion:false,runtime:false,broker:false,live:false,foundryMain:false})
test('bind exact Foundry r58 continuation head',()=>assert.equal(FOUNDRY_HEAD,'a6a4d9a1596d620a1728e4b900c65463a910ffce'))
test('retain exact rejected terminal execution identities',()=>assert.deepEqual(rejected.runs,[34628935384,34629218195,34629363802,34629552876]))
test('retain exact metals mining execution identity',()=>assert.deepEqual(advance.runs,[34629597921]))
test('preserve fail-closed rejection classification',()=>assert.equal(rejected.classification,'FOUR_TERMINAL_REJECTIONS_FAIL_CLOSED'))
test('preserve development-only metals mining classification',()=>assert.equal(advance.classification,'MIXED_METALS_MINING_ADVANCE_RESEARCH_ONLY'))
test('grant no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))
