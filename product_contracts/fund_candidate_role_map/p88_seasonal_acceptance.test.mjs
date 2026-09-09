import test from 'node:test';
import assert from 'node:assert/strict';
const MM_HEAD='b255fe911c0c5a3d95f695939cec51e6da841105';
const p88={run:34360627098,job:102496369730,artifact:10107654619,artifactDigest:'sha256:ef8de43d5715e594b0ef88761cfc382988398f2f255cd00488553c5265677f78',matchedFull:-0.006023699337046384,spyFull:-0.04394597511050313,matched2020:-0.06044576798649548,spy2020:-0.1597382388575862,folds2020:2,sharpe2020:-0.4401275593792908,state:'FIXED_EQUITY_BOND_SEASONAL_ALLOCATOR_REJECTED'};
test('bind exact P88 product head',()=>assert.equal(MM_HEAD,'b255fe911c0c5a3d95f695939cec51e6da841105'));
test('P88 fixed seasonal allocator is rejected',()=>{assert.equal(p88.run,34360627098);assert.equal(p88.job,102496369730);assert.equal(p88.artifact,10107654619);assert.ok(p88.artifactDigest.startsWith('sha256:'));assert.ok(p88.matchedFull<0);assert.ok(p88.spyFull<0);assert.ok(p88.matched2020<0);assert.ok(p88.spy2020<0);assert.equal(p88.folds2020,2);assert.ok(p88.sharpe2020<0);assert.equal(p88.state,'FIXED_EQUITY_BOND_SEASONAL_ALLOCATOR_REJECTED')});
test('P88 consequence grants no ranking timing allocation or trading authority',()=>assert.deepEqual(Object.values({ranking:false,allocation:false,sizing:false,timing:false,promotion:false,tuning:false,strategy:false,runtime:false,data:false,broker:false,live:false}),Array(11).fill(false)));
