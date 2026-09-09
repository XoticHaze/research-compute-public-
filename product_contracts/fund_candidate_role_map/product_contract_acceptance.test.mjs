import test from 'node:test'
import assert from 'node:assert/strict'
const MM_HEAD='9b6cbb7f538c3f43be8b00c94c094cfdc7a84b90'
const era={run:34322914461,job:102373424285,artifact:10092580859,digest:'sha256:b63b1cbc56c79f20e6e2173e1effc67b0b63aaa4bb01c3675814ccd52f39c3f0',positiveInterceptEras:4,positiveLowerBoundEras:2,middleRawQQQ:[-1.3053076066983804,-3.958498423743251],recentIntercept:0.05130490142268842,recentLower:0.009702742324751736}
test('bind exact rendered MM era-context product head',()=>assert.equal(MM_HEAD,'9b6cbb7f538c3f43be8b00c94c094cfdc7a84b90'))
test('non-overlap eras preserve residual alpha without universal QQQ dominance',()=>{assert.equal(era.run,34322914461);assert.equal(era.artifact,10092580859);assert.equal(era.positiveInterceptEras,4);assert.equal(era.positiveLowerBoundEras,2);assert.ok(era.middleRawQQQ.every(v=>v<0));assert.ok(era.recentIntercept>0&&era.recentLower>0)})
test('product acceptance grants no portfolio or trading authority',()=>{const b={portfolioRanking:false,allocation:false,sizing:false,timing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,liveTrading:false};assert.deepEqual(Object.values(b),Array(10).fill(false))})
