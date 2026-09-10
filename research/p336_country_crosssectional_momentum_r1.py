from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf

COUNTRIES=['EWA','EWC','EWG','EWH','EWI','EWJ','EWL','EWM','EWN','EWS','EWT','EWU','EWW','EWY','EWQ','EWP']
ALL=COUNTRIES+['SPY']; START='2001-01-01'; END='2026-09-10'; COST_BPS=25; TOP_K=3
raw=yf.download(ALL,start=START,end=END,auto_adjust=True,progress=False,threads=False)
px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[ALL].resample('ME').last().dropna(how='all')
ret=px.pct_change(); score=px.shift(1)/px.shift(12)-1
rows=[]
for dt in ret.index:
    s=score.loc[dt,COUNTRIES].dropna(); rr=ret.loc[dt,COUNTRIES].dropna(); avail=s.index.intersection(rr.index)
    if len(avail)<TOP_K: continue
    top=s.loc[avail].nlargest(TOP_K).index
    rows.append((dt,float(rr.loc[top].mean()),float(rr.loc[avail].mean()),float(ret.loc[dt,'SPY']) if pd.notna(ret.loc[dt,'SPY']) else np.nan,tuple(top)))
z=pd.DataFrame(rows,columns=['date','gross','matched','spy','top']).set_index('date')
prev=set(); net=[]; turns=[]
for _,row in z.iterrows():
    cur=set(row.top); turn=1.0 if not prev else 1.0-len(prev&cur)/TOP_K
    net.append(row.gross-turn*COST_BPS/10000); turns.append(turn); prev=cur
z['strategy']=net; z['turnover']=turns

def stats(s):
    s=s.dropna(); w=(1+s).cumprod(); yrs=len(s)/12; sd=s.std()
    return {'months':int(len(s)),'cagr':float(w.iloc[-1]**(1/yrs)-1),'sharpe':float(s.mean()/sd*math.sqrt(12)) if sd>0 else 0.0,'max_drawdown':float((w/w.cummax()-1).min())}
res={}
for name,start in {'2005_plus':'2005-01-01','2010_plus':'2010-01-01','2015_plus':'2015-01-01','2020_plus':'2020-01-01'}.items():
    q=z.loc[start:].dropna(subset=['strategy','matched','spy']); a,b,c=stats(q.strategy),stats(q.matched),stats(q.spy)
    res[name]={'strategy':a,'equal_country_matched':b,'spy_context':c,'matched_excess_cagr':a['cagr']-b['cagr'],'spy_opportunity_gap_cagr':a['cagr']-c['cagr'],'mean_monthly_turnover':float(q.turnover.mean())}
q=z.loc['2005-01-01':].dropna(subset=['strategy','matched']); folds=[stats(f.strategy)['cagr']-stats(f.matched)['cagr'] for f in np.array_split(q,5)]
passed=all(res[k]['matched_excess_cagr']>0 for k in res) and sum(x>0 for x in folds)>=3
decision='P336_COUNTRY_CROSSSECTIONAL_MOMENTUM_SUPPORTED' if passed else 'P336_COUNTRY_CROSSSECTIONAL_MOMENTUM_NOT_SUPPORTED'
out={'schema':'research.p336_country_crosssectional_momentum_r1','parent':'P336','claim':'Geographic transport of the fixed cross-sectional ranking architecture: monthly select the top 3 of a predeclared long-history country ETF universe by causal lagged 12-1 momentum, equal-weight them, charge 25bp turnover friction, and compare with the contemporaneous equal-country matched universe plus SPY opportunity context over fixed windows and five chronology folds. No top-k, lookback, country-set, rebalance, cost, or date search.','country_universe':COUNTRIES,'top_k':TOP_K,'cost_bps':COST_BPS,'results':res,'chronology_fold_matched_excess_cagr':folds,'positive_folds':sum(x>0 for x in folds),'decision_rule':'Support geographic transport only if after-cost matched excess CAGR is positive in every fixed window and >=3/5 chronology folds. Failure narrows cross-sectional momentum transport without invalidating the supported US-sector evidence.','decision':decision,'limitations':['country ETFs combine country, currency and market-structure exposures','equal-country matched control is investable opportunity-set control but not cap-weighted global benchmark','single adjusted-price provider','no portfolio ranking/allocation/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p336_country_crosssectional_momentum_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
