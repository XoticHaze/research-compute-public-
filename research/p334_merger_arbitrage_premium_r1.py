from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf

SYMS=['MNA','SPY','BIL']; START='2009-01-01'; END='2026-09-10'; COST_BPS=10; BETA_MONTHS=36
raw=yf.download(SYMS,start=START,end=END,auto_adjust=True,progress=False,threads=False)
px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[SYMS].dropna().resample('ME').last(); r=px.pct_change().dropna()
rows=[]; prev=None
for i in range(BETA_MONTHS,len(r)):
    h=r.iloc[i-BETA_MONTHS:i]
    X=np.column_stack([np.ones(len(h)),h.SPY.to_numpy()]); y=h.MNA.to_numpy(); b=np.linalg.lstsq(X,y,rcond=None)[0]
    ws=max(0.0,min(1.0,float(b[1]))); wb=1.0-ws; cur=r.iloc[i]
    matched=ws*cur.SPY+wb*cur.BIL; w=np.array([ws,wb]); turn=1.0 if prev is None else float(np.abs(w-prev).sum()/2.0)
    rows.append((r.index[i],float(cur.MNA-(COST_BPS/10000 if prev is None else 0.0)),float(matched-turn*COST_BPS/10000),float(cur.SPY),turn,ws,wb)); prev=w
z=pd.DataFrame(rows,columns=['date','strategy','matched','spy','turnover','beta_spy','w_bil']).set_index('date')
def stats(s):
    s=s.dropna(); w=(1+s).cumprod(); yrs=len(s)/12; sd=s.std(); return {'months':int(len(s)),'cagr':float(w.iloc[-1]**(1/yrs)-1),'sharpe':float(s.mean()/sd*math.sqrt(12)) if sd>0 else 0.0,'max_drawdown':float((w/w.cummax()-1).min())}
res={}
for name,start in {'2014_plus':'2014-01-01','2018_plus':'2018-01-01','2020_plus':'2020-01-01','2022_plus':'2022-01-01'}.items():
    q=z.loc[start:]; a,b,c=stats(q.strategy),stats(q.matched),stats(q.spy)
    res[name]={'merger_arbitrage':a,'causal_beta_matched':b,'spy_context':c,'matched_excess_cagr':a['cagr']-b['cagr'],'spy_opportunity_gap_cagr':a['cagr']-c['cagr'],'mean_beta_spy':float(q.beta_spy.mean()),'mean_cash_weight':float(q.w_bil.mean()),'mean_matched_turnover':float(q.turnover.mean())}
q=z.loc['2014-01-01':]; folds=[stats(f.strategy)['cagr']-stats(f.matched)['cagr'] for f in np.array_split(q,5)]; passed=all(res[k]['matched_excess_cagr']>0 for k in res) and sum(x>0 for x in folds)>=3
decision='P334_MERGER_ARBITRAGE_PREMIUM_SUPPORTED' if passed else 'P334_MERGER_ARBITRAGE_PREMIUM_NOT_SUPPORTED'
out={'schema':'research.p334_merger_arbitrage_premium_r1','parent':'P334','claim':'Test fixed merger-arbitrage event-risk premium via MNA against a chronologically causal one-month-lagged 36-month SPY beta-matched benchmark with BIL residual cash and 10bp friction, across fixed 2014+/2018+/2020+/2022+ windows and five chronology folds. No beta-window, clipping, product, cost, or date tuning.','cost_bps':COST_BPS,'beta_months':BETA_MONTHS,'results':res,'chronology_fold_matched_excess_cagr':folds,'positive_folds':sum(x>0 for x in folds),'decision_rule':'Support only if after-cost matched excess CAGR is positive in all fixed windows and >=3/5 chronology folds. Failure rejects this fixed fund-level merger-arbitrage formulation without beta-window, product, cost, or date rescue.','decision':decision,'limitations':['fund-level merger-arbitrage proxy rather than deal-level reconstruction','causal rolling equity-beta benchmark does not replicate nonlinear deal-break risk','single adjusted-price provider','no portfolio ranking/allocation/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p334_merger_arbitrage_premium_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
