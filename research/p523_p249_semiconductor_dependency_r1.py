from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

OUT=Path('research/artifacts/p523_p249_semiconductor_dependency_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
CROSS=('SPY','QQQ','TLT','GLD','DBC')
IND=('SOXX','XBI','XHB','KRE','ITA','IGV','IYT','XRT','XOP','IHI')
T=list(dict.fromkeys((*CROSS,*IND,'AVUV','AVDV','IJR','VSS')))
P64BP=50; P36BP=50
raw=yf.download(T,start='2005-01-01',end='2026-09-11',auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw).dropna(how='all').astype(float)
m=c.resample('ME').last(); r=m.pct_change(fill_method=None)

def rank_frame(symbols,topk):
    mm=c[list(symbols)].resample('ME').last(); mom=mm.pct_change(6)
    trend=(c[list(symbols)]/c[list(symbols)].rolling(200,min_periods=160).mean()-1).resample('ME').last()
    prev={s:0. for s in symbols}; rows=[]
    for dt in mm.index:
        b=pd.DataFrame({'mom':mom.loc[dt,list(symbols)],'trend':trend.loc[dt,list(symbols)]},index=list(symbols)); loc=mm.index.get_loc(dt)
        if b.isna().any().any() or not isinstance(loc,(int,np.integer)) or loc+1>=len(mm): continue
        score=b.rank(axis=0,pct=True).mean(axis=1); nxt=mm.index[loc+1]
        rr=mm.loc[nxt,list(symbols)]/mm.loc[dt,list(symbols)]-1
        if rr.isna().any(): continue
        chosen=score.nlargest(topk).index; w={s:(1/topk if s in chosen else 0.) for s in symbols}
        to=.5*sum(abs(w[s]-prev[s]) for s in symbols)
        rows.append((nxt,sum(w[s]*float(rr[s]) for s in symbols),float(rr.mean()),to)); prev=w
    return pd.DataFrame(rows,columns=['date','gross','matched','turn']).set_index('date')

a=rank_frame(CROSS,2); b=rank_frame(IND,3); ix=a.index.intersection(b.index)
p64=pd.DataFrame({'x':.5*(a.loc[ix].gross-a.loc[ix].turn*P64BP/10000)+.5*(b.loc[ix].gross-b.loc[ix].turn*P64BP/10000),'ctl':.5*a.loc[ix].matched+.5*b.loc[ix].matched},index=ix); p64.index=p64.index.to_period('M').to_timestamp('M')

def p36():
    z=c[['SOXX','QQQ']].dropna(); idx=z.index; mm=z.resample('ME').last(); rel=mm['SOXX'].pct_change(6)-mm['QQQ'].pct_change(6); sig={dt:(1. if rel.loc[dt]>0 else 0.) for dt in mm.index if pd.notna(rel.loc[dt])}; labs=list(sig); prev=None; rows=[]
    for i in range(len(labs)-1):
        dt,nxt=labs[i],labs[i+1]; i0=idx.get_indexer([dt],method='pad')[0]+1; i1=idx.get_indexer([nxt],method='pad')[0]+1
        if i0<0 or i1<0 or i1>=len(idx): continue
        w=sig[dt]; ar=float(z.iloc[i1].SOXX/z.iloc[i0].SOXX-1); qr=float(z.iloc[i1].QQQ/z.iloc[i0].QQQ-1); to=1. if prev is None else abs(w-prev)
        rows.append((idx[i1],w*ar+(1-w)*qr-to*P36BP/10000,.5*(ar+qr),'SOXX' if w>0 else 'QQQ')); prev=w
    q=pd.DataFrame(rows,columns=['date','x','ctl','state']).set_index('date'); q.index=q.index.to_period('M').to_timestamp('M'); return q

p36x=p36(); svr=m[['AVUV','AVDV','IJR','VSS']].pct_change(fill_method=None); sv=.5*(svr.AVUV+svr.AVDV); svctl=.5*(svr.IJR+svr.VSS)
base=sv.to_frame('sv').join(svctl.rename('svctl')).join(p64.rename(columns={'x':'p64','ctl':'p64ctl'})).join(p36x.rename(columns={'x':'p36','ctl':'p36ctl'})).dropna()
base['p249']=(base.sv+base.p64+base.p36)/3; base['ctl']=(base.svctl+base.p64ctl+base.p36ctl)/3; base['excess']=base.p249-base.ctl; base['spy']=r.SPY
q=base.loc['2010-01-01':'2026-08-31'].copy()

def state_stats(name):
    z=q[q.state==name]
    if len(z)<18: return {'months':int(len(z)),'ready':False}
    ann_excess=float(z.excess.mean()*12); ann_vs_spy=float((z.p249-z.spy).mean()*12); hit=float((z.excess>0).mean()); downside=z[z.spy<0]
    return {'months':int(len(z)),'ready':True,'annualized_mean_excess_vs_matched':ann_excess,'annualized_mean_excess_vs_spy':ann_vs_spy,'monthly_matched_excess_hit_rate':hit,'down_spy_months':int(len(downside)),'down_spy_annualized_mean_excess_vs_matched':float(downside.excess.mean()*12) if len(downside) else None}

states={k:state_stats(k) for k in ('SOXX','QQQ')}; ready=all(v.get('ready') for v in states.values())
supported=ready and all(v['annualized_mean_excess_vs_matched']>0 for v in states.values()) and all(v['monthly_matched_excess_hit_rate']>=.5 for v in states.values())
decision='P249_EXCESS_NOT_SEMICONDUCTOR_STATE_DEPENDENT' if supported else ('P249_SEMICONDUCTOR_STATE_DEPENDENCY_DETECTED' if ready else 'P249_SEMICONDUCTOR_DEPENDENCY_DATA_NOT_READY')
out={'schema':'research.p523_p249_semiconductor_dependency_r1.v1','workload_id':'P523_P249_SEMICONDUCTOR_DEPENDENCY_R1','parent':'P249','claim':'P249 matched excess should remain positive across both causal P36 states rather than being confined to months when its P36 primitive selects SOXX.','contract':{'reconstruct':'frozen P249 equal-third small-value/P64/P36 semantics and declared costs','sample':'2010-01 through completed 2026-08','states':['P36 selects SOXX','P36 selects QQQ'],'support_rule':'each state >=18 months, annualized mean matched excess >0 and monthly matched-excess hit rate >=50% in both states','no_state_threshold_weight_product_date_cost_or_parameter_search':True},'states':states,'decision':decision,'scientific_consequence':'If dependency is detected, narrow the P249 survivor claim to acknowledge semiconductor-state concentration without changing weights or allocation. If not detected, preserve P249 as a multi-primitive return survivor while continuing prospective observation.','boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':decision,'states':states},sort_keys=True))