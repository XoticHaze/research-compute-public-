from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

COUNTRIES=['EWA','EWC','EWG','EWH','EWJ','EWW','EWS','EWT','EWU','EWY','EZA','FXI']
CONTROLS=['ACWI','SPY']
ALL=COUNTRIES+CONTROLS
START='2009-01-01'; END='2026-09-10'; COST_BP=50; TOP_K=3; LOOKBACK_MONTHS=12
WINDOWS={'2015_plus':'2015-01-01','2020_plus':'2020-01-01','2022_plus':'2022-01-01'}
raw=yf.download(ALL,start=START,end=END,auto_adjust=True,progress=False,threads=False)
close=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[ALL].dropna()
m=close.resample('ME').last(); ret=m.pct_change(); score=m[COUNTRIES].shift(1)/m[COUNTRIES].shift(LOOKBACK_MONTHS)-1
w=pd.DataFrame(0.0,index=m.index,columns=COUNTRIES)
for dt,row in score.iterrows():
    if row.notna().sum()==len(COUNTRIES): w.loc[dt,row.nlargest(TOP_K).index]=1/TOP_K
gross=(w*ret[COUNTRIES]).sum(axis=1); turn=.5*w.diff().abs().sum(axis=1); active=w.sum(axis=1).gt(0)
if active.any(): turn.loc[active.idxmax()]=1.0
candidate=gross-(COST_BP/10000)*turn
matched=ret[COUNTRIES].mean(axis=1).copy()
if active.any(): matched.loc[active.idxmax()]-=COST_BP/10000
acwi=ret.ACWI.copy(); spy=ret.SPY.copy()
if active.any():
    first=active.idxmax(); acwi.loc[first]-=COST_BP/10000; spy.loc[first]-=COST_BP/10000
x=pd.DataFrame({'candidate':candidate,'matched':matched,'ACWI':acwi,'SPY':spy}).loc[active].dropna()

def metrics(r):
    q=pd.Series(r,dtype=float).dropna(); n=len(q); eq=(1+q).cumprod(); vol=float(q.std(ddof=1)*math.sqrt(12)) if n>1 else 0
    return {'months':int(n),'cagr':float(eq.iloc[-1]**(12/n)-1),'maxdd':float((eq/eq.cummax()-1).min()),'sharpe_rf0':float(q.mean()*12/vol) if vol else None}

def eval_window(q):
    a=metrics(q.candidate); b=metrics(q.matched); c=metrics(q.ACWI); s=metrics(q.SPY)
    folds=[]
    for i,ix in enumerate(np.array_split(np.arange(len(q)),5),1):
        z=q.iloc[ix]; ma=metrics(z.candidate)['cagr']; mb=metrics(z.matched)['cagr']
        folds.append({'fold':i,'candidate_cagr':ma,'matched_cagr':mb,'matched_excess_cagr':ma-mb})
    return {'candidate':a,'matched':b,'ACWI':c,'SPY':s,'matched_excess_cagr':a['cagr']-b['cagr'],'vs_ACWI_cagr':a['cagr']-c['cagr'],'vs_SPY_cagr':a['cagr']-s['cagr'],'positive_matched_folds':sum(f['matched_excess_cagr']>0 for f in folds),'folds':folds}
results={name:eval_window(x.loc[x.index>=pd.Timestamp(start)]) for name,start in WINDOWS.items()}
passes=sum(v['matched_excess_cagr']>0 and v['positive_matched_folds']>=3 for v in results.values())
# This is a transport test, not a requirement that every country universe dominate US equities.
# Durable cross-universe support requires positive after-cost matched excess with chronology breadth in all fixed windows,
# plus non-negative ACWI opportunity excess in at least two of three windows.
acwi_pass=sum(v['vs_ACWI_cagr']>=0 for v in results.values())
supported=passes==len(WINDOWS) and acwi_pass>=2
decision='P354_COUNTRY_MOMENTUM_TRANSPORT_SUPPORTED' if supported else 'P354_COUNTRY_MOMENTUM_TRANSPORT_NOT_CONFIRMED'
out={'schema':'research.p354_country_momentum_transport_r1','parent':'P266_INDUSTRY_MOMENTUM_ARCHITECTURE_TRANSPORT','claim':'Orthogonal universe transport of the already-fixed 12-month, top-3, monthly cross-sectional momentum architecture from US industries to a frozen 12-country ETF universe. No lookback, top-k, country, threshold, cost, window, or weight search.','contract':{'countries':COUNTRIES,'lookback_months':LOOKBACK_MONTHS,'top_k':TOP_K,'rebalance':'monthly','one_way_turnover_cost_bps':COST_BP,'matched_control':'equal-weight exact country universe','opportunity_controls':CONTROLS,'windows':WINDOWS,'gate':'positive after-cost matched excess and >=3/5 positive chronology folds in all three fixed windows, plus non-negative CAGR vs ACWI in >=2/3 windows'},'common_sample':{'start':str(x.index.min().date()),'last_month_label':str(x.index.max().date()),'months':int(len(x)),'input_end_exclusive':END},'results':results,'gate_counts':{'matched_chronology_windows_passed':passes,'ACWI_opportunity_windows_nonnegative':acwi_pass},'decision':decision,'scientific_consequence':'Pass broadens the fixed cross-sectional momentum mechanism beyond US industries. Failure narrows transportability only and does not kill the previously supported industry survivor; do not rescue by changing country set, top-k, lookback, costs, or windows.','limitations':['Yahoo adjusted-price representation','ETF histories proxy country equity exposures rather than constituent-level country universes','monthly labels may fall after input cutoff because resampling labels month-end; no observations after the input cutoff are downloaded'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p354_country_momentum_transport_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
