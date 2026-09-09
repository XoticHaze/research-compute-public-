import test from 'node:test'
import assert from 'node:assert/strict'
const MM_PRODUCT_HEAD='0de4bd1e3ce8dfd399c675ea838a5abb2c218dd8'
const evidence={
  p131:{run:34385626929,job:102581033088,artifact:10117582854,decision:'P131_DOLLAR_REGIME_NOT_SUPPORTED'},
  p132:{run:34386024421,job:102582376873,artifact:10117727426,decision:'P132_CLAIMS_CYCLE_NOT_SUPPORTED'},
  p133:{run:34387143369,job:102586157238,artifact:10118133124,decision:'P133_UNRESOLVED_DATA_BOUND_ROTATE_CAPACITY',explicitRows:780},
  p134:{run:34386232388,job:102583084895,artifact:10117806997,decision:'PARK_EXACT_P134_FUND_FORMULATION_NO_PARAMETER_RESCUE',matched2015:.005682,spy2015:-.098178},
  p135:{run:34386891056,job:102585303984,artifact:10118050468,decision:'REJECT_EXACT_P135_R1_AND_ROTATE_NO_PARAMETER_RESCUE',matched2015:.0105,spy2015:-.0514},
}
test('bind exact macro product head',()=>assert.equal(MM_PRODUCT_HEAD,'0de4bd1e3ce8dfd399c675ea838a5abb2c218dd8'))
test('preserve rejection versus data-bound distinction',()=>{assert.match(evidence.p131.decision,/NOT_SUPPORTED/);assert.match(evidence.p132.decision,/NOT_SUPPORTED/);assert.match(evidence.p133.decision,/UNRESOLVED_DATA_BOUND/);assert.equal(evidence.p133.explicitRows,780)})
test('preserve limited matched effects without portfolio-fit promotion',()=>{assert.ok(evidence.p134.matched2015>0&&evidence.p134.spy2015<0);assert.ok(evidence.p135.matched2015>0&&evidence.p135.spy2015<0)})
test('preserve exact execution identities',()=>assert.deepEqual(Object.values(evidence).map(x=>[x.run,x.job,x.artifact]),[[34385626929,102581033088,10117582854],[34386024421,102582376873,10117727426],[34387143369,102586157238,10118133124],[34386232388,102583084895,10117806997],[34386891056,102585303984,10118050468]]))
test('no product expansion into portfolio or trading authority',()=>assert.deepEqual(Object.values({ranking:false,allocation:false,sizing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,live:false}),Array(9).fill(false)))
