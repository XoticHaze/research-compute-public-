import test from 'node:test'
import assert from 'node:assert/strict'
const FOUNDRY_HEAD='f57921e341fed666a4f6e45c548d532a38e4726d'
const claim={id:'METALS_MINING_STAGEA_TRANSPORT_REJECTED_20260911',run:34629852588,classification:'METALS_MINING_GENERIC_TRANSPORT_REJECTED_SUPERSEDES_DEVELOPMENT_ADVANCE'}
const supersedes='METALS_MINING_STAGEA_DEVELOPMENT_ADVANCE_20260911'
const protectedAuthority=Object.freeze({ranking:false,allocation:false,promotion:false,runtime:false,broker:false,live:false,foundryMain:false})
test('bind exact Foundry r60 continuation head',()=>assert.equal(FOUNDRY_HEAD,'f57921e341fed666a4f6e45c548d532a38e4726d'))
test('retain exact terminal execution identity',()=>assert.equal(claim.run,34629852588))
test('preserve superseding rejection classification',()=>assert.equal(claim.classification,'METALS_MINING_GENERIC_TRANSPORT_REJECTED_SUPERSEDES_DEVELOPMENT_ADVANCE'))
test('supersede only the development advance',()=>assert.equal(supersedes,'METALS_MINING_STAGEA_DEVELOPMENT_ADVANCE_20260911'))
test('grant no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))
