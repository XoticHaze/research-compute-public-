import test from 'node:test'
import assert from 'node:assert/strict'

const FOUNDRY_HEAD = '0d63a4985da188a5a9a11b0f17516f9cb7e4c043'
const claim = Object.freeze({child:'P516_DIVIDEND_QUALITY_RESIDUAL_R1', run:34553529997, job:103121199540, artifact:10181666432, digest:'9c07517938d8ab2467a0bafc58cdf645238a11b79fc93ac2611bc3b6c362aad4', classification:'DIVIDEND_QUALITY_ALPHA_NOT_SUPPORTED'})
const protectedAuthority = Object.freeze({ranking:false, allocation:false, promotion:false, runtime:false, broker:false, live:false, foundryMain:false})

test('bind exact Foundry r25 continuation head',()=>assert.equal(FOUNDRY_HEAD,'0d63a4985da188a5a9a11b0f17516f9cb7e4c043'))
test('retain exact P516 terminal identity',()=>assert.deepEqual([claim.run,claim.job,claim.artifact],[34553529997,103121199540,10181666432]))
test('require exact source artifact digest',()=>assert.match(claim.digest,/^[0-9a-f]{64}$/))
test('preserve terminal rejection classification',()=>assert.equal(claim.classification,'DIVIDEND_QUALITY_ALPHA_NOT_SUPPORTED'))
test('release acceptance grants no protected authority',()=>assert.deepEqual(Object.values(protectedAuthority),Array(7).fill(false)))
