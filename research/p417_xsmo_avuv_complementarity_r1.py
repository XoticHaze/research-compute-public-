from __future__ import annotations
import json, math
from pathlib import Path
import pandas as pd, numpy as np, yfinance as yf
T=['XSMO','AVUV','IJR']; COST=0.0025
x=yf.download(T,start='2019-01-01',auto_adjust=True,progress=False,threads=False)
if x.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=x['Close'] if isinstance(x.columns,pd.MultiIndex) else x
r=c[T].resample('ME').last().dropna().pct_change().dropna()
def charge(s):
 y=s.copy()
 if len(y): y.iloc[0]-=COST; y.iloc[-1]-=COST
 return y
def cagr(s): return float((1+s).prod()**(12/len(s))-1) if len(s) else float('nan')
def sh(s):
 sd=s.std(ddof=1); return float(np.sqrt(12)*s.mean()/sd) if len(s)>1 and sd>0 else float('nan')
def dd(s):
 w=(1+s).cumprod(); return float((w/w.cummax()-1).min()) if len(s) else float('nan')
q=r.loc['2020-01-01':].copy()
xs=charge(q.XSMO); av=charge(q.AVUV); ctl=charge(q.IJR)
ex_xs=xs-ctl; ex_av=av-ctl
blocks=[('2020-01-01','2021-12-31'),('2022-01-01','2023-12-31'),('2024-01-01',None)]
block_corr=[]
for a,b in blocks:
 z=pd.concat([ex_xs.loc[a:b],ex_av.loc[a:b]],axis=1).dropna()
 block_corr.append(float(z.corr().iloc[0,1]) if len(z)>=6 else None)
overall=float(pd.concat([ex_xs,ex_av],axis=1).dropna().corr().iloc[0,1])
combo=charge(0.5*q.XSMO+0.5*q.AVUV)
combo_ctl=charge(q.IJR)
metrics={'months':len(combo),'xsmo_cagr':cagr(xs),'avuv_cagr':cagr(av),'ijr_cagr':cagr(ctl),'combo_cagr':cagr(combo),'combo_matched_excess_pp':100*(cagr(combo)-cagr(combo_ctl)),'xsmo_sharpe':sh(xs),'avuv_sharpe':sh(av),'combo_sharpe':sh(combo),'combo_max_drawdown':dd(combo),'xsmo_max_drawdown':dd(xs),'avuv_max_drawdown':dd(av)}
low_blocks=sum(v is not None and abs(v)<0.6 for v in block_corr)
passed=abs(overall)<0.5 and low_blocks>=2 and metrics['combo_matched_excess_pp']>0
out={'schema':'research.p417_xsmo_avuv_complementarity.v1','workload_id':'P417_XSMO_AVUV_COMPLEMENTARITY_R1','parent':'SMALL_CAP_FACTOR_COMPLEMENTARITY','claim':'With both factor sleeves held fixed, XSMO-IJR momentum excess and AVUV-IJR small-value excess are sufficiently distinct to support scientific complementarity; a frozen 50/50 diagnostic is used only to verify combined matched excess, not to select weights.','cost_bps_each_endpoint':25,'overall_excess_correlation':overall,'block_excess_correlations':block_corr,'blocks_below_abs_0_6':low_blocks,'metrics':metrics,'decision_rule':'COMPLEMENTARITY_SUPPORTED only if overall |residual-excess correlation|<0.5, at least 2/3 fixed blocks have |corr|<0.6, and the frozen 50/50 XSMO+AVUV diagnostic has positive after-cost excess over IJR. No weight/product/window optimization.','decision':'SMALL_CAP_FACTOR_COMPLEMENTARITY_SUPPORTED' if passed else 'SMALL_CAP_FACTOR_COMPLEMENTARITY_NOT_SUPPORTED','scientific_consequence':('Small-cap momentum and small-value exhibit scientifically useful complementary excess sources in this fixed fund representation; allocation/ranking remains outside this role.' if passed else 'Do not infer independent small-cap alpha sources from the two survivor labels alone; preserve each sleeve evidence and classify this only as combination/redundancy evidence.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p417_xsmo_avuv_complementarity_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'overall_corr':round(overall,3),'block_corr':[None if v is None else round(v,3) for v in block_corr],'combo_excess_pp':round(metrics['combo_matched_excess_pp'],3)},sort_keys=True))