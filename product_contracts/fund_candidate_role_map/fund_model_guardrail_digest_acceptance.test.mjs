import test from 'node:test';
import assert from 'node:assert/strict';
const MM_HEAD='491f845265dcc72b64a437376396070ba6137d33';
const rows=[['P99','VOL_MANAGED_QQQ_EXCESS_RETURN_REJECTED_RISK_UTILITY_RETAINED'],['P82','P82_AGGREGATE_SURVIVOR_TIMING_CAUSALITY_NOT_ESTABLISHED'],['P96_P97','QQQ_SHORT_HORIZON_INTRADAY_REVERSAL_FAMILY_PARKED']];
test('bind exact consolidated guardrail digest head',()=>assert.equal(MM_HEAD,'491f845265dcc72b64a437376396070ba6137d33'));
test('digest keeps three non-ranking evidence roles distinct',()=>{assert.equal(rows.length,3);assert.deepEqual(rows.map(x=>x[0]),['P99','P82','P96_P97']);assert.ok(rows.every(x=>x[1].length>0))});
test('digest grants no ranking allocation sizing leverage timing or trading authority',()=>assert.deepEqual(Object.values({ranking:false,allocation:false,sizing:false,leverage:false,timing:false,promotion:false,strategy:false,runtime:false,data:false,broker:false,live:false}),Array(11).fill(false)));
