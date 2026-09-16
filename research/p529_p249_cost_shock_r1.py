from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
OUT=Path('research/artifacts/p529_p249_cost_shock_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
CROSS=('SPY','QQQ','TLT','GLD','DBC'); IND=('SOXX','XBI','XHB','KRE','ITA','IGV','IYT','XRT','XOP','IHI'); T=list(dict.fromkeys((*CROSS,*IND,'AVUV','AVDV','IJR','VSS'))); COST_BP=100
raw=yf.download(T,start='2005-01-01',end='2026-09-01',auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw).dropna(how='all').astype(float); m=c.resample('ME').last()
def rank_frame(symbols,topk):
    mm=c[list(symbols)].resample('ME').last(); mom=mm.pct_change(6); trend=(c[list(symbols)]/c[list(symbols)].rolling(200,min_periods=160).mean()-1).resample('ME').last(); prev={s:0. for s in symbols}; rows=[]
    for dt in mm.index:
        b=pd.DataFrame({'mom':mom.loc[dt,list(symbols)],'trend':trend.loc[dt,list(symbols)]},index=list(symbols)); loc=mm.index.get_loc(dt)
        if b.isna().any().any() or not isinstance(loc,(int,np.integer)) or loc+1>=len(mm): continue
        score=b.rank(axis=0,pct=True).mean(axis=1); nxt=mm.index[loc+1]; rr=mm.loc[nxt,list(symbols)]/mm.loc[dt,list(symbols)]-1
        if rr.isna().any(): continue
        chosen=score.nlargest(topk).index; w={s:(1/topk if s in chosen else 0.) for s in symbols}; to=.5*sum(abs(w[s]-prev[s]) for s in symbols); rows.append((nxt,sum(w[s]*float(rr[s]) for s in symbols)-to*COST_BP/10000,float(rr.mean()))); prev=w
    return pd.DataFrame(rows,columns=['date','ret','ctl']).set_index('date')
a=rank_frame(CROSS,2); b=rank_frame(IND,3); ix=a.index.intersection(b.index); p64=pd.DataFrame({'ret':.5*a.loc[ix].ret+.5*b.loc[ix].ret,'ctl':.5*a.loc[ix].ctl+.5*b.loc[ix].ctl},index=ix); p64.index=p64.index.to_period('M').to_timestamp('M')
def p36():
    z=c[['SOXX','QQQ']].dropna(); idx=z.index; mm=z.resample('ME').last(); rel=mm.SOXX.pct_change(6)-mm.QQQ.pct_change(6); sig={dt:(1. if rel.loc[dt]>0 else 0.) for dt in mm.index if pd.notna(rel.loc[dt])}; labs=list(sig); prev=None; rows=[]
    for i in range(len(labs)-1):
        dt,nxt=labs[i],labs[i+1]; i0=idx.get_indexer([dt],method='pad')[0]+1; i1=idx.get_indexer([nxt],method='pad')[0]+1
        if i0<0 or i1<0 or i1>=len(idx): continue
        w=sig[dt]; ar=float(z.iloc[i1].SOXX/z.iloc[i0].SOXX-1); qr=float(z.iloc[i1].QQQ/z.iloc[i0].QQQ-1); to=1. if prev is None else abs(w-prev); rows.append((idx[i1],w*ar+(1-w)*qr-to*COST_BP/10000,.5*(ar+qr))); prev=w
    q=pd.DataFrame(rows,columns=['date','ret','ctl']).set_index('date'); q.index=q.index.to_period('M').to_timestamp('M'); return q
p36x=p36(); svr=m[['AVUV','AVDV','IJR','VSS']].pct_change(fill_method=None); sv=pd.DataFrame({'ret':.5*(svr.AVUV+svr.AVDV),'ctl':.5*(svr.IJR+svr.VSS)})
q=sv.rename(columns={'ret':'sv','ctl':'svctl'}).join(p64.rename(columns={'ret':'p64','ctl':'p64ctl'})).join(p36x.rename(columns={'ret':'p36','ctl':'p36ctl'})).dropna().loc[:'2026-08-31']; q['p249']=(q.sv+q.p64+q.p36)/3; q['ctl']=(q.svctl+q.p64ctl+q.p36ctl)/3; q['excess']=q.p249-q.ctl
n=len(q); cuts=[0,n//3,2*n//3,n]; blocks={}
for i in range(3):
    z=q.iloc[cuts[i]:cuts[i+1]]; blocks[f'block_{i+1}']={'months':int(len(z)),'start':str(z.index.min().date()),'end':str(z.index.max().date()),'annualized_matched_excess':float(z.excess.mean()*12)}
full=float(q.excess.mean()*12); positive=sum(v['annualized_matched_excess']>0 for v in blocks.values()); decision='P249_DOUBLE_COST_ROBUSTNESS_SUPPORTED' if full>0 and positive>=2 else 'P249_DOUBLE_COST_FRAGILITY'
out={'schema':'research.p529_p249_cost_shock_r1.v1','workload_id':'P529_P249_COST_SHOCK_R1','parent':'P249','claim':'The frozen P249 core should retain positive matched excess under a predeclared 2x turnover-cost stress without changing signals or weights.','contract':{'base_declared_turnover_cost_bp':50,'stress_turnover_cost_bp':100,'stress_multiplier':2,'sample_end':'2026-08-31','support_rule':'full-sample annualized matched excess >0 and positive in >=2/3 contiguous common-sample blocks','no_weight_product_date_threshold_lookback_state_subset_or_posthoc_cost_search':True},'coverage':{'start':str(q.index.min().date()),'end':str(q.index.max().date()),'months':int(n)},'annualized_matched_excess':full,'positive_blocks':positive,'blocks':blocks,'decision':decision,'scientific_consequence':'Use only as implementation-friction robustness evidence. Do not infer allocation, execution-cost authority, or runtime changes.','boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':decision,'full_excess_pp':round(full*100,3),'positive_blocks':positive,'blocks':{k:round(v['annualized_matched_excess']*100,3) for k,v in blocks.items()}},sort_keys=True))
