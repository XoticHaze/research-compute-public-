import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD='82de10722ff2d3ec8cdd18df091bfa406fc1f1e3'
const result=Object.freeze({
  run:34384151359,
  job:102576084014,
  started_at:'2026-09-09T17:38:36Z',
  science_head:'968d629d5bdab4591acc5b7902a2d9c9ed69499d',
  artifact:10117040207,
  artifact_digest:'sha256:95b58288932c29f2924d5b401e43e008e4ad85be8e90a4ef47ce4b5b7e8754e2',
  rows:239,
  vector_sha256:'a86493347faf3f64567c490eaa514761912557da5db029cdb13461790578ac5b',
  source_panel_sha256:'eeee61d2b08621c6dcbff826855224370f073fcabb08ea49e190a65813236561',
  matched_excess_cagr:0.041851444892579304,
  qqq_gap_cagr:-0.027385451598155974,
  decision:'P46_MONTHLY_SLEEVE_VECTOR_MATERIALIZED',
})

test('bind exact P46 product and science heads',()=>{assert.equal(MM_PRODUCT_HEAD,'82de10722ff2d3ec8cdd18df091bfa406fc1f1e3');assert.equal(result.science_head,'968d629d5bdab4591acc5b7902a2d9c9ed69499d')})
test('bind exact immutable return vector',()=>{assert.equal(result.rows,239);assert.equal(result.vector_sha256,'a86493347faf3f64567c490eaa514761912557da5db029cdb13461790578ac5b');assert.equal(result.source_panel_sha256,'eeee61d2b08621c6dcbff826855224370f073fcabb08ea49e190a65813236561')})
test('preserve matched support and QQQ opportunity gap together',()=>{assert.ok(result.matched_excess_cagr>0.0418);assert.ok(result.qqq_gap_cagr<-0.0273)})
test('materialization is not portfolio promotion',()=>{assert.equal(result.decision,'P46_MONTHLY_SLEEVE_VECTOR_MATERIALIZED');assert.deepEqual(Object.values({ranking:false,allocation:false,sizing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,live:false}),Array(9).fill(false))})
