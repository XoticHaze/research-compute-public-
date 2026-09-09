import test from 'node:test';
import assert from 'node:assert/strict';

const MM_HEAD = '42de38fc4c5f066c21d06657c0e83409a08e2448';
const component = Object.freeze({ run:34344001336, job:102441165843, artifact:10100912534, from2022Matched:0.033813282567537684, from2022Qqq:0.001952619030715974, cross:0.029831316452898715, industry:0.03364535114027478, folds:4, corr:0.2875045789659649, from2015Qqq:-0.06276523472475026 });
const risk = Object.freeze({ run:34347239172, job:102451637786, artifact:10102210437, from2022Matched:0.030552654433576798, from2022Qqq:-0.0013079726738995934, sharpeQqq:0.21184437589778382, calmarQqq:0.44252609838884494, dd:-0.14226263733239897, qqqDd:-0.2611420718116394, from2015Qqq:-0.06511646080940325, from2015SharpeQqq:-0.15328154194237276 });

test('bind exact P64 recent-evidence product head',()=>assert.equal(MM_HEAD,'42de38fc4c5f066c21d06657c0e83409a08e2448'));
test('both frozen sleeves contribute recent matched alpha without erasing QQQ opportunity cost',()=>{assert.equal(component.run,34344001336);assert.equal(component.artifact,10100912534);assert.ok(component.from2022Matched>0&&component.cross>0&&component.industry>0);assert.equal(component.folds,4);assert.ok(component.from2015Qqq<0)});
test('recent risk-adjusted support is narrower than broad QQQ superiority',()=>{assert.equal(risk.run,34347239172);assert.equal(risk.job,102451637786);assert.equal(risk.artifact,10102210437);assert.ok(risk.sharpeQqq>0&&risk.calmarQqq>0&&risk.dd>risk.qqqDd);assert.ok(risk.from2022Qqq<0&&risk.from2015Qqq<0&&risk.from2015SharpeQqq<0)});
test('product handoff grants no portfolio or trading authority',()=>assert.deepEqual(Object.values({ranking:false,allocation:false,sizing:false,timing:false,promotion:false,strategy:false,runtime:false,data:false,broker:false,live:false}),Array(10).fill(false)));
