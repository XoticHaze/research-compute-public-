import test from 'node:test';
import assert from 'node:assert/strict';
const MM_HEAD='706104d824a2eac06cd306bbf846351f7b06f0df';
const p89={run:34361686774,job:102499989223,artifact:10108082766,artifactDigest:'sha256:f20b7e16326c75c0d4e0e845cac9a3697dcc0dfced3bab10925293d53f9037c4',matchedFull:0.014292600264143918,matched2015:-0.027530707127733756,matched2020:-0.016861331743506236,qqq2020:-0.1435756737283762,qqqFolds2020:0,sharpe2020:-0.1711397356004209,state:'CREDIT_RISK_REGIME_ALLOCATOR_REJECTED_LATER_WINDOWS'};
test('bind exact P89 product head',()=>assert.equal(MM_HEAD,'706104d824a2eac06cd306bbf846351f7b06f0df'));
test('P89 later-window credit regime is rejected',()=>{assert.equal(p89.run,34361686774);assert.equal(p89.job,102499989223);assert.equal(p89.artifact,10108082766);assert.ok(p89.artifactDigest.startsWith('sha256:'));assert.ok(p89.matchedFull>0);assert.ok(p89.matched2015<0);assert.ok(p89.matched2020<0);assert.ok(p89.qqq2020<0);assert.equal(p89.qqqFolds2020,0);assert.ok(p89.sharpe2020<0);assert.equal(p89.state,'CREDIT_RISK_REGIME_ALLOCATOR_REJECTED_LATER_WINDOWS')});
test('P89 grants no timing ranking allocation tuning or trading authority',()=>assert.deepEqual(Object.values({ranking:false,allocation:false,sizing:false,timing:false,promotion:false,tuning:false,strategy:false,runtime:false,data:false,broker:false,live:false}),Array(11).fill(false)));
