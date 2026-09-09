import test from 'node:test';
import assert from 'node:assert/strict';
const MM_HEAD='befd6c18fa8070a0983eed065ff7bf6626d7450c';
const d={run:34347916732,job:102453835212,artifact:10102487639,one20m:0.033304,one20q:-0.030328,one20folds:3,five20m:0.013184,five20q:-0.052009,five20folds:2,five15m:-0.005401,five15q:-0.072525,five15folds:1,dd:-0.1874,qqqdd:-0.3245};
test('bind exact P64 delay-demotion product head',()=>assert.equal(MM_HEAD,'befd6c18fa8070a0983eed065ff7bf6626d7450c'));
test('combined delay demotes broad alpha while preserving only narrow recent risk context',()=>{assert.equal(d.run,34347916732);assert.equal(d.job,102453835212);assert.equal(d.artifact,10102487639);assert.ok(d.one20m>0&&d.one20q<0);assert.ok(d.five20m>0&&d.five20q<0&&d.five20folds<3);assert.ok(d.five15m<0&&d.five15q<0&&d.five15folds===1);assert.ok(d.dd>d.qqqdd)});
test('delay consequence grants no portfolio or trading authority',()=>assert.deepEqual(Object.values({ranking:false,allocation:false,sizing:false,timing:false,promotion:false,strategy:false,runtime:false,data:false,broker:false,live:false}),Array(10).fill(false)));
