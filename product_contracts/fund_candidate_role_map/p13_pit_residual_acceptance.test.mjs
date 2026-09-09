import test from 'node:test'
import assert from 'node:assert/strict'
const MM_PRODUCT_HEAD='193ba25f2e38285b232444e9d06fc857d2b96621'
const r=Object.freeze({run:34373639716,job:102540806066,artifact:10112939249,full_raw:-0.10315320063356981,full_pit_ew:-0.047543320207722894,full_smh:-0.0909109587228667,y2022_raw:-0.1216998656908832,y2022_pit_ew:-0.06399648753294063,y2022_smh:-0.14397360602042197})
test('bind exact P13 PIT product head',()=>assert.equal(MM_PRODUCT_HEAD,'193ba25f2e38285b232444e9d06fc857d2b96621'))
test('P13 point-in-time residual alpha parent is parked',()=>{assert.equal(r.run,34373639716);assert.equal(r.job,102540806066);assert.equal(r.artifact,10112939249);assert.ok(r.full_raw<0&&r.full_pit_ew<0&&r.full_smh<0);assert.ok(r.y2022_raw<0&&r.y2022_pit_ew<0&&r.y2022_smh<0)})
test('no rescue or trading authority',()=>{const b={lookbackRescue:false,topKRescue:false,portfolioRanking:false,allocation:false,sizing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,liveTrading:false};assert.deepEqual(Object.values(b),Array(11).fill(false))})
