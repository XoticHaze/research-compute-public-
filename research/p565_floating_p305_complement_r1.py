from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf

T=['SPMO','IJS','SPY','IJR','FLRN','SHV']
START='2012-01-01'; END='2026-09-12'; EP=.0025; TC=.001
ART=Path('research/artifacts'); ART.mkdir(parents=True,exist_ok=True); OUT=ART/'p565_floating_p305_complement_r1.json'
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
r=c[T].resample('ME').last().pct_change(fill_method=None)

def ew_net(a,b):
    q=pd.concat([a,b],axis=1).dropna(); out=[]
    for ra,rb in q.to_numpy(float):
        gross=.5*ra+.5*rb; denom=1+gross
        if denom<=0: out.append(np.nan); continue
        w1=.5*(1+ra)/denom; w2=.5*(1+rb)/denom
        traded=abs(w1-.5)+abs(w2-.5)
        out.append(gross-TC*traded)
    return pd.Series(out,index=q.index,dtype=float)

p305=ew_net(r.SPMO,r.IJS); pctl=ew_net(r.SPY,r.IJR)
chall=ew_net(p305,r.FLRN); mctl=ew_net(pctl,r.SHV)
base=pd.concat({'challenger':chall,'matched_control':mctl,'p305':p305,'p305_control':pctl,'flrn':r.FLRN,'shv':r.SHV},axis=1).dropna()

def stats(s):
    x=s.dropna().astype(float)
    if len(x)<12:return {'months':int(len(x))}
    y=x.to_numpy(float).copy(); y[0]-=EP; y[-1]-=EP
    w=np.cumprod(1+y); yrs=len(y)/12
    cagr=float(w[-1]**(1/yrs)-1); vol=float(np.std(y,ddof=1)*math.sqrt(12)); sh=float(np.mean(y)*12/vol) if vol>0 else None
    dd=float(np.min(w/np.maximum.accumulate(w)-1))
    return {'months':int(len(y)),'cagr':cagr,'vol':vol,'sharpe':sh,'max_drawdown':dd}

def frame(start,end=None):
    q=base.loc[start:end].dropna(); a=stats(q.challenger); m=stats(q.matched_control); p=stats(q.p305)
    corr=float((q.flrn-q.shv).corr(q.p305-q.p305_control)) if len(q)>=12 else None
    return {'months':int(len(q)),'challenger':a,'matched_control':m,'p305':p,
      'matched_excess_pp':100*(a['cagr']-m['cagr']),
      'p305_cagr_delta_pp':100*(a['cagr']-p['cagr']),
      'sharpe_delta_vs_p305':None if a['sharpe'] is None or p['sharpe'] is None else a['sharpe']-p['sharpe'],
      'maxdd_improvement_vs_p305_pp':100*(a['max_drawdown']-p['max_drawdown']),
      'residual_corr':corr}
windows={'2013+':frame('2013-01-01'),'2018+':frame('2018-01-01'),'2020+':frame('2020-01-01'),'2022+':frame('2022-01-01')}
blocks={'2013_2016':frame('2013-01-01','2016-12-31'),'2017_2020':frame('2017-01-01','2020-12-31'),'2021_2023':frame('2021-01-01','2023-12-31'),'2024_plus':frame('2024-01-01')}
posw=sum(v['months']>=24 and v['matched_excess_pp']>0 for v in windows.values()); posb=sum(v['months']>=18 and v['matched_excess_pp']>0 for v in blocks.values())
coverage=all(v['months']>=18 for v in blocks.values()); full=windows['2013+']; corr=full['residual_corr']
passed=(coverage and posw>=3 and posb>=3 and full['matched_excess_pp']>0 and corr is not None and abs(corr)<=.35 and full['sharpe_delta_vs_p305'] is not None and full['sharpe_delta_vs_p305']>0 and full['maxdd_improvement_vs_p305_pp']>0)
out={'schema':'research.p565_floating_p305_complement_r1.v1','workload_id':'P565_FLOATING_P305_COMPLEMENT_R1','parent':'FLOATING_RATE_IG_CREDIT_CARRY','claim':'A frozen 50/50 P305+FLRN diagnostic should preserve positive after-cost matched excess and improve P305 risk efficiency while FLRN-SHV residuals remain distinct from P305 residuals; CAGR opportunity cost versus P305 is reported explicitly and never optimized away.','contract':{'monthly_rebalance_traded_notional_cost_bps':10,'endpoint_cost_bps_each':25,'fixed_weight':.5,'windows':['2013+','2018+','2020+','2022+'],'blocks':['2013_2016','2017_2020','2021_2023','2024_plus'],'max_abs_residual_corr':.35,'parameter_search':False},'windows':windows,'blocks':blocks,'positive_windows':int(posw),'positive_blocks':int(posb),'coverage_ready':coverage,'decision_rule':'SUPPORTED only if all blocks have >=18 months, >=3/4 fixed windows and >=3/4 chronology blocks have positive challenger-vs-matched-control excess, full matched excess is positive, abs residual correlation<=0.35, and full-history Sharpe and max drawdown both improve versus P305. P305 CAGR opportunity cost is reported but not optimized. No weight/date/cost/correlation rescue.','decision':('FLOATING_P305_COMPLEMENTARITY_SUPPORTED' if passed else ('FLOATING_P305_COMPLEMENT_SOURCE_COVERAGE_NOT_READY' if not coverage else 'FLOATING_P305_COMPLEMENTARITY_NOT_SUPPORTED')),'scientific_consequence':('Strengthen floating-rate IG alpha as a scientifically complementary return source beside P305 under a frozen non-optimized diagnostic; report CAGR opportunity cost and leave allocation authority to Coordinator.' if passed else ('Record coverage insufficiency only; preserve P560/P561 evidence.' if not coverage else 'Record failed complementarity without erasing P560/P561 standalone alpha; do not tune weights/costs/correlation threshold to rescue.')),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'positive_windows':posw,'positive_blocks':posb,'full_matched_excess_pp':round(full['matched_excess_pp'],3),'full_p305_cagr_delta_pp':round(full['p305_cagr_delta_pp'],3),'full_sharpe_delta':None if full['sharpe_delta_vs_p305'] is None else round(full['sharpe_delta_vs_p305'],3),'full_maxdd_improvement_pp':round(full['maxdd_improvement_vs_p305_pp'],3),'residual_corr':None if corr is None else round(corr,3)},sort_keys=True))
