from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base

SECTORS=("XLK","XLF","XLV","XLE","XLI","XLY","XLP","XLU","XLB")
ALL=SECTORS+("SPY","QQQ")
MOM=126; TREND=200; MIN_BREADTH=6; TOP=3; COSTS=(25,50)
WINDOWS={'full':None,'2015_forward':'2015-01-01','2020_forward':'2020-01-01'}

def cagr(r):
    r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')
def mdd(r):
    r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); return float((e/e.cummax()-1).min()) if len(e) else float('nan')
def fold_count(a,b):
    vals=[]
    for i,ids in enumerate(np.array_split(np.arange(len(a)),5),1):
        x=a.iloc[ids]; y=b.iloc[ids]; vals.append({'fold':i,'excess_cagr':cagr(x)-cagr(y)})
    return sum(v['excess_cagr']>0 for v in vals),vals

def build():
    close=base.load(ALL).sort_index(); last=pd.Timestamp(close.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cutoff=last.to_period('M').start_time-pd.Timedelta(days=1)
    m=close.resample('ME').last(); m=m.loc[m.index<=cutoff]
    trend=(close[list(SECTORS)]/close[list(SECTORS)].rolling(TREND,min_periods=160).mean()).resample('ME').last().reindex(m.index); mom=m[list(SECTORS)].pct_change(6)
    rec=[]; pg={}; pr={}
    for i,dt in enumerate(m.index[:-1]):
        if i<7: continue
        raw=mom.loc[dt]
        if raw.isna().any() or trend.loc[dt].isna().any(): continue
        ranked=list(raw.where(raw>0,-np.inf).sort_values(ascending=False).head(TOP).index)
        breadth=int((trend.loc[dt]>1).sum()); gated=ranked if breadth>=MIN_BREADTH else []
        nxt=m.index[i+1]; ret=m.loc[nxt]/m.loc[dt]-1
        wg={s:(1/len(gated) if gated and s in gated else 0.) for s in SECTORS}; wr={s:(1/TOP if s in ranked else 0.) for s in SECTORS}
        tg=.5*(sum(abs(wg[s]-pg.get(s,0.)) for s in SECTORS)+abs((1-sum(wg.values()))-(1-sum(pg.values())))); tr=.5*(sum(abs(wr[s]-pr.get(s,0.)) for s in SECTORS)+abs((1-sum(wr.values()))-(1-sum(pr.values()))))
        rec.append({'date':nxt,'gated_gross':sum(wg[s]*float(ret[s]) for s in SECTORS),'raw_gross':sum(wr[s]*float(ret[s]) for s in SECTORS),'gated_turn':tg,'raw_turn':tr,'equal_sector':float(ret[list(SECTORS)].mean()),'spy':float(ret.SPY),'qqq':float(ret.QQQ),'active':bool(gated),'breadth':breadth}); pg=wg; pr=wr
    return pd.DataFrame(rec).set_index('date'),close,cutoff

def evaluate(q,bp):
    g=q.gated_gross-q.gated_turn*bp/10000; r=q.raw_gross-q.raw_turn*bp/10000
    fr,frd=fold_count(g,r); fe,fed=fold_count(g,q.equal_sector)
    return {'months':len(q),'active_fraction':float(q.active.mean()),'candidate_cagr':cagr(g),'raw_cagr':cagr(r),'equal_sector_cagr':cagr(q.equal_sector),'spy_cagr':cagr(q.spy),'qqq_cagr':cagr(q.qqq),'candidate_mdd':mdd(g),'raw_mdd':mdd(r),'equal_sector_mdd':mdd(q.equal_sector),'excess_vs_raw':cagr(g)-cagr(r),'excess_vs_equal_sector':cagr(g)-cagr(q.equal_sector),'excess_vs_spy':cagr(g)-cagr(q.spy),'excess_vs_qqq':cagr(g)-cagr(q.qqq),'drawdown_improvement_vs_raw':mdd(g)-mdd(r),'positive_folds_vs_raw':fr,'positive_folds_vs_equal_sector':fe,'folds_vs_raw':frd,'folds_vs_equal_sector':fed}

def main():
    f,close,cutoff=build(); out={'schema':'research.p16_temporal_adjudicator_r1','parent':'P16','hypothesis':'The frozen 6-of-9 sector breadth gate on positive 126-session top-3 momentum improves later-period after-cost scarce-capital economics versus always-on raw momentum, not only aggregate drawdown.','scientific_contract':{'universe':list(SECTORS),'momentum_lookback_sessions':MOM,'trend_window_sessions':TREND,'min_breadth':MIN_BREADTH,'top_k':TOP,'costs_bps':list(COSTS),'matched_claim_control':'always-on raw positive momentum top-3','other_controls':['equal-sector','SPY','QQQ'],'windows':WINDOWS,'chronological_folds':5,'complete_months_only':True,'no_parameter_tuning':True},'tests':{},'source':{'provider':'Yahoo Finance via yfinance; research-only','panel_sha256':base.source_hash(close),'last_complete_month_end':str(cutoff.date())}}
    for name,start in WINDOWS.items():
        q=f if start is None else f.loc[pd.Timestamp(start):]
        out['tests'][name]={str(bp):evaluate(q,bp) for bp in COSTS}
    t=out['tests']['2020_forward']['50']; out['decision']='P16_TEMPORAL_GATE_SUPPORTED' if t['excess_vs_raw']>0 and t['positive_folds_vs_raw']>=3 and t['drawdown_improvement_vs_raw']>0 else 'P16_TEMPORAL_GATE_WEAK_OR_FAILED'
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p16_temporal_adjudicator_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
