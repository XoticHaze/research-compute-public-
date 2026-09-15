# Fresh Market Research firing trigger 2026-09-15; scientific specification below unchanged.
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

OUT=Path('research/artifacts/p249_p64_information_ablation_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
CROSS=('SPY','QQQ','TLT','GLD','DBC')
IND=('SOXX','XBI','XHB','KRE','ITA','IGV','IYT','XRT','XOP','IHI')
T=list(dict.fromkeys((*CROSS,*IND,'AVUV','AVDV','IJR','VSS')))
COST_BP=50
BLOCKS={'block_1':(0,1/3),'block_2':(1/3,2/3),'block_3':(2/3,1)}

raw=yf.download(T,start='2005-01-01',end='2026-09-01',auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw).dropna(how='all').astype(float)
m=c.resample('ME').last()

def rank_frame(symbols,topk,features):
    mm=c[list(symbols)].resample('ME').last(); mom=mm.pct_change(6); trend=(c[list(symbols)]/c[list(symbols)].rolling(200,min_periods=160).mean()-1).resample('ME').last(); prev={s:0. for s in symbols}; rows=[]
    for dt in mm.index:
        cols={}
        if 'mom' in features: cols['mom']=mom.loc[dt,list(symbols)]
        if 'trend' in features: cols['trend']=trend.loc[dt,list(symbols)]
        b=pd.DataFrame(cols,index=list(symbols)); loc=mm.index.get_loc(dt)
        if b.isna().any().any() or not isinstance(loc,(int,np.integer)) or loc+1>=len(mm): continue
        score=b.rank(axis=0,pct=True).mean(axis=1); nxt=mm.index[loc+1]; rr=mm.loc[nxt,list(symbols)]/mm.loc[dt,list(symbols)]-1
        if rr.isna().any(): continue
        chosen=score.nlargest(topk).index; w={s:(1/topk if s in chosen else 0.) for s in symbols}; to=.5*sum(abs(w[s]-prev[s]) for s in symbols); rows.append((nxt,sum(w[s]*float(rr[s]) for s in symbols)-to*COST_BP/10000,float(rr.mean()))); prev=w
    q=pd.DataFrame(rows,columns=['date','ret','ctl']).set_index('date'); q.index=q.index.to_period('M').to_timestamp('M'); return q

def p64(features):
    a=rank_frame(CROSS,2,features); b=rank_frame(IND,3,features); ix=a.index.intersection(b.index); return pd.DataFrame({'ret':.5*a.loc[ix].ret+.5*b.loc[ix].ret,'ctl':.5*a.loc[ix].ctl+.5*b.loc[ix].ctl},index=ix)

def p36():
    z=c[['SOXX','QQQ']].dropna(); idx=z.index; mm=z.resample('ME').last(); rel=mm.SOXX.pct_change(6)-mm.QQQ.pct_change(6); sig={dt:(1. if rel.loc[dt]>0 else 0.) for dt in mm.index if pd.notna(rel.loc[dt])}; labs=list(sig); prev=None; rows=[]
    for i in range(len(labs)-1):
        dt,nxt=labs[i],labs[i+1]; i0=idx.get_indexer([dt],method='pad')[0]+1; i1=idx.get_indexer([nxt],method='pad')[0]+1
        if i0<0 or i1<0 or i1>=len(idx): continue
        w=sig[dt]; ar=float(z.iloc[i1].SOXX/z.iloc[i0].SOXX-1); qr=float(z.iloc[i1].QQQ/z.iloc[i0].QQQ-1); to=1. if prev is None else abs(w-prev); rows.append((idx[i1],w*ar+(1-w)*qr-to*COST_BP/10000,.5*(ar+qr))); prev=w
    q=pd.DataFrame(rows,columns=['date','ret','ctl']).set_index('date'); q.index=q.index.to_period('M').to_timestamp('M'); return q

svr=m[['AVUV','AVDV','IJR','VSS']].pct_change(fill_method=None); sv=pd.DataFrame({'ret':.5*(svr.AVUV+svr.AVDV),'ctl':.5*(svr.IJR+svr.VSS)}); p36x=p36(); variants={'INCUMBENT_MOM_TREND':p64(('mom','trend')),'MOM_ONLY':p64(('mom',)),'TREND_ONLY':p64(('trend',))}
def evaluate(p64x):
    q=sv.rename(columns={'ret':'sv','ctl':'svctl'}).join(p64x.rename(columns={'ret':'p64','ctl':'p64ctl'})).join(p36x.rename(columns={'ret':'p36','ctl':'p36ctl'})).dropna().loc[:'2026-08-31']; q['ret']=(q.sv+q.p64+q.p36)/3; q['ctl']=(q.svctl+q.p64ctl+q.p36ctl)/3; q['excess']=q.ret-q.ctl; n=len(q); cuts=[0,n//3,2*n//3,n]; blocks=[]
    for i in range(3):
        z=q.iloc[cuts[i]:cuts[i+1]]; blocks.append(float(z.excess.mean()*12))
    wealth=(1+q.ret).cumprod(); ctlw=(1+q.ctl).cumprod(); years=n/12
    return {'months':int(n),'start':str(q.index.min().date()),'end':str(q.index.max().date()),'candidate_cagr':float(wealth.iloc[-1]**(1/years)-1),'matched_control_cagr':float(ctlw.iloc[-1]**(1/years)-1),'annualized_mean_matched_excess':float(q.excess.mean()*12),'positive_blocks':int(sum(x>0 for x in blocks)),'blocks_annualized_mean_excess':blocks,'max_drawdown':float((wealth/wealth.cummax()-1).min())}
res={k:evaluate(v) for k,v in variants.items()}; inc=res['INCUMBENT_MOM_TREND']
for k,v in res.items(): v['excess_delta_vs_incumbent_pp']=100*(v['annualized_mean_matched_excess']-inc['annualized_mean_matched_excess'])
challengers=['MOM_ONLY','TREND_ONLY']; best=max(challengers,key=lambda k:res[k]['annualized_mean_matched_excess']); promote=bool(res[best]['annualized_mean_matched_excess']>inc['annualized_mean_matched_excess'] and res[best]['positive_blocks']>=inc['positive_blocks'] and res[best]['positive_blocks']>=2); decision=f'P249_P64_INFORMATION_ABLATION__{best}__CHALLENGER' if promote else 'P249_P64_INFORMATION_ABLATION__INCUMBENT_INFORMATION_SET_SURVIVES'
out={'schema':'research.p249_p64_information_ablation_r1.v1','workload_id':'P249_P64_INFORMATION_ABLATION_R1','parent':'P249','claim':'Test whether P249 P64 needs both frozen 6-month momentum and 200-day trend information, or whether one information component is a cleaner development-only challenger while small-value, P36, weights, universes, costs, and chronology remain frozen.','contract':{'incumbent_features':['6m_momentum','200d_trend'],'ablations':['6m_momentum_only','200d_trend_only'],'p64_cross_topk':2,'p64_industry_topk':3,'turnover_cost_bp':50,'p249_weights':'equal thirds SMALL_VALUE/P64/P36','sample_end':'2026-08-31','promotion_rule':'ablation must exceed incumbent annualized mean matched excess, retain >= incumbent positive-block count, and be positive in >=2/3 equal-count chronology blocks','no_feature_threshold_lookback_topk_universe_weight_cost_date_or_block_search':True},'variants':res,'best_ablation':best,'decision':decision,'scientific_consequence':'If an ablation wins, treat it only as a development challenger to the frozen P249 incumbent; protected forward evidence remains untouched. If neither wins, preserve the incumbent P64 information set and switch improvement modality rather than tuning these features.','boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':decision,'best_ablation':best,'variants':{k:{'candidate_cagr_pct':round(v['candidate_cagr']*100,3),'control_cagr_pct':round(v['matched_control_cagr']*100,3),'excess_pp':round(v['annualized_mean_matched_excess']*100,3),'positive_blocks':v['positive_blocks'],'delta_vs_incumbent_pp':round(v['excess_delta_vs_incumbent_pp'],3)} for k,v in res.items()}},sort_keys=True))
