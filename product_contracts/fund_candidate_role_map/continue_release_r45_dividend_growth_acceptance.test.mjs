import test from 'node:test'
import assert from 'node:assert/strict'
const FOUNDRY_HEAD='827140e2c6d5c15cc58880ded241da78d1c8c146'
const claim=Object.freeze({run:34591373981,job:103237197893,artifact:10195761319,classification:'DIVIDEND_GROWTH_ALPHA_REJECTED__DEFENSIVE_SHAPING_ONLY'})
const protectedAuthority=Object.freeze({ranking:false,allocation:false,promotion:false,runtime:false,broker:false,live:false,foundryMain:false})
test('bind exact Foundry r45 continuation head',()=>assert.equal(FOUNDRY_HEAD,'827140e2c6d5c15cc58880ded241da78d1c8c146'))
test('retain exact dividend-growth terminal identity',()=>assert.deepEqual([claim.run,claim.job,claim.artifact],[34591373981,103237197893,10195761319]))
test('preserve terminal classification',()=>assert.equal(claim.classification,'DIVIDEND_GROWTH_ALPHA_REJECTED__DEFENSIVE_SHAPING_ONLY'))
test('grant no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))