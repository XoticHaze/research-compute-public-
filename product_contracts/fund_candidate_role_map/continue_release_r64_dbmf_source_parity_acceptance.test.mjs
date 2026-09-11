import test from 'node:test'
import assert from 'node:assert/strict'
const FOUNDRY_HEAD='1d6e2e2bc7a07f8abd858d4ed9d2bdb4895fdc98'
const claim={id:'DBMF_FIRSTPARTY_CALENDAR_PARITY_20260911',run:34635278627,classification:'ANNUAL_SOURCE_PARITY_VALIDATED__NO_ALPHA_PROMOTION'}
const annualDiff=[0.0007313075600373087,0.000043750431807002,0.00007947448965704706]
const protectedAuthority=Object.freeze({ranking:false,allocation:false,promotion:false,runtime:false,broker:false,live:false,foundryMain:false})
test('bind exact Foundry r64 continuation head',()=>assert.equal(FOUNDRY_HEAD,'1d6e2e2bc7a07f8abd858d4ed9d2bdb4895fdc98'))
test('retain exact terminal execution identity',()=>assert.equal(claim.run,34635278627))
test('preserve annual source parity without alpha promotion',()=>assert.equal(claim.classification,'ANNUAL_SOURCE_PARITY_VALIDATED__NO_ALPHA_PROMOTION'))
test('all frozen annual differences are within 50bp',()=>assert.ok(annualDiff.every(x=>x<=0.005)))
test('grant no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))
