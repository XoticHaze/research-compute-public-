import test from 'node:test'
import assert from 'node:assert/strict'
const MM_PRODUCT_HEAD='34375b4ea143b59575b0dc7d1840f53784f93a02'
const rows=[{id:'P131',run:34385626929,job:102581033088,artifact:10117582854,m2015:-.023108533741071913,opp2015:-.0555698988508353},{id:'P132',run:34386024421,job:102582376873,artifact:10117727426,m2020:.002574302962541797,opp2020:-.09671817640964431},{id:'P133',run:34386118091,job:102582694686,artifact:10117770296,m2015:.001104299767605621,opp2015:-.12062107197314798}]
test('bind exact macro digest product head',()=>assert.equal(MM_PRODUCT_HEAD,'34375b4ea143b59575b0dc7d1840f53784f93a02'))
test('preserve three independent NOT_SUPPORTED failure shapes',()=>{assert.deepEqual(rows.map(x=>x.id),['P131','P132','P133']);assert.ok(rows[0].m2015<0&&rows[0].opp2015<0);assert.ok(rows[1].m2020>0&&rows[1].m2020<.003&&rows[1].opp2020<-.09);assert.ok(rows[2].m2015<.002&&rows[2].opp2015<-.12)})
test('no nearby macro rescue or portfolio authority',()=>assert.deepEqual(Object.values({ranking:false,allocation:false,sizing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,live:false}),Array(9).fill(false)))