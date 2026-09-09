#!/usr/bin/env python3
import json
from pathlib import Path
import pandas as pd
import p36_soxx_delay_temporal_holdout_r1 as p

DELAY=1
START=pd.Timestamp('2015-01-01')

def cagr(r):
    r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')
def main():
    px={}; src={}
    for s in (p.ASSET,'QQQ'): px[s],src[s]=p.base.yahoo(s)
    current_month_start=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp()
    f=p.build(px,DELAY).loc[lambda x:(x.index>=START)&(x.index<current_month_start)].copy()
    f['excess_monthly']=f.candidate-f.matched; f['year']=f.index.year
    years=[]
    for y,q in f.groupby('year'):
        years.append({'year':int(y),'months':int(len(q)),'candidate_cagr':cagr(q.candidate),'matched_cagr':cagr(q.matched),'excess_cagr':cagr(q.candidate)-cagr(q.matched),'excess_vs_qqq':cagr(q.candidate)-cagr(q.qqq),'sum_monthly_excess':float(q.excess_monthly.sum())})
    ranked=sorted(years,key=lambda x:x['sum_monthly_excess'],reverse=True); pos=sum(max(0.0,x['sum_monthly_excess']) for x in years); top3=sum(max(0.0,x['sum_monthly_excess']) for x in ranked[:3])/pos if pos else None
    rem={}
    for n in (1,2,3):
        ys=sorted(x['year'] for x in ranked[:n]); q=f.loc[~f.year.isin(ys)]; rem[str(n)]={'removed_years':ys,'months':len(q),'excess_cagr':cagr(q.candidate)-cagr(q.matched),'excess_cagr_vs_qqq':cagr(q.candidate)-cagr(q.qqq)}
    py=sum(x['excess_cagr']>0 for x in years)/len(years); concentrated=(top3 is not None and top3>=.60) or rem['2']['excess_cagr']<=0 or py<.60
    out={'schema':'research.p36_soxx_year_concentration_r2','parent':'P36','hypothesis':'The unchanged SOXX-vs-QQQ six-month relative-momentum selector with one-trading-day implementation delay and 50-bps switching cost has post-2015 matched-control excess distributed across completed calendar months rather than carried by a few exceptional years.','scientific_contract':{'representation':'SOXX_vs_QQQ','lookback_months':6,'delay_trading_days':DELAY,'cost_bps':50,'start':'2015-01-01','matched_control':'same shifted intervals static 50/50 SOXX+QQQ','opportunity_control':'QQQ','current_incomplete_month_excluded':True,'no_parameter_tuning':True},'full':{'months':len(f),'start':str(f.index.min().date()),'end':str(f.index.max().date()),'excess_cagr':cagr(f.candidate)-cagr(f.matched),'excess_cagr_vs_qqq':cagr(f.candidate)-cagr(f.qqq),'positive_calendar_year_fraction':py,'top3_positive_excess_share':top3},'years':years,'remove_top_contribution_years':rem,'sources':src,'decision':'P36_SOXX_EDGE_CALENDAR_CONCENTRATED' if concentrated else 'P36_SOXX_EDGE_CALENDAR_BROAD'}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p36_soxx_year_concentration_r2.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
