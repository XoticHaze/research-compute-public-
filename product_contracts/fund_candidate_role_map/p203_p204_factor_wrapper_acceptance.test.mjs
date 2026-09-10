import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD='b2bbd974643607c3a35a0941ae3162efe8642c30'
const p203=Object.freeze({state:'PARK',decision:'MODEL_FORMULATION_REJECT_FUND_FACTOR_NO_INCREMENTAL_ALPHA',run:34430757953,job:102725580700,started:'2026-09-10T02:46:36Z',head:'5c19303a0083e5c5c1bfa1cfd98f9e1ebdd108a2',artifact:10134388257,artifact_sha:'6180e9cb970d8992c1f0a1e5398727c42aeeb693af1747574e0cac86e861ec28',excess_spy:-0.007650335050272128,excess_iwf:-0.027493543978241997,positive_spy_folds:2,positive_iwf_folds:1})
const p204=Object.freeze({state:'PARK_STYLE_CONDITIONAL',decision:'MODEL_FORMULATION_REJECT_STYLE_EXCESS_NOT_PERSISTENT',run:34430868055,job:102725911175,started:'2026-09-10T02:48:21Z',head:'745deb74464ff0919d85b964098412e76d9886ca',artifact:10134428947,artifact_sha:'d01d343c1ba9bccbd81adb8ce19a1ad6d466c826bb10a5357364366e2ca70df1',full_excess_spy_bp:100,full_excess_iwf_bp:-99,from2018_excess_spy_bp:-38,from2020_excess_spy_bp:-49})
const boundaries={ranking:false,allocation:false,sizing:false,promotion:false,strategy_spec:false,runtime:false,data:false,broker:false,live_trading:false}

test('bind exact P203/P204 MM product head',()=>assert.equal(MM_PRODUCT_HEAD,'b2bbd974643607c3a35a0941ae3162efe8642c30'))
test('QUAL wrapper is rejected versus broad and growth controls',()=>{assert.equal(p203.state,'PARK');assert.ok(p203.excess_spy<0);assert.ok(p203.excess_iwf<0);assert.ok(p203.positive_spy_folds<3);assert.ok(p203.positive_iwf_folds<3)})
test('MTUM full-sample strength is style conditional, not persistent alpha',()=>{assert.equal(p204.state,'PARK_STYLE_CONDITIONAL');assert.ok(p204.full_excess_spy_bp>0);assert.ok(p204.full_excess_iwf_bp<0);assert.ok(p204.from2018_excess_spy_bp<0);assert.ok(p204.from2020_excess_spy_bp<0)})
test('preserve exact external science identities',()=>{assert.deepEqual([p203.run,p203.job,p203.started,p203.head,p203.artifact,p203.artifact_sha],[34430757953,102725580700,'2026-09-10T02:46:36Z','5c19303a0083e5c5c1bfa1cfd98f9e1ebdd108a2',10134388257,'6180e9cb970d8992c1f0a1e5398727c42aeeb693af1747574e0cac86e861ec28']);assert.deepEqual([p204.run,p204.job,p204.started,p204.head,p204.artifact,p204.artifact_sha],[34430868055,102725911175,'2026-09-10T02:48:21Z','745deb74464ff0919d85b964098412e76d9886ca',10134428947,'d01d343c1ba9bccbd81adb8ce19a1ad6d466c826bb10a5357364366e2ca70df1'])})
test('factor-wrapper guardrails grant no capital or trading authority',()=>assert.deepEqual(Object.values(boundaries),Array(Object.keys(boundaries).length).fill(false)))
