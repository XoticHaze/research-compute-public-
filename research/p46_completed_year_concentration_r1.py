from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p46_temporal_factor_discriminators_r1 as p46

BP=50
START=2015
END=2025


def cagr(r):
    r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')


def main():
    close=base.load(p46.SYMBOLS).sort_index(); f=p46.returns(close,p46.FACTORS)
    monthly=close.resample('ME').last(); qqq=monthly['QQQ'].pct_change().reindex(f.index)
    x=f.loc[(f.index.year>=START)&(f.index.year<=END)].copy(); x['candidate']=x.gross-x.turnover*BP/10000; x['qqq']=qqq.reindex(x.index)
    years=[]
    for y,g in x.groupby(x.index.year):
        if len(g)!=12: continue
        cr=float((1+g.candidate).prod()-1); er=float((1+g.ew).prod()-1); qr=float((1+g.qqq).prod()-1)
        years.append({'year':int(y),'candidate_return':cr,'matched_ew_return':er,'qqq_return':qr,'excess_vs_matched':cr-er,'excess_vs_qqq':cr-qr})
    complete=[z['year'] for z in years]; q=x[x.index.year.isin(complete)]
    ranked=sorted(years,key=lambda z:z['excess_vs_matched'],reverse=True); best=[z['year'] for z in ranked[:2]]
    def aggregate(frame):
        return {'months':len(frame),'candidate_cagr':cagr(frame.candidate),'matched_ew_cagr':cagr(frame.ew),'qqq_cagr':cagr(frame.qqq),'excess_cagr_vs_matched':cagr(frame.candidate)-cagr(frame.ew),'excess_cagr_vs_qqq':cagr(frame.candidate)-cagr(frame.qqq)}
    pos=[z for z in years if z['excess_vs_matched']>0]; pos_sum=sum(z['excess_vs_matched'] for z in pos); top3=sum(z['excess_vs_matched'] for z in ranked[:3] if z['excess_vs_matched']>0)
    out={'schema':'research.p46_completed_year_concentration_r1','parent':'P46','hypothesis':'P46 original-representation after-cost excess should persist across completed calendar years rather than depend on a few standout years.','scientific_contract':{'mechanism':'original P46 four-factor top-2 monthly','cost_bps':BP,'completed_years':[START,END],'matched_control':'same-universe equal weight','broad_market_opportunity_cost':'QQQ','tests':['positive completed-year fraction','top-3 positive-excess concentration','remove strongest complete year','remove two strongest complete years'],'no_parameter_tuning':True},'years':years,'aggregate':aggregate(q),'positive_year_fraction':sum(z['excess_vs_matched']>0 for z in years)/len(years),'top3_share_of_positive_excess':top3/pos_sum if pos_sum>0 else None,'best_excess_years':best,'remove_best_year':aggregate(q[q.index.year!=best[0]]),'remove_top2_years':aggregate(q[~q.index.year.isin(best)]),'source':{'provider':'Yahoo Finance via yfinance; research-only','panel_sha256':base.source_hash(close)}}
    rb=out['remove_best_year']; out['decision']='P46_COMPLETED_YEAR_PERSISTENCE_SUPPORTED' if out['positive_year_fraction']>=0.6 and rb['excess_cagr_vs_matched']>0 and rb['excess_cagr_vs_qqq']>0 else 'P46_COMPLETED_YEAR_CONCENTRATION_WEAKNESS'
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_completed_year_concentration_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
