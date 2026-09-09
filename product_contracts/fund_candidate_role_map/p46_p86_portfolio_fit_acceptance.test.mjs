import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD='bf20679bebbf9d01689f1e8a0cff291c718382aa'
const result=Object.freeze({run_id:34371464431,job_id:102533465869,artifact_id:10112086926,artifact_digest:'sha256:597fea907c989d1566c013d5e7ccac25b2083ed43b0e19867005812f35580d8a',from2020_excess_vs_p86:0.008529574206989299,from2020_excess_vs_p46:-0.0027537061310631827,from2020_excess_vs_qqq:-0.045592842434651226,from2020_sharpe_delta_vs_p86:0.29023604233966727,positive_folds_vs_p86:3,from2015_excess_vs_qqq:-0.060276268351243445,from2022_excess_vs_qqq:-0.014887015194637865})

test('bind exact MM P46 P86 portfolio-fit product head',()=>assert.equal(MM_PRODUCT_HEAD,'bf20679bebbf9d01689f1e8a0cff291c718382aa'))
test('portfolio fit is supported only as risk-adjusted diversification',()=>{assert.equal(result.run_id,34371464431);assert.equal(result.job_id,102533465869);assert.equal(result.artifact_id,10112086926);assert.ok(result.from2020_excess_vs_p86>0);assert.ok(result.from2020_sharpe_delta_vs_p86>0);assert.equal(result.positive_folds_vs_p86,3)})
test('alpha opportunity-cost promotion remains rejected',()=>{assert.ok(result.from2020_excess_vs_p46<0);assert.ok(result.from2020_excess_vs_qqq<0);assert.ok(result.from2015_excess_vs_qqq<0);assert.ok(result.from2022_excess_vs_qqq<0)})
test('product acceptance grants no portfolio or trading authority',()=>{const b={portfolioRanking:false,allocation:false,sizing:false,leverage:false,timing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,liveTrading:false};assert.deepEqual(Object.values(b),Array(11).fill(false))})
