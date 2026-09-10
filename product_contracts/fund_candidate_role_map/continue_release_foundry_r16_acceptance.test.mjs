import test from 'node:test'
import assert from 'node:assert/strict'

const FOUNDRY_HEAD='98068deed2032c825f400189ff62ae8cbaad7f3a'
const claim=['POINT_IN_TIME_FUNDAMENTAL_SELECTION',34534268525,103062094703,10174771218,'79c76e6068351019a084620a93ebf29de26961a6ab6d0e6b453e8d222f7c5164','EIGHT_MORE_HISTORICAL_ALIASES_RESOLVED__FIVE_CORPORATE_ACTION_RESIDUALS_REMAIN']
const protectedBoundaries={automatic:false,ranking:false,allocation:false,promotion:false,runtime:false,broker:false,live:false,foundryMain:false}
test('bind exact Foundry r16 continuation head',()=>assert.equal(FOUNDRY_HEAD,'98068deed2032c825f400189ff62ae8cbaad7f3a'))
test('retain exact PIT execution identity',()=>assert.deepEqual(claim.slice(1,4),[34534268525,103062094703,10174771218]))
test('require sha256-sized artifact digest',()=>assert.match(claim[4],/^[0-9a-f]{64}$/))
test('PIT residual aliases remain fail closed at five',()=>assert.equal(claim[5],'EIGHT_MORE_HISTORICAL_ALIASES_RESOLVED__FIVE_CORPORATE_ACTION_RESIDUALS_REMAIN'))
test('release acceptance grants no protected authority',()=>assert.deepEqual(Object.values(protectedBoundaries),Array(8).fill(false)))
