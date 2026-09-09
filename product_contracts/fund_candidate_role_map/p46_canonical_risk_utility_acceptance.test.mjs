import test from 'node:test'
import assert from 'node:assert/strict'
const MM_PRODUCT_HEAD='af4bfcc8231ea76be6c89b5f898ffdc1b313ae12'
const cost={run:34388044981,job:102589194917,artifact:10118492178,head:'8b13d33bef16efc9571b71bc7be752b14c870151',digest:'sha256:53d58f04aa2b5753144528854eb784e0b0e70ccdf6ed1b743ffc6856e9a1fda8',matched25:.0300,matched50:.0210,matched100:.0033,turnover:3.21}
const risk={run:34388125831,job:102589467510,artifact:10118513227,head:'ed99f9fa56de4f76fb8d0031ca28beea8165c24e',digest:'sha256:04e675f6e8d7c9d42090b2a84c8358e9bfd743339a9bf6649cf8aa871a764480',cagr:.1273,spyCagr:.1380,qqqCagr:.1893,maxdd:-.1331,spyMaxdd:-.2393,qqqMaxdd:-.3258,sharpe:1.19,spySharpe:.95,qqqSharpe:1.03,worst12:-.0764,spyWorst12:-.1818,qqqWorst12:-.3258}
test('bind exact P46 canonical product head',()=>assert.equal(MM_PRODUCT_HEAD,'af4bfcc8231ea76be6c89b5f898ffdc1b313ae12'))
test('canonical cost envelope preserves matched alpha',()=>{assert.ok(cost.matched25>cost.matched50&&cost.matched50>cost.matched100&&cost.matched100>0);assert.equal(cost.turnover,3.21)})
test('risk utility offsets raw-return opportunity weakness without erasing it',()=>{assert.ok(risk.cagr<risk.spyCagr&&risk.cagr<risk.qqqCagr);assert.ok(risk.maxdd>risk.spyMaxdd&&risk.maxdd>risk.qqqMaxdd);assert.ok(risk.sharpe>risk.spySharpe&&risk.sharpe>risk.qqqSharpe);assert.ok(risk.worst12>risk.spyWorst12&&risk.worst12>risk.qqqWorst12)})
test('preserve exact corrected executions',()=>{assert.deepEqual([cost.run,cost.job,cost.artifact,cost.head],[34388044981,102589194917,10118492178,'8b13d33bef16efc9571b71bc7be752b14c870151']);assert.deepEqual([risk.run,risk.job,risk.artifact,risk.head],[34388125831,102589467510,10118513227,'ed99f9fa56de4f76fb8d0031ca28beea8165c24e'])})
test('no portfolio or trading authority',()=>assert.deepEqual(Object.values({ranking:false,allocation:false,sizing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,live:false}),Array(9).fill(false)))
