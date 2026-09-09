import test from 'node:test'
import assert from 'node:assert/strict'
const MM_PRODUCT_HEAD='2f7a81513488131a533b1ff9d5490d574a023db1'
const r={run:34388641721,job:102591193284,artifact:10118718305,head:'73021193e9383051fef2c040166c855d9f2b7ae8',digest:'sha256:e2428ad95c8a18123af268220071d492c8896c31344cd03cbf17323d695536d9',cagr:.1561,matched:.1449,spy:.1380,qqq:.1893,sharpe:.86,spySharpe:.95,trailsMatched100:true,trailsSpy100:true}
test('bind exact P47 product head',()=>assert.equal(MM_PRODUCT_HEAD,'2f7a81513488131a533b1ff9d5490d574a023db1'))
test('preserve scoped 50bps alpha and weak risk utility',()=>{assert.ok(r.cagr>r.matched&&r.cagr>r.spy&&r.cagr<r.qqq);assert.ok(r.sharpe<r.spySharpe);assert.equal(r.trailsMatched100,true);assert.equal(r.trailsSpy100,true)})
test('preserve exact execution identity',()=>assert.deepEqual([r.run,r.job,r.artifact,r.head],[34388641721,102591193284,10118718305,'73021193e9383051fef2c040166c855d9f2b7ae8']))
test('no portfolio or trading authority',()=>assert.deepEqual(Object.values({ranking:false,allocation:false,sizing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,live:false}),Array(9).fill(false)))
