import test from 'node:test'
import assert from 'node:assert/strict'
const FOUNDRY_HEAD='8708531f0c38c444707ab36b3b443820c8e418b4'
const claim=Object.freeze({run:34591754914,job:103238395430,artifact:10195907017,classification:'PIT_MEMBERSHIP_AND_SEC_IDENTIFIER_AUTHORITY_READY__HISTORICAL_UNIVERSE_BLOCKER_RESOLVED'})
const protectedAuthority=Object.freeze({alphaInference:false,ranking:false,allocation:false,promotion:false,runtime:false,broker:false,live:false,foundryMain:false})
test('bind exact Foundry r49 continuation head',()=>assert.equal(FOUNDRY_HEAD,'8708531f0c38c444707ab36b3b443820c8e418b4'))
test('retain exact P388 PIT authority terminal identity',()=>assert.deepEqual([claim.run,claim.job,claim.artifact],[34591754914,103238395430,10195907017]))
test('preserve data-authority classification',()=>assert.equal(claim.classification,'PIT_MEMBERSHIP_AND_SEC_IDENTIFIER_AUTHORITY_READY__HISTORICAL_UNIVERSE_BLOCKER_RESOLVED'))
test('grant no alpha or protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(8).fill(false)))