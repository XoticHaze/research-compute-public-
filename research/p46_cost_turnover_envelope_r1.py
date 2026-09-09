from __future__ import annotations
import json,math,hashlib
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
U=('SPY','QQQ','TLT','GLD','DBC'); COSTS=(0,25,50,100,200,300,500,750,1000)

def cagr(r):
    r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')
def build():
    d=yf.download(list(U),start='2005-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna(how='all').astype(float)
    last=pd.Timestamp(d.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cut=last.to_period('M').start_time-pd.Timedelta(days=1); d=d.loc[d.index<=cut]
    m=d.resample('ME').last(); dr=d.pct_change(fill_method=None); vol=(d.pct_change(fill_method=None).rolling(126,min_periods=100).std(ddof=0)*math.sqrt(252)).resample('ME').last(); trend=(d/d.rolling(200,min_periods=160).mean()-1).resample('ME').last(); dd=(d/d.rolling(126,min_periods=100).max()-1).resample('ME').last(); mom=m.pct_change(6)
    prev={s:0. for s in U}; rows=[]
    for i,dt in enumerate(m.index[:-1]):
        b=pd.DataFrame({'mom6':mom.loc[dt,list(U)],'trend200':trend.loc[dt,list(U)],'low_vol6':-vol.loc[dt,list(U)],'drawdown6':dd.loc[dt,list(U)]},index=list(U))
        if b.isna().any().any(): continue
        chosen=list(b.rank(axis=0,pct=True,method='average').mean(axis=1).sort_values(ascending=False,kind='mergesort').head(2).index); nxt=m.index[i+1]; rr=m.loc[nxt,list(U)]/m.loc[dt,list(U)]-1
        if rr.isna().any(): continue
        w={s:(.5 if s in chosen else 0.) for s in U}; turn=.5*sum(abs(w[s]-prev[s]) for s in U); gross=sum(w[s]*float(rr[s]) for s in U); rows.append({'date':nxt,'gross':gross,'turnover':turn,'equal_weight':float(rr.mean()),'qqq':float(rr.QQQ),'spy':float(rr.SPY)}); prev=w
    return pd.DataFrame(rows).set_index('date'),d,cut

def evaluate(q,cost):
    net=q.gross-q.turnover*cost/10000
    return {'months':len(q),'cagr':cagr(net),'equal_weight_cagr':cagr(q.equal_weight),'qqq_cagr':cagr(q.qqq),'spy_cagr':cagr(q.spy),'excess_equal_weight':cagr(net)-cagr(q.equal_weight),'excess_qqq':cagr(net)-cagr(q.qqq),'excess_spy':cagr(net)-cagr(q.spy),'mean_monthly_turnover':float(q.turnover.mean()),'annualized_one_way_turnover':float(q.turnover.mean()*12)}
def main():
    q,d,cut=build(); windows={'2015':'2015-01-01','2020':'2020-01-01','2022':'2022-01-01'}; tests={w:{str(c):evaluate(q.loc[pd.Timestamp(s):],c) for c in COSTS} for w,s in windows.items()}
    thresholds={}
    for w in windows:
        thresholds[w]={k:max([c for c in COSTS if tests[w][str(c)][k]>0],default=None) for k in ('excess_equal_weight','excess_qqq','excess_spy')}
    a=tests['2015']['200']; b=tests['2020']['200']; decision='P46_COST_ENVELOPE_STRONG' if a['excess_equal_weight']>0 and a['excess_qqq']>0 and b['excess_equal_weight']>0 else 'P46_COST_ENVELOPE_LIMITED'
    out={'schema':'research.p46_cost_turnover_envelope_r1','parent':'P46','hypothesis':'The frozen P46 selector retains economically meaningful matched and opportunity excess under implementation friction materially above the previously tested 50-100 bps range.','contract':{'selector':'frozen original P46 four-factor cross-asset top-2 monthly','cost_bps_per_one_way_turnover':list(COSTS),'controls':['same-universe equal-weight','QQQ','SPY'],'windows':list(windows),'no_signal_weight_or_window_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(cut.date()),'panel_sha256':hashlib.sha256(d.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest()},'tests':tests,'highest_tested_positive_cost_bps':thresholds,'decision':decision}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_cost_turnover_envelope_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
