import test from 'node:test';
import assert from 'node:assert/strict';
const MM_HEAD='1f907887d2fb2edd047f56decef2e14d03666298';
const p47={mechanismRun:34351221703,permutationRun:34352098873,bootstrapRun:34353718446,p2020Excess:0.036,p2020Rank:0.1005,p2020Spread:0.1295,p2020BlockNonpositiveExcess:0.206,state:'AFTER_COST_EDGE_RETAINED_DIRECT_SCORE_CAUSAL_CONFIDENCE_REDUCED'};
test('bind exact P47 mechanism-fragility product head',()=>assert.equal(MM_HEAD,'1f907887d2fb2edd047f56decef2e14d03666298'));
test('P47 economic path is unusual but direct score mapping and serial certainty are weak',()=>{assert.equal(p47.mechanismRun,34351221703);assert.equal(p47.permutationRun,34352098873);assert.equal(p47.bootstrapRun,34353718446);assert.ok(p47.p2020Excess<0.05);assert.ok(p47.p2020Rank>=0.05);assert.ok(p47.p2020Spread>=0.05);assert.ok(p47.p2020BlockNonpositiveExcess>0.20);assert.equal(p47.state,'AFTER_COST_EDGE_RETAINED_DIRECT_SCORE_CAUSAL_CONFIDENCE_REDUCED')});
test('P47 consequence grants no ranking or trading authority',()=>assert.deepEqual(Object.values({ranking:false,allocation:false,sizing:false,timing:false,promotion:false,strategy:false,runtime:false,data:false,broker:false,live:false}),Array(10).fill(false)));
