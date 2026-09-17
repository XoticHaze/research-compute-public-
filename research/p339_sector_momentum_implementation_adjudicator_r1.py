from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
SECTORS=['XLB','XLE','XLF','XLI','XLK','XLP','XLU','XLV','XLY']; ALL=SECTORS+['SPY']; START='2003-01-01'; END='2026-09-10'; COST_BPS=25; TOP_K=3
raw=yf.download(ALL,start=START,end=END,auto_adjust=True,progress=False,threads=False)
px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[ALL].dropna().resample('ME').last(); ret=px.pct_change(); score=px.shift(1)/px.shift(12)-1
rows=[]
for dt in ret.index:
 s=score.loc[dt,SECTORS].dropna(); rr=ret.loc[dt,SECTORS].dropna(); avail=s.index.intersection(rr.index)
 if len(avail)<TOP_K: continue
 top=s.loc[avail].nlargest(TOP_K).index; rows.append((dt,float(rr.loc[top].mean()),float(rr.loc[avail].mean()),float(ret.loc[dt,'SPY']),tuple(top)))
z=pd.DataFrame(rows,columns=['date','gross','matched','spy','top']).set_index('date'); prev=set(); net=[]; turns=[]
for _,r in z.iterrows():
 cur=set(r.top); turn=1.0 if not prev else 1.0-len(prev&cur)/TOP_K; net.append(r.gross-turn*COST_BPS/10000); turns.append(turn); prev=cur
z['strategy']=net; z['turnover']=turns
def stats(s):
 s=s.dropna(); w=(1+s).cumprod(); yrs=len(s)/12; sd=s.std(); return {'months':int(len(s)),'cagr':float(w.iloc[-1]**(1/yrs)-1),'sharpe':float(s.mean()/sd*math.sqrt(12)) if sd>0 else 0.0,'max_drawdown':float((w/w.cummax()-1).min())}
res={}
for name,start in {'2005_plus':'2005-01-01','2010_plus':'2010-01-01','2015_plus':'2015-01-01','2020_plus':'2020-01-01'}.items():
 q=z.loc[start:].dropna(); a,b,c=stats(q.strategy),stats(q.matched),stats(q.spy); res[name]={'strategy':a,'matched':b,'spy':c,'matched_excess_cagr':a['cagr']-b['cagr'],'spy_gap_cagr':a['cagr']-c['cagr'],'mean_turnover':float(q.turnover.mean())}
q=z.loc['2005-01-01':].dropna(); folds=[stats(f.strategy)['cagr']-stats(f.matched)['cagr'] for f in np.array_split(q,5)]; passed=all(res[k]['matched_excess_cagr']>0 for k in res) and sum(x>0 for x in folds)>=3
decision='P339_CORRECTED_NINE_SECTOR_MOMENTUM_SUPPORTED' if passed else 'P339_CORRECTED_NINE_SECTOR_MOMENTUM_NOT_SUPPORTED'
out={'schema':'research.p339_sector_momentum_implementation_adjudicator_r1','parent':'P339','claim':'Implementation adjudicator for P310 versus P330: rerun the original fixed nine-sector P310 universe with the P330 intended causal implementation, where the already-lagged 12-1 score formed at month t directly selects sleeves for month-t return, and charge one-way turnover as 1 minus selected-set overlap. No universe, signal, top-k, window, or cost tuning.','universe':SECTORS,'cost_bps':COST_BPS,'results':res,'chronology_fold_matched_excess_cagr':folds,'positive_folds':sum(x>0 for x in folds),'decision_rule':'If corrected nine-sector implementation clears positive matched excess in all windows and >=3/5 folds, classify the P310/P330 contradiction as implementation/causality-cost accounting rather than dependence on XLC/XLRE expansion. Failure preserves a real universe/representation contradiction requiring further narrowing.','decision':decision,'implementation_difference_from_p310':['P310 formed an already prior-information momentum score then shifted weights by one additional month before applying returns','P310 charged sum(abs(delta weights)), while this adjudicator uses one-way turnover 0.5*L1 = 1-overlap/top_k for equal-weight selected sets'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p339_sector_momentum_implementation_adjudicator_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
