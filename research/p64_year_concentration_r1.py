from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import p82_component_contribution_r2 as p82

START=pd.Timestamp('2015-01-01')


def cagr(r):
    r=pd.Series(r,dtype=float).dropna()
    return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')


def main():
    f=p82.build()
    current_month_start=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp()
    q=f.loc[(f.index>=START)&(f.index<current_month_start),['p64','p64_matched','qqq']].dropna().copy()
    q['excess_monthly']=q.p64-q.p64_matched; q['year']=q.index.year
    years=[]
    for y,z in q.groupby('year'):
        years.append({'year':int(y),'months':int(len(z)),'candidate_cagr':cagr(z.p64),'matched_cagr':cagr(z.p64_matched),'excess_cagr':cagr(z.p64)-cagr(z.p64_matched),'excess_vs_qqq':cagr(z.p64)-cagr(z.qqq),'sum_monthly_excess':float(z.excess_monthly.sum())})
    ranked=sorted(years,key=lambda x:x['sum_monthly_excess'],reverse=True)
    pos=sum(max(0.0,x['sum_monthly_excess']) for x in years)
    top3_share=sum(max(0.0,x['sum_monthly_excess']) for x in ranked[:3])/pos if pos else None
    removals={}
    for n in (1,2,3):
        removed=sorted(x['year'] for x in ranked[:n]); z=q.loc[~q.year.isin(removed)]
        removals[str(n)]={'removed_years':removed,'months':int(len(z)),'excess_cagr':cagr(z.p64)-cagr(z.p64_matched),'excess_cagr_vs_qqq':cagr(z.p64)-cagr(z.qqq)}
    positive_year_fraction=sum(x['excess_cagr']>0 for x in years)/len(years)
    concentrated=(top3_share is not None and top3_share>=0.60) or removals['2']['excess_cagr']<=0 or positive_year_fraction<0.60
    out={'schema':'research.p64_year_concentration_r1','parent':'P64','hypothesis':'The unchanged P64 component used inside P82 has post-2015 after-cost matched-control excess distributed across completed calendar years rather than being carried by a few exceptional years.','scientific_contract':{'component':'unchanged P64 as consumed by P82 component contribution R2','component_cost_bps':50,'start':'2015-01-01','current_incomplete_month_excluded':True,'comparators':['P64 matched control','QQQ'],'no_parameter_or_weight_tuning':True},'full':{'start':str(q.index.min().date()),'end':str(q.index.max().date()),'months':int(len(q)),'excess_cagr':cagr(q.p64)-cagr(q.p64_matched),'excess_cagr_vs_qqq':cagr(q.p64)-cagr(q.qqq),'positive_calendar_year_fraction':positive_year_fraction,'top3_positive_excess_share':top3_share},'years':years,'remove_top_contribution_years':removals,'decision':'P64_EDGE_CALENDAR_CONCENTRATED' if concentrated else 'P64_EDGE_CALENDAR_BROAD'}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p64_year_concentration_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
