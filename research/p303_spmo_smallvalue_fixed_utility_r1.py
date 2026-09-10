from __future__ import annotations
import json, math
from pathlib import Path
import pandas as pd, yfinance as yf
SYMS=['SPMO','SPY','VBR','VB']; START='2015-01-01'; END='2026-09-10'; COST_BPS=25
raw=yf.download(SYMS,start=START,end=END,auto_adjust=True,progress=False,threads=False); px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[SYMS].dropna(); r=px.pct_change().dropna(); monthly=px.resample('ME').last().pct_change().dropna(); combo=.5*r.SPMO+.5*r.VBR; matched=.5*r.SPY+.5*r.VB
# fixed monthly rebalance endpoint cost: two sleeves, charge cost on monthly turnover implied by resetting to 50/50
mret=pd.DataFrame({'SPMO':monthly.SPMO,'VBR':monthly.VBR}); gross=.5*mret.SPMO+.5*mret.VBR; drift_spmo=.5*(1+mret.SPMO)/(1+gross); turnover=2*(drift_spmo-.5).abs(); net_monthly=gross-turnover*(COST_BPS/10000); bench_monthly=.5*monthly.SPY+.5*monthly.VB

def stats(s):
 s=s.dropna(); wealth=(1+s).cumprod(); yrs=len(s)/12; cagr=float(wealth.iloc[-1]**(1/yrs)-1); vol=float(s.std()*math.sqrt(12)); sharpe=float(s.mean()/s.std()*math.sqrt(12)) if s.std()>0 else 0.; dd=float((wealth/wealth.cummax()-1).min()); return {'months':int(len(s)),'cagr':cagr,'vol':vol,'sharpe':sharpe,'max_drawdown':dd}
def window(a):
 n=net_monthly.loc[net_monthly.index>=pd.Timestamp(a)]; b=bench_monthly.loc[n.index]; sp=monthly.SPY.loc[n.index]; q=monthly.get('QQQ') if False else None; return {'combo':stats(n),'matched':stats(b),'sp500':stats(sp),'matched_excess_cagr':stats(n)['cagr']-stats(b)['cagr'],'sp500_excess_cagr':stats(n)['cagr']-stats(sp)['cagr']}
res={k:window(v) for k,v in {'2017_plus':'2017-01-01','2020_plus':'2020-01-01','2022_plus':'2022-01-01'}.items()}
# fixed 5 chronological folds from 2017+ monthly observations
z=pd.DataFrame({'n':net_monthly,'b':bench_monthly}).loc['2017-01-01':].dropna(); folds=[]
for part in __import__('numpy').array_split(z,5): folds.append(stats(part.n)['cagr']-stats(part.b)['cagr'])
passes=(res['2017_plus']['matched_excess_cagr']>0 and res['2020_plus']['matched_excess_cagr']>0 and res['2022_plus']['matched_excess_cagr']>0 and sum(x>0 for x in folds)>=3); decision='P303_FIXED_COMBINATION_UTILITY_SUPPORTED' if passes else 'P303_FIXED_COMBINATION_UTILITY_NOT_SUPPORTED'
out={'schema':'research.p303_spmo_smallvalue_fixed_utility_r1','parent':'P303','claim':'After P301 established orthogonality, test a single predeclared 50/50 SPMO+VBR combination against the exact 50/50 SPY+VB matched baseline after 25 bp endpoint turnover costs. No weight search.','cost_bps':COST_BPS,'weights':{'SPMO':0.5,'VBR':0.5},'matched_weights':{'SPY':0.5,'VB':0.5},'results':res,'chronology_fold_matched_excess_cagr':folds,'positive_folds':sum(x>0 for x in folds),'decision_rule':'Support only if after-cost matched excess CAGR is positive in 2017+, 2020+, and 2022+, with at least 3/5 positive chronological folds.','decision':decision,'limitations':['single fixed equal-weight scientific utility test','same adjusted-price provider','VBR/VB transport remains mixed/regime-conditional','no allocation/ranking/product/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p303_spmo_smallvalue_fixed_utility_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
