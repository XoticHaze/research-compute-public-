from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

OUT=Path('research/artifacts/p524_p249_primitive_persistence_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
CROSS=('SPY','QQQ','TLT','GLD','DBC')
IND=('SOXX','XBI','XHB','KRE','ITA','IGV','IYT','XRT','XOP','IHI')
T=list(dict.fromkeys((*CROSS,*IND,'AVUV','AVDV','IJR','VSS')))
P64BP=50; P36BP=50
BLOCKS={'2010_2013':('2010-01-01','2013-12-31'),'2014_2017':('2014-01-01','2017-12-31'),'2018_2021':('2018-01-01','2021-12-31'),'2022_2026aug':('2022-01-01','2026-08-31')}
raw=yf.download(T,start='2005-01-01',end='2026-09-01',auto_adjust=True,progress=False,threads=False)
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
        chosen=score.nlargest(topk).index; w={s:(1/topk if s in chosen else 0.) for s in symbols}; to=.5*sum(abs(w[s]-prev[s]) for s in symbols)
        rows.append((nxt,sum(w[s]*float(rr[s]) for s in symbols),float(rr.mean()),to)); prev=w
    return pd.DataFrame(rows,columns=['date','gross','matched','turn']).set_index('date')

a=rank_frame(CROSS,2); b=rank_frame(IND,3); ix=a.index.intersection(b.index)
p64=pd.DataFrame({'ret':.5*(a.loc[ix].gross-a.loc[ix].turn*P64BP/10000)+.5*(b.loc[ix].gross-b.loc[ix].turn*P64BP/10000),'ctl':.5*a.loc[ix].matched+.5*b.loc[ix].matched},index=ix); p64.index=p64.index.to_period('M').to_timestamp('M')

def p36():
    z=c[['SOXX','QQQ']].dropna(); idx=z.index; mm=z.resample('ME').last(); rel=mm['SOXX'].pct_change(6)-mm['QQQ'].pct_change(6); sig={dt:(1. if rel.loc[dt]>0 else 0.) for dt in mm.index if pd.notna(rel.loc[dt])}; labs=list(sig); prev=None; rows=[]
    for i in range(len(labs)-1):
        dt,nxt=labs[i],labs[i+1]; i0=idx.get_indexer([dt],method='pad')[0]+1; i1=idx.get_indexer([nxt],method='pad')[0]+1
        if i0<0 or i1<0 or i1>=len(idx): continue
        w=sig[dt]; ar=float(z.iloc[i1].SOXX/z.iloc[i0].SOXX-1); qr=float(z.iloc[i1].QQQ/z.iloc[i0].QQQ-1); to=1. if prev is None else abs(w-prev)
        rows.append((idx[i1],w*ar+(1-w)*qr-to*P36BP/10000,.5*(ar+qr))); prev=w
    q=pd.DataFrame(rows,columns=['date','ret','ctl']).set_index('date'); q.index=q.index.to_period('M').to_timestamp('M'); return q

p36x=p36(); svr=m[['AVUV','AVDV','IJR','VSS']].pct_change(fill_method=None)
sv=pd.DataFrame({'ret':.5*(svr.AVUV+svr.AVDV),'ctl':.5*(svr.IJR+svr.VSS)})
q=sv.rename(columns={'ret':'sv','ctl':'svctl'}).join(p64.rename(columns={'ret':'p64','ctl':'p64ctl'})).join(p36x.rename(columns={'ret':'p36','ctl':'p36ctl'})).dropna().loc['2010-01-01':'2026-08-31']
q['p249']=(q.sv+q.p64+q.p36)/3; q['p249ctl']=(q.svctl+q.p64ctl+q.p36ctl)/3

def metrics(ret,ctl,start=None,end=None):
    z=pd.DataFrame({'ret':ret,'ctl':ctl}).dropna()
    if start: z=z.loc[z.index>=pd.Timestamp(start)]
    if end: z=z.loc[z.index<=pd.Timestamp(end)]
    ex=z.ret-z.ctl
    return {'months':int(len(z)),'annualized_mean_excess':float(ex.mean()*12),'matched_excess_hit_rate':float((ex>0).mean()),'positive_total_excess':bool((1+z.ret).prod()>(1+z.ctl).prod())}

prims={'SMALL_VALUE':('sv','svctl'),'P64':('p64','p64ctl'),'P36':('p36','p36ctl'),'P249':('p249','p249ctl')}
outp={}
for name,(rc,cc) in prims.items():
    full=metrics(q[rc],q[cc]); blocks={k:metrics(q[rc],q[cc],a,b) for k,(a,b) in BLOCKS.items()}
    outp[name]={'full':full,'blocks':blocks,'positive_excess_blocks':sum(v['annualized_mean_excess']>0 for v in blocks.values())}
primitive_names=['SMALL_VALUE','P64','P36']
robust=[n for n in primitive_names if outp[n]['full']['annualized_mean_excess']>0 and outp[n]['positive_excess_blocks']>=3]
fragile=[n for n in primitive_names if n not in robust]
decision='P249_MULTI_PRIMITIVE_EXCESS_PERSISTENCE_SUPPORTED' if len(robust)>=2 and outp['P249']['positive_excess_blocks']>=3 else 'P249_PRIMITIVE_PERSISTENCE_CONCENTRATED'
out={'schema':'research.p524_p249_primitive_persistence_r1.v1','workload_id':'P524_P249_PRIMITIVE_PERSISTENCE_R1','parent':'P249','claim':'The selected P249 core should derive matched excess from multiple frozen primitives across chronology rather than from a single primitive.','contract':{'reconstruct':'frozen small-value, P64, P36 and equal-third P249 semantics with declared costs','sample':'2010-01 through completed 2026-08','blocks':BLOCKS,'primitive_robust_rule':'full-sample annualized mean matched excess >0 and positive in >=3/4 fixed chronology blocks','core_support_rule':'at least two of three primitives robust and P249 positive in >=3/4 blocks','no_weight_product_date_cost_threshold_lookback_or_subset_search':True},'primitives':outp,'robust_primitives':robust,'fragile_primitives':fragile,'decision':decision,'scientific_consequence':'Use primitive persistence only to narrow or strengthen the scientific survivor claim. Do not remove, reweight, or allocate primitives from this diagnostic.','boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':decision,'robust':robust,'fragile':fragile,'primitives':{k:{'full_excess_pp':round(v['full']['annualized_mean_excess']*100,3),'positive_blocks':v['positive_excess_blocks']} for k,v in outp.items()}},sort_keys=True))