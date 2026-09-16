from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

OUT=Path('research/artifacts/p527_p249_block_bootstrap_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
CROSS=('SPY','QQQ','TLT','GLD','DBC'); IND=('SOXX','XBI','XHB','KRE','ITA','IGV','IYT','XRT','XOP','IHI')
T=list(dict.fromkeys((*CROSS,*IND,'AVUV','AVDV','IJR','VSS')))
raw=yf.download(T,start='2005-01-01',end='2026-09-01',auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw).dropna(how='all').astype(float); m=c.resample('ME').last()

def rank_frame(symbols,topk,bp=50):
    mm=c[list(symbols)].resample('ME').last(); mom=mm.pct_change(6); trend=(c[list(symbols)]/c[list(symbols)].rolling(200,min_periods=160).mean()-1).resample('ME').last()
    prev={s:0. for s in symbols}; rows=[]
    for dt in mm.index:
        b=pd.DataFrame({'mom':mom.loc[dt,list(symbols)],'trend':trend.loc[dt,list(symbols)]},index=list(symbols)); loc=mm.index.get_loc(dt)
        if b.isna().any().any() or not isinstance(loc,(int,np.integer)) or loc+1>=len(mm): continue
        score=b.rank(axis=0,pct=True).mean(axis=1); nxt=mm.index[loc+1]; rr=mm.loc[nxt,list(symbols)]/mm.loc[dt,list(symbols)]-1
        if rr.isna().any(): continue
        chosen=score.nlargest(topk).index; w={s:(1/topk if s in chosen else 0.) for s in symbols}; to=.5*sum(abs(w[s]-prev[s]) for s in symbols)
        rows.append((nxt,sum(w[s]*float(rr[s]) for s in symbols)-to*bp/10000,float(rr.mean()))); prev=w
    return pd.DataFrame(rows,columns=['date','ret','ctl']).set_index('date')

a=rank_frame(CROSS,2); b=rank_frame(IND,3); ix=a.index.intersection(b.index)
p64=pd.DataFrame({'ret':.5*a.loc[ix].ret+.5*b.loc[ix].ret,'ctl':.5*a.loc[ix].ctl+.5*b.loc[ix].ctl},index=ix); p64.index=p64.index.to_period('M').to_timestamp('M')

def p36():
    z=c[['SOXX','QQQ']].dropna(); idx=z.index; mm=z.resample('ME').last(); rel=mm['SOXX'].pct_change(6)-mm['QQQ'].pct_change(6); sig={dt:(1. if rel.loc[dt]>0 else 0.) for dt in mm.index if pd.notna(rel.loc[dt])}; labs=list(sig); prev=None; rows=[]
    for i in range(len(labs)-1):
        dt,nxt=labs[i],labs[i+1]; i0=idx.get_indexer([dt],method='pad')[0]+1; i1=idx.get_indexer([nxt],method='pad')[0]+1
        if i0<0 or i1<0 or i1>=len(idx): continue
        w=sig[dt]; ar=float(z.iloc[i1].SOXX/z.iloc[i0].SOXX-1); qr=float(z.iloc[i1].QQQ/z.iloc[i0].QQQ-1); to=1. if prev is None else abs(w-prev)
        rows.append((idx[i1],w*ar+(1-w)*qr-to*50/10000,.5*(ar+qr))); prev=w
    q=pd.DataFrame(rows,columns=['date','ret','ctl']).set_index('date'); q.index=q.index.to_period('M').to_timestamp('M'); return q

p36x=p36(); svr=m[['AVUV','AVDV','IJR','VSS']].pct_change(fill_method=None); sv=pd.DataFrame({'ret':.5*(svr.AVUV+svr.AVDV),'ctl':.5*(svr.IJR+svr.VSS)})
q=sv.rename(columns={'ret':'sv','ctl':'svctl'}).join(p64.rename(columns={'ret':'p64','ctl':'p64ctl'})).join(p36x.rename(columns={'ret':'p36','ctl':'p36ctl'})).dropna().loc[:'2026-08-31']
q['p249']=(q.sv+q.p64+q.p36)/3; q['ctl']=(q.svctl+q.p64ctl+q.p36ctl)/3; ex=(q.p249-q.ctl).to_numpy(float)
if len(ex)<60: raise SystemExit('COMMON_SAMPLE_COVERAGE_NOT_READY')

# Prospectively frozen uncertainty test: circular moving-block bootstrap preserves local serial dependence.
BLOCK=6; REPS=20000; SEED=249527; rng=np.random.default_rng(SEED); n=len(ex); starts=np.arange(n); vals=np.empty(REPS)
for j in range(REPS):
    draw=[]
    while len(draw)<n:
        s=int(rng.choice(starts)); draw.extend(ex[(s+np.arange(BLOCK))%n].tolist())
    vals[j]=np.mean(draw[:n])*12
q05=float(np.quantile(vals,.05)); med=float(np.quantile(vals,.50)); q95=float(np.quantile(vals,.95)); ppos=float(np.mean(vals>0)); point=float(np.mean(ex)*12)
decision='P249_MATCHED_EXCESS_BLOCK_BOOTSTRAP_SUPPORTED' if q05>0 and ppos>=.95 else 'P249_MATCHED_EXCESS_SAMPLING_FRAGILITY'
out={'schema':'research.p527_p249_block_bootstrap_r1.v1','workload_id':'P527_P249_BLOCK_BOOTSTRAP_R1','parent':'P249','claim':'P249 matched excess should remain positive under sequence-aware resampling of its exact completed common sample.','contract':{'reconstruction':'frozen equal-third small-value + P64 + P36 with declared 50bp turnover costs','sample_end':'2026-08-31','bootstrap':'circular moving-block bootstrap of monthly matched excess','block_months':BLOCK,'reps':REPS,'seed':SEED,'support_rule':'5th percentile annualized matched excess > 0 and >=95% bootstrap replicates positive','no_weight_product_date_cost_threshold_lookback_state_or_subset_search':True},'coverage':{'start':str(q.index.min().date()),'end':str(q.index.max().date()),'months':int(n)},'annualized_matched_excess':{'point':point,'q05':q05,'median':med,'q95':q95,'positive_rep_rate':ppos},'decision':decision,'scientific_consequence':'Strengthen or narrow P249 statistical robustness only. No allocation, primitive reweighting, or runtime authority follows from this diagnostic.','boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':decision,'months':n,'point_pp':round(point*100,3),'q05_pp':round(q05*100,3),'median_pp':round(med*100,3),'q95_pp':round(q95*100,3),'positive_rep_rate':round(ppos,4)},sort_keys=True))
