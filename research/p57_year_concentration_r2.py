from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import p57_crossasset_parsimonious_r1 as p57

BP=25


def cagr(r):
    r=pd.Series(r,dtype=float).dropna()
    return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')


def main():
    fr,close=p57.run(0)
    current_month_start=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp()
    fr=fr.loc[fr.index<current_month_start]
    z=pd.DataFrame({'candidate':fr.gross-fr.turnover*BP/10000.0,'matched':fr.ew}).dropna()
    mm=close[['SPY','QQQ']].resample('ME').last().pct_change().reindex(z.index)
    z['spy']=mm.SPY; z['qqq']=mm.QQQ; z['excess_monthly']=z.candidate-z.matched; z['year']=z.index.year
    years=[]
    for y,q in z.groupby('year'):
        years.append({'year':int(y),'months':int(len(q)),'candidate_cagr':cagr(q.candidate),'matched_cagr':cagr(q.matched),'excess_cagr':cagr(q.candidate)-cagr(q.matched),'excess_vs_qqq':cagr(q.candidate)-cagr(q.qqq),'sum_monthly_excess':float(q.excess_monthly.sum())})
    ranked=sorted(years,key=lambda x:x['sum_monthly_excess'],reverse=True)
    pos=sum(max(0.0,x['sum_monthly_excess']) for x in years)
    top3_share=sum(max(0.0,x['sum_monthly_excess']) for x in ranked[:3])/pos if pos else None
    removals={}
    for n in (1,2,3,5):
        removed=sorted(x['year'] for x in ranked[:n]); q=z.loc[~z.year.isin(removed)]
        removals[str(n)]={'removed_years':removed,'months':int(len(q)),'excess_cagr':cagr(q.candidate)-cagr(q.matched),'excess_cagr_vs_qqq':cagr(q.candidate)-cagr(q.qqq)}
    positive_year_fraction=sum(x['excess_cagr']>0 for x in years)/len(years)
    concentrated=(top3_share is not None and top3_share>=0.60) or removals['2']['excess_cagr']<=0 or positive_year_fraction<0.60
    out={'schema':'research.p57_year_concentration_r2','parent':'P57','hypothesis':'The frozen parsimonious cross-asset momentum+trend top-2 sleeve has 25-bps matched-control excess distributed across completed calendar months rather than carried by a few exceptional years.','scientific_contract':{'economics':'unchanged P57 momentum+trend cross-asset top-2 monthly','cost_bps':BP,'matched_control':'same-universe equal weight over identical completed months','opportunity_controls':['SPY','QQQ'],'tests':['calendar-year persistence','top-positive-year share','remove top 1/2/3/5 contribution years'],'current_incomplete_month_excluded':True,'no_parameter_tuning':True},'source':{'normalized_price_panel_sha256':p57.base.source_hash(close)},'full':{'start':str(z.index.min().date()),'end':str(z.index.max().date()),'months':int(len(z)),'excess_cagr':cagr(z.candidate)-cagr(z.matched),'excess_cagr_vs_spy':cagr(z.candidate)-cagr(z.spy),'excess_cagr_vs_qqq':cagr(z.candidate)-cagr(z.qqq),'positive_calendar_year_fraction':positive_year_fraction,'top3_positive_excess_share':top3_share},'years':years,'remove_top_contribution_years':removals,'decision':'P57_EDGE_CALENDAR_CONCENTRATED' if concentrated else 'P57_EDGE_CALENDAR_BROAD'}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p57_year_concentration_r2.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
