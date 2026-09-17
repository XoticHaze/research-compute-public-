from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf

SYMS=['CWB','SPY','IEF','BIL']; START='2008-01-01'; END='2026-09-10'; COST_BPS=10; BETA_MONTHS=36
raw=yf.download(SYMS,start=START,end=END,auto_adjust=True,progress=False,threads=False)
px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[SYMS].dropna().resample('ME').last()
r=px.pct_change().dropna()
rows=[]
prev_w=None
for i in range(BETA_MONTHS,len(r)):
    hist=r.iloc[i-BETA_MONTHS:i]
    if hist[SYMS].isna().any().any():
        continue
    y=hist.CWB.to_numpy()
    X=np.column_stack([np.ones(len(hist)),hist.SPY.to_numpy(),hist.IEF.to_numpy()])
    beta=np.linalg.lstsq(X,y,rcond=None)[0]
    ws=max(0.0,min(1.0,float(beta[1]))); wi=max(0.0,min(1.0,float(beta[2])))
    s=ws+wi
    if s>1.0:
        ws/=s; wi/=s
    wb=1.0-ws-wi
    cur=r.iloc[i]
    if cur[SYMS].isna().any():
        continue
    matched=ws*cur.SPY+wi*cur.IEF+wb*cur.BIL
    w=np.array([ws,wi,wb])
    turn=1.0 if prev_w is None else float(np.abs(w-prev_w).sum()/2.0)
    matched_net=float(matched-turn*COST_BPS/10000)
    cwb_net=float(cur.CWB-(COST_BPS/10000 if prev_w is None else 0.0))
    rows.append((r.index[i],cwb_net,matched_net,float(cur.SPY),turn,ws,wi,wb))
    prev_w=w
z=pd.DataFrame(rows,columns=['date','strategy','matched','spy','matched_turnover','beta_spy','beta_ief','w_bil']).set_index('date')

def stats(s):
    s=s.dropna(); w=(1+s).cumprod(); yrs=len(s)/12; sd=s.std()
    return {'months':int(len(s)),'cagr':float(w.iloc[-1]**(1/yrs)-1),'sharpe':float(s.mean()/sd*math.sqrt(12)) if sd>0 else 0.0,'max_drawdown':float((w/w.cummax()-1).min())}
res={}
for name,start in {'2013_plus':'2013-01-01','2018_plus':'2018-01-01','2020_plus':'2020-01-01','2022_plus':'2022-01-01'}.items():
    q=z.loc[start:]
    a,b,c=stats(q.strategy),stats(q.matched),stats(q.spy)
    res[name]={'convertible':a,'causal_beta_matched':b,'spy_context':c,'matched_excess_cagr':a['cagr']-b['cagr'],'spy_opportunity_gap_cagr':a['cagr']-c['cagr'],'mean_matched_turnover':float(q.matched_turnover.mean()),'mean_beta_spy':float(q.beta_spy.mean()),'mean_beta_ief':float(q.beta_ief.mean()),'mean_cash_weight':float(q.w_bil.mean())}
q=z.loc['2013-01-01':]
folds=[]
for f in np.array_split(q,5):
    folds.append(stats(f.strategy)['cagr']-stats(f.matched)['cagr'])
passed=all(res[k]['matched_excess_cagr']>0 for k in res) and sum(x>0 for x in folds)>=3
decision='P331_CONVERTIBLE_CONVEXITY_SUPPORTED' if passed else 'P331_CONVERTIBLE_CONVEXITY_NOT_SUPPORTED'
out={'schema':'research.p331_convertible_convexity_r1','parent':'P331','claim':'Test fixed convertible-bond convexity/premium via CWB against a chronologically causal one-month-lagged 36-month rolling SPY+IEF beta-matched benchmark with BIL residual cash and 10bp friction. Fixed beta window, clipping, products, costs, windows, and chronology folds; no tuning.','cost_bps':COST_BPS,'beta_months':BETA_MONTHS,'results':res,'chronology_fold_matched_excess_cagr':folds,'positive_folds':sum(x>0 for x in folds),'decision_rule':'Support only if after-cost matched excess CAGR is positive in all fixed windows and >=3/5 chronology folds. Failure rejects this fixed CWB convexity/premium formulation without beta-window, clipping, product, cost, or date rescue.','decision':decision,'limitations':['fund-level convertible proxy, not security-level convertible decomposition','causal rolling linear beta benchmark is an exposure-matched approximation rather than option-theoretic replication','single adjusted-price provider','no portfolio ranking/allocation/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True)
Path('research/artifacts/p331_convertible_convexity_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps(out,sort_keys=True))
