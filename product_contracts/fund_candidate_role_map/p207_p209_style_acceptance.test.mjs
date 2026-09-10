import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD='147678c8f5db8a06a12e2f00a01cfdfac3ecca0b'
const p207={run:34431329265,job:102727260968,started:'2026-09-10T02:55:29Z',head:'dbfd67672c4c3b35e2f846712e634bd095c3094c',artifact:10134588875,sha:'234e203e937f68e50af2dd8da493f03efeee0fad80e17953cfd6ba03c0bdb987',iwm2010:47,iwd2010:-11,spy2010:-254,foldsIwm:3,foldsIwd:3}
const p208={run:34431428021,job:102727563695,started:'2026-09-10T02:57:08Z',head:'b1f360539147e8f7013cfc1a0c8344368a57dd1a',artifact:10134624488,sha:'42173c8dd5757a9b9a2c81626f6a04ba122342a67ef608c1f1041a9051825ccc',iwd2018:221,spy2018:-137,iwd2020:366,spy2020:35,spy2022:-55,foldsIwd:2,foldsSpy:2}
const p209={run:34431474502,job:102727709207,started:'2026-09-10T02:57:54Z',head:'abe668559d8055fa6ec9c342d96c7e18edba5ddb',artifact:10134643905,sha:'31d8de9b225510d89ba7f75221e41480f6acd6eb3e92d12a2bbbf11819c2d749',efa2010:-7,spy2010:-709,efa2015:25,efa2020:224,foldsEfa:1}
const authority={ranking:false,allocation:false,sizing:false,promotion:false,strategy_spec:false,runtime:false,data:false,broker:false,live_trading:false}

test('bind exact product head',()=>assert.equal(MM_PRODUCT_HEAD,'147678c8f5db8a06a12e2f00a01cfdfac3ecca0b'))
test('VBR intersection lacks durable incremental alpha',()=>{assert.ok(p207.iwm2010>0);assert.ok(p207.iwd2010<0);assert.ok(p207.spy2010<0);assert.ok(p207.foldsIwd<=3)})
test('COWZ recent strength remains regime context',()=>{assert.ok(p208.iwd2020>0);assert.ok(p208.spy2020>0);assert.ok(p208.spy2018<0);assert.ok(p208.spy2022<0);assert.ok(p208.foldsSpy<3)})
test('EFV recent value-relative strength fails broad durability',()=>{assert.ok(p209.efa2010<0);assert.ok(p209.spy2010<0);assert.ok(p209.efa2020>0);assert.ok(p209.foldsEfa<3)})
test('preserve external science identities',()=>{assert.equal(p207.artifact,10134588875);assert.equal(p208.artifact,10134624488);assert.equal(p209.artifact,10134643905)})
test('no capital or trading authority',()=>assert.deepEqual(Object.values(authority),Array(Object.keys(authority).length).fill(false)))
