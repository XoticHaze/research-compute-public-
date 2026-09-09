from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base

SYMS=tuple(base.UNIVERSES['crossasset'])

def frame():
    close=base.load(SYMS); m=close.resample('ME').last(); mom=m.pct_change(6); trend=(close/close.rolling(200,min_periods=160).mean()-1).resample('ME').last(); prev={s:0.0 for s in SYMS}; rec=[]
    for dt in m.index:
        b=pd.DataFrame({'mom6':mom.loc[dt,list(SYMS)],'trend200':trend.loc[dt,list(SYMS)]},index=list(SYMS))
        if b.isna().any().any(): continue
        sc=b.rank(axis=0,pct=True,method='average').mean(axis=1); loc=m.index.get_loc(dt)
        if not isinstance(loc,(int,np.integer)) or loc+1>=len(m): continue
        nxt=m.index[loc+1]; r=m.loc[nxt,list(SYMS)]/m.loc[dt,list(SYMS)]-1
        if r.isna().any(): continue
        chosen=sc.sort_values(ascending=False).head(2).index.tolist(); w={s:(0.5 if s in chosen else 0.0) for s in SYMS}; to=0.5*sum(abs(w[s]-prev[s]) for s in SYMS)
        rec.append({'date':nxt,'gross':sum(w[s]*float(r[s]) for s in SYMS),'ew':float(r.mean()),'spy':float(r['SPY']),'qqq':float(r['QQQ']),'turnover':to}); prev=w
    return pd.DataFrame(rec).set_index('date'),close

def evaluate(fr,bps):
    c=fr.gross-fr.turnover*bps/10000; cm=base.metrics(c); em=base.metrics(fr.ew); sm=base.metrics(fr.spy); qm=base.metrics(fr.qqq); pos,folds=base.fold_count(c,fr.ew)
    return {'candidate':cm,'matched_ew':em,'spy':sm,'qqq':qm,'excess_cagr_vs_matched':cm['cagr']-em['cagr'],'excess_cagr_vs_spy':cm['cagr']-sm['cagr'],'excess_cagr_vs_qqq':cm['cagr']-qm['cagr'],'positive_matched_folds':pos,'folds':folds,'mean_annual_turnover':float(fr.turnover.mean()*12)}
def main():
    fr,close=frame(); tests={}
    for bp in (25,50): tests[str(bp)]=evaluate(fr,bp)
    bm=base.metrics(fr.ew)['cagr']; grid=[]
    for bp in range(0,201): grid.append(base.metrics(fr.gross-fr.turnover*bp/10000)['cagr']-bm)
    non=[i for i,x in enumerate(grid) if x<=0]
    tests['cost_breakeven']={'first_nonpositive_bps':non[0] if non else None,'excess_at_25':grid[25],'excess_at_50':grid[50],'excess_at_100':grid[100]}
    out={'schema':'research.p62_crossasset_parsimonious_capital_risk_r1','parents':['P46','P57'],'hypothesis':'P57 matched alpha survives an explicit capital-efficiency and broad-market opportunity-cost test, rather than merely beating a weak same-universe equal-weight control.','scientific_contract':{'universe':list(SYMS),'factors':['mom6','trend200'],'top_k':2,'cadence':'monthly','costs_bps':[25,50],'comparators':['same-universe equal weight','SPY','QQQ'],'risk_metrics':['volatility','max drawdown','Sharpe rf0','Calmar'],'cost_breakeven_grid_bps':[0,200],'no_parameter_tuning':True},'source':{'provider':'Yahoo Finance via yfinance','normalized_price_panel_sha256':base.source_hash(close)},'tests':tests}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p62_crossasset_parsimonious_capital_risk_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    print(json.dumps({'25':{'cagr':tests['25']['candidate']['cagr'],'ex_matched':tests['25']['excess_cagr_vs_matched'],'ex_spy':tests['25']['excess_cagr_vs_spy'],'ex_qqq':tests['25']['excess_cagr_vs_qqq'],'mdd':tests['25']['candidate']['max_drawdown_monthly'],'sharpe':tests['25']['candidate']['sharpe_rf0']},'50':{'ex_matched':tests['50']['excess_cagr_vs_matched'],'ex_spy':tests['50']['excess_cagr_vs_spy'],'ex_qqq':tests['50']['excess_cagr_vs_qqq']},'breakeven':tests['cost_breakeven']},sort_keys=True))
if __name__=='__main__': main()
