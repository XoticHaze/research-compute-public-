from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf

SECTORS=['XLB','XLC','XLE','XLF','XLI','XLK','XLP','XLRE','XLU','XLV','XLY']; ALL=SECTORS+['SPY']
START='2001-01-01'; END='2026-09-10'; COST_BPS=25; TOP_K=3
raw=yf.download(ALL,start=START,end=END,auto_adjust=True,progress=False,threads=False)
px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[ALL].resample('ME').last().dropna(how='all')
ret=px.pct_change(); score=px.shift(1)/px.shift(12)-1

def build(universe):
    rows=[]
    for dt in ret.index:
        s=score.loc[dt,universe].dropna(); rr=ret.loc[dt,universe].dropna(); avail=s.index.intersection(rr.index)
        if len(avail)<TOP_K: continue
        top=s.loc[avail].nlargest(TOP_K).index
        rows.append((dt,float(rr.loc[top].mean()),float(rr.loc[avail].mean()),tuple(top)))
    z=pd.DataFrame(rows,columns=['date','gross','matched','top']).set_index('date')
    prev=set(); vals=[]; turns=[]
    for _,row in z.iterrows():
        cur=set(row.top); turn=1.0 if not prev else 1.0-len(prev&cur)/TOP_K
        vals.append(row.gross-turn*COST_BPS/10000); turns.append(turn); prev=cur
    z['strategy']=vals; z['turnover']=turns
    return z

def stats(s):
    s=s.dropna(); w=(1+s).cumprod(); yrs=len(s)/12; sd=s.std()
    return {'months':int(len(s)),'cagr':float(w.iloc[-1]**(1/yrs)-1),'sharpe':float(s.mean()/sd*math.sqrt(12)) if sd>0 else 0.0,'max_drawdown':float((w/w.cummax()-1).min())}

def eval_one(omit):
    u=[x for x in SECTORS if x!=omit]; z=build(u); wins={}
    for name,start in {'2010_plus':'2010-01-01','2015_plus':'2015-01-01','2020_plus':'2020-01-01'}.items():
        q=z.loc[start:]; a,b=stats(q.strategy),stats(q.matched); wins[name]={'strategy':a,'matched':b,'matched_excess_cagr':a['cagr']-b['cagr'],'mean_turnover':float(q.turnover.mean())}
    q=z.loc['2010-01-01':]; folds=[stats(f.strategy)['cagr']-stats(f.matched)['cagr'] for f in np.array_split(q,5)]
    robust=all(wins[k]['matched_excess_cagr']>0 for k in wins) and sum(x>0 for x in folds)>=3
    return {'windows':wins,'folds':folds,'positive_folds':sum(x>0 for x in folds),'robust':robust}
results={s:eval_one(s) for s in SECTORS}
robust_count=sum(v['robust'] for v in results.values()); tech_robust=results['XLK']['robust']
passed=robust_count>=9 and tech_robust
decision='P333_SECTOR_MOMENTUM_CONCENTRATION_ROBUST' if passed else 'P333_SECTOR_MOMENTUM_CONCENTRATION_WEAKNESS'
out={'schema':'research.p333_sector_momentum_concentration_jackknife_r1','parent':'P333','claim':'Orthogonal concentration/attribution falsifier for the supported P330 sector-momentum survivor. Re-run the unchanged top-3 causal 12-1 monthly rule after removing each sector ETF one at a time, preserving 25bp turnover friction and contemporaneous equal-sector matched control. No top-k, signal, weight, rebalance, cost, or replacement search.','sector_universe':SECTORS,'results':results,'robust_omission_count':robust_count,'technology_omission_robust':tech_robust,'decision_rule':'Call concentration robust only if >=9/11 leave-one-sector-out universes preserve positive matched excess in 2010+/2015+/2020+ and >=3/5 positive chronology folds, and the XLK-omitted universe independently meets that rule. Failure narrows robustness but does not erase P330/P332 passing evidence.','decision':decision,'limitations':['jackknife tests sector dependence, not constituent concentration within sectors','same adjusted-price provider as P330','no portfolio ranking/allocation/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p333_sector_momentum_concentration_jackknife_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
