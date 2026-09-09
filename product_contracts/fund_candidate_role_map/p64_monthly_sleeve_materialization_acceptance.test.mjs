import test from 'node:test'
import assert from 'node:assert/strict'
const MM_PRODUCT_HEAD='1e957af6ac18b65b00c96f4e176dccda864def2d'
const r=Object.freeze({run:34384489441,job:102577235307,started_at:'2026-09-09T17:41:55Z',science_head:'7e4dbd25bca641daa438162bb62869512b2ac369',artifact:10117167468,artifact_digest:'sha256:b645e797bf551cd1ef8fb1e1596c8998fc67178a24116a77ab6acdd91dce98fb',rows:234,vector_sha256:'16c823cca3f620463204b2a439f8400f0f51bb6c102b3286ba207c235a98f821',matched_gap:-0.0022704530545865076,qqq_gap:-0.05785686137017265,decision:'P64_INVESTABLE_MONTHLY_SLEEVE_VECTOR_MATERIALIZED'})
test('bind exact P64 product and science heads',()=>{assert.equal(MM_PRODUCT_HEAD,'1e957af6ac18b65b00c96f4e176dccda864def2d');assert.equal(r.science_head,'7e4dbd25bca641daa438162bb62869512b2ac369')})
test('bind exact P64 vector',()=>{assert.equal(r.rows,234);assert.equal(r.vector_sha256,'16c823cca3f620463204b2a439f8400f0f51bb6c102b3286ba207c235a98f821')})
test('fail closed on current investable economics',()=>{assert.ok(r.matched_gap<0);assert.ok(r.qqq_gap<0);assert.equal(r.decision,'P64_INVESTABLE_MONTHLY_SLEEVE_VECTOR_MATERIALIZED')})
test('no portfolio or trading authority',()=>assert.deepEqual(Object.values({ranking:false,allocation:false,sizing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,live:false}),Array(9).fill(false)))
