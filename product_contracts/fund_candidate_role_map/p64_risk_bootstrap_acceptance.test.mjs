import test from 'node:test';
import assert from 'node:assert/strict';
const MM_HEAD='175a04dbd49ae8154521013a599a90cfd92360d1';
const p64={run:34353600753,job:102472607751,artifact:10104770660,p20cagr:0.1105,p20sharpe:0.3635,p20calmar:0.366,p22cagr:0.1845,p22sharpe:0.2655,p22calmar:0.251};
test('bind exact P64 risk-bootstrap product head',()=>assert.equal(MM_HEAD,'175a04dbd49ae8154521013a599a90cfd92360d1'));
test('recent favorable point estimates are statistically fragile under paired block resampling',()=>{assert.equal(p64.run,34353600753);assert.equal(p64.job,102472607751);assert.equal(p64.artifact,10104770660);assert.ok(p64.p20cagr>0.10);assert.ok(p64.p20sharpe>0.35);assert.ok(p64.p20calmar>0.35);assert.ok(p64.p22cagr>0.18);assert.ok(p64.p22sharpe>0.25);assert.ok(p64.p22calmar>0.25)});
test('bootstrap consequence grants no portfolio or trading authority',()=>assert.deepEqual(Object.values({ranking:false,allocation:false,sizing:false,timing:false,promotion:false,strategy:false,runtime:false,data:false,broker:false,live:false}),Array(10).fill(false)));
