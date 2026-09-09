from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base

SECTORS=("XLK","XLF","XLV","XLE","XLI","XLY","XLP","XLU","XLB")
ALL=SECTORS+("SPY","QQQ")
LB=126; VW=63; TOP=3; COSTS=(25,50)
WINDOWS={'full':None,'2015_forward':'2015-01-01','2020_forward':'2020-01-01'}

def cagr(r):
    r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')
def mdd(r):
    r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); return float((e/e.cummax()-1).min()) if len(e) else float('nan')
def folds(a,b):
    out=[]
    for i,ids in enumerate(np.array_split(np.arange(len(a)),5),1):
        x=a.iloc[ids]; y=b.iloc[ids]; out.append({'fold':i,'excess_cagr':cagr(x)-cagr(y)})
    return out

def build():
    close=base.load(ALL).sort_index(); m=close.resample('ME').last(); dr=close.pct_change()
    mom=m[list(SECTORS)].pct_change(6)
    vol=(dr[list(SECTORS)].rolling(VW,min_periods=VW-5).std(ddof=1)*math.sqrt(252)).resample('ME').last()
    rec=[]; prev_ra={}; prev_raw={}
    for i,dt in enumerate(m.index[:-1]):
        if i<6: continue
        raw=mom.loc[dt]; risk=(raw/vol.loc[dt]).where(raw>0,-np.inf)
        if raw.isna().any() or vol.loc[dt].isna().any(): continue
        ra=list(risk.sort_values(ascending=False).head(TOP).index); rr=list(raw.where(raw>0,-np.inf).sort_values(ascending=False).head(TOP).index)
        nxt=m.index[i+1]; ret=m.loc[nxt]/m.loc[dt]-1
        wr={s:(1/TOP if s in ra else 0.) for s in SECTORS}; ww={s:(1/TOP if s in rr else 0.) for s in SECTORS}
        tra=.5*sum(abs(wr[s]-prev_ra.get(s,0.)) for s in SECTORS); trw=.5*sum(abs(ww[s]-prev_raw.get(s,0.)) for s in SECTORS)
        row={'date':nxt,'ra_gross':sum(wr[s]*float(ret[s]) for s in SECTORS),'raw_gross':sum(ww[s]*float(ret[s]) for s in SECTORS),'ra_turn':tra,'raw_turn':trw,'equal_sector':float(ret[list(SECTORS)].mean()),'spy':float(ret.SPY),'qqq':float(ret.QQQ)}
        rec.append(row); prev_ra=wr; prev_raw=ww
    return pd.DataFrame(rec).set_index('date'),close

def eval_window(q,bp):
    ra=q.ra_gross-q.ra_turn*bp/10000; raw=q.raw_gross-q.raw_turn*bp/10000
    fr=folds(ra,raw); fe=folds(ra,q.equal_sector)
    return {'months':len(q),'ra_cagr':cagr(ra),'raw_cagr':cagr(raw),'equal_sector_cagr':cagr(q.equal_sector),'spy_cagr':cagr(q.spy),'qqq_cagr':cagr(q.qqq),'ra_mdd':mdd(ra),'raw_mdd':mdd(raw),'equal_sector_mdd':mdd(q.equal_sector),'excess_vs_raw':cagr(ra)-cagr(raw),'excess_vs_equal_sector':cagr(ra)-cagr(q.equal_sector),'excess_vs_spy':cagr(ra)-cagr(q.spy),'excess_vs_qqq':cagr(ra)-cagr(q.qqq),'positive_folds_vs_raw':sum(x['excess_cagr']>0 for x in fr),'positive_folds_vs_equal_sector':sum(x['excess_cagr']>0 for x in fe),'folds_vs_raw':fr,'folds_vs_equal_sector':fe}

def main():
    f,close=build(); out={'schema':'research.p15_temporal_adjudicator_r1','parent':'P15','hypothesis':'Frozen 126-session momentum divided by prior 63-session realized volatility adds persistent after-cost value over raw sector momentum in later chronology, not merely in the long aggregate sample.','scientific_contract':{'universe':list(SECTORS),'lookback_sessions':LB,'vol_window_sessions':VW,'top_k':TOP,'costs_bps':list(COSTS),'matched_claim_control':'raw positive momentum top-3','other_controls':['equal-sector','SPY','QQQ'],'windows':WINDOWS,'chronological_folds':5,'no_parameter_tuning':True},'tests':{},'source':{'provider':'Yahoo Finance via yfinance; research-only','panel_sha256':base.source_hash(close)}}
    for name,start in WINDOWS.items():
        q=f if start is None else f.loc[pd.Timestamp(start):]
        out['tests'][name]={str(bp):eval_window(q,bp) for bp in COSTS}
    t=out['tests']['2020_forward']['50']; out['decision']='P15_TEMPORAL_EDGE_SUPPORTED' if t['excess_vs_raw']>0 and t['excess_vs_equal_sector']>0 and t['positive_folds_vs_raw']>=3 else 'P15_TEMPORAL_EDGE_WEAK_OR_FAILED'
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p15_temporal_adjudicator_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
