from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import p46_alt_etf_representation_r2 as alt

SYMBOLS=('SPY','QQQ','TLT','GLD','DBC')
BP=50


def cagr(r):
    r=pd.Series(r,dtype=float).dropna()
    return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')


def main():
    alt.SYMBOLS=SYMBOLS
    close=alt.base.load(SYMBOLS)
    current_month_start=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp()
    close=close.loc[close.index<current_month_start]
    f=alt.build(close)
    z=pd.DataFrame({'candidate':f.gross-f.turnover*BP/10000.0,'matched':f.matched}).dropna()
    z['excess_monthly']=z.candidate-z.matched; z['year']=z.index.year
    years=[]
    for y,q in z.groupby('year'):
        years.append({'year':int(y),'months':int(len(q)),'candidate_cagr':cagr(q.candidate),'matched_cagr':cagr(q.matched),'excess_cagr':cagr(q.candidate)-cagr(q.matched),'sum_monthly_excess':float(q.excess_monthly.sum())})
    ranked=sorted(years,key=lambda x:x['sum_monthly_excess'],reverse=True)
    pos=sum(max(0.0,x['sum_monthly_excess']) for x in years)
    removals={}
    for n in (1,2,3,5):
        removed=sorted(x['year'] for x in ranked[:n]); q=z.loc[~z.year.isin(removed)]
        removals[str(n)]={'removed_years':removed,'months':int(len(q)),'excess_cagr':cagr(q.candidate)-cagr(q.matched)}
    top3_share=sum(max(0.0,x['sum_monthly_excess']) for x in ranked[:3])/pos if pos else None
    positive_year_fraction=sum(x['excess_cagr']>0 for x in years)/len(years)
    concentrated=(top3_share is not None and top3_share>=0.60) or removals['2']['excess_cagr']<=0 or positive_year_fraction<0.60
    out={
      'schema':'research.p46_year_concentration_r1','parent':'P46',
      'hypothesis':'The frozen original P46 four-factor top-2 allocator retains after-cost matched-control excess across calendar years rather than deriving most of its edge from a few exceptional years.',
      'scientific_contract':{'symbols':list(SYMBOLS),'factors':['mom6','trend200','low_vol6','drawdown6'],'top_k':2,'cost_bps':BP,'matched_control':'same-universe equal weight over identical months','tests':['calendar-year persistence','top-positive-year share','remove top 1/2/3/5 contribution years'],'no_parameter_or_proxy_tuning':True},
      'full':{'start':str(z.index.min().date()),'end':str(z.index.max().date()),'months':int(len(z)),'excess_cagr':cagr(z.candidate)-cagr(z.matched),'positive_calendar_year_fraction':positive_year_fraction,'top3_positive_excess_share':top3_share},
      'years':years,'remove_top_contribution_years':removals,
      'decision':'P46_EDGE_CALENDAR_CONCENTRATED' if concentrated else 'P46_EDGE_CALENDAR_BROAD',
      'source':{'provider':'Yahoo Finance via yfinance','normalized_price_panel_sha256':alt.base.source_hash(close)}
    }
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_year_concentration_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))

if __name__=='__main__': main()
