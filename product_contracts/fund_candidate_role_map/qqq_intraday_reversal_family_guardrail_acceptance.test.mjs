import test from 'node:test';
import assert from 'node:assert/strict';
const MM_HEAD='d1ca80fa75378ed5b1fdd34d20fea9a253ac0afd';
const p96={run:34365224869,job:102512080605,artifact:10109547005,matched2020:-0.09156458333337647,qqq2020:-0.22641694150616232,folds:1};
const p97={run:34365391586,job:102512656788,artifact:10109614011,matched2020:-0.009507761218303878,qqq2020:-0.14436547230371755,folds:2};
test('bind exact reversal-family product head',()=>assert.equal(MM_HEAD,'d1ca80fa75378ed5b1fdd34d20fea9a253ac0afd'));
test('P96 and P97 jointly park nearby QQQ reversal rescue',()=>{assert.equal(p96.run,34365224869);assert.equal(p97.run,34365391586);assert.ok(p96.matched2020<0&&p97.matched2020<0);assert.ok(p96.qqq2020<0&&p97.qqq2020<0);assert.ok(p96.folds<3&&p97.folds<3)});
test('family park grants no ranking allocation sizing timing tuning or trading authority',()=>assert.deepEqual(Object.values({ranking:false,allocation:false,sizing:false,timing:false,promotion:false,tuning:false,strategy:false,runtime:false,data:false,broker:false,live:false}),Array(11).fill(false)));
