from __future__ import annotations
import json
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
T=['SPMO','IJS','SPY','IJR','AVDV','VSS']; COST=0.0025
x=yf.download(T,start='2019-09-01',auto_adjust=True,progress=False,threads=False)
if x.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=x['Close'] if isinstance(x.columns,pd.MultiIndex) else x
m=c[T].resample('ME').last().dropna(); r=m.pct_change().dropna()
if len(r)<60: raise SystemExit('SOURCE_FAILURE_SHORT_OVERLAP')
def charge(s):
 y=s.copy()
 if len(y): y.iloc[0]-=COST; y.iloc[-1]-=COST
 return y
def cagr(s): return float((1+s).prod()**(12/len(s))-1) if len(s) else float('nan')
def sh(s):
 sd=s.std(ddof=1); return float(np.sqrt(12)*s.mean()/sd) if len(s)>1 and sd>0 else float('nan')
def dd(s):
 w=(1+s).cumprod(); return float((w/w.cummax()-1).min()) if len(s) else float('nan')
p305=0.5*r.SPMO+0.5*r.IJS; p305ctl=0.5*r.SPY+0.5*r.IJR
av=r.AVDV; avctl=r.VSS
ex1=p305-p305ctl; ex2=av-avctl
blocks={'2020-2021':('2020-01-01','2021-12-31'),'2022-2023':('2022-01-01','2023-12-31'),'2024+':('2024-01-01',None)}
corr_overall=float(ex1.loc['2020-01-01':].corr(ex2.loc['2020-01-01':]))
block_corr={k:float(ex1.loc[a:b].corr(ex2.loc[a:b])) for k,(a,b) in blocks.items()}
block_pass=sum(abs(v)<0.4 for v in block_corr.values())
blend=0.25*r.SPMO+0.25*r.IJS+0.5*r.AVDV; ctl=0.25*r.SPY+0.25*r.IJR+0.5*r.VSS
q=charge(blend.loc['2020-01-01':]); z=charge(ctl.reindex(q.index)); p=charge(p305.reindex(q.index)); pc=charge(p305ctl.reindex(q.index))
blend_excess=100*(cagr(q)-cagr(z)); p305_excess=100*(cagr(p)-cagr(pc))
pass_gate=abs(corr_overall)<0.4 and block_pass>=2 and blend_excess>0 and sh(q)>=sh(p) and dd(q)>=dd(p)
out={'schema':'research.p403_p305_avdv_complementarity.v1','workload_id':'P403_P305_AVDV_COMPLEMENTARITY_R1','parent':'INTERNATIONAL_SMALL_VALUE_SELECTION_PREMIUM','claim':'P401 AVDV relative excess can complement the already-supported fixed P305 momentum/small-value return source without weight search.','period':'2020+','cost_bps_each_endpoint':25,'residual_correlation_overall':corr_overall,'block_correlations':block_corr,'block_correlation_pass_count':block_pass,'blend_definition':'25% SPMO + 25% IJS + 50% AVDV','matched_control':'25% SPY + 25% IJR + 50% VSS','blend_cagr':cagr(q),'matched_control_cagr':cagr(z),'blend_matched_excess_pp':blend_excess,'p305_cagr':cagr(p),'p305_control_cagr':cagr(pc),'p305_matched_excess_pp':p305_excess,'blend_sharpe':sh(q),'p305_sharpe':sh(p),'blend_max_drawdown':dd(q),'p305_max_drawdown':dd(p),'decision_rule':'COMPLEMENTS only if |overall residual correlation|<0.4, >=2/3 fixed block correlations are <0.4 in absolute value, the fixed blend has positive matched excess, Sharpe is no worse than P305 alone, and drawdown is no worse than P305 alone. No weight/product/window/cost tuning after observation.','decision':'P401_COMPLEMENTS_P305' if pass_gate else 'P401_COMPLEMENTARITY_NOT_ESTABLISHED','scientific_consequence':('P401 supplies a distinct enough after-cost return source to justify preserving complementarity evidence alongside P305; this is not portfolio allocation authority and weights remain frozen diagnostics.' if pass_gate else 'Do not claim P401 complements P305 under this fixed diagnostic. Preserve P401 standalone passing evidence and classify this as a portfolio-fit/complementarity weakness rather than a standalone model failure.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p403_p305_avdv_complementarity_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'corr':round(corr_overall,3),'blocks':{k:round(v,3) for k,v in block_corr.items()},'blend_excess_pp':round(blend_excess,3),'blend_sharpe':round(sh(q),3),'p305_sharpe':round(sh(p),3)},sort_keys=True))
