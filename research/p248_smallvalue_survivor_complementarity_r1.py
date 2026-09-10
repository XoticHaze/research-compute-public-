from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

START='2005-01-01'; P64_BP=50; P36_BP=50; SV_BP=10
CROSS=('SPY','QQQ','TLT','GLD','DBC')
IND=('SOXX','XBI','XHB','KRE','ITA','IGV','IYT','XRT','XOP','IHI')
ALL=tuple(dict.fromkeys((*CROSS,*IND,'AVUV','AVDV','IJR','VSS')))
WINDOWS={'2020':'2020-01-01','2022':'2022-01-01'}

def metrics(r):
    q=pd.Series(r,dtype=float).dropna(); e=(1+q).cumprod(); n=len(q); ann=float(q.mean()*12); vol=float(q.std(ddof=1)*math.sqrt(12));
    return {'months':int(n),'cagr':float(e.iloc[-1]**(12/n)-1),'maxdd':float((e/e.cummax()-1).min()),'sharpe_rf0':float(ann/vol) if vol else None}

def endpoint_cost(r,bps):
    q=pd.Series(r,dtype=float).dropna().copy(); f=bps/10000
    if len(q): q.iloc[0]-=f; q.iloc[-1]-=f
    return q

def rank_frame(close,symbols,topk):
    m=close[list(symbols)].resample('ME').last(); mom=m.pct_change(6); trend=(close[list(symbols)]/close[list(symbols)].rolling(200,min_periods=160).mean()-1).resample('ME').last(); prev={s:0.0 for s in symbols}; rec=[]
    for dt in m.index:
        b=pd.DataFrame({'mom6':mom.loc[dt,list(symbols)],'trend200':trend.loc[dt,list(symbols)]},index=list(symbols))
        if b.isna().any().any(): continue
        score=b.rank(axis=0,pct=True,method='average').mean(axis=1); loc=m.index.get_loc(dt)
        if not isinstance(loc,(int,np.integer)) or loc+1>=len(m): continue
        nxt=m.index[loc+1]; rr=m.loc[nxt,list(symbols)]/m.loc[dt,list(symbols)]-1
        if rr.isna().any(): continue
        chosen=score.sort_values(ascending=False).head(topk).index; w={s:(1/topk if s in chosen else 0.0) for s in symbols}; to=.5*sum(abs(w[s]-prev[s]) for s in symbols)
        rec.append((nxt,sum(w[s]*float(rr[s]) for s in symbols),float(rr.mean()),to)); prev=w
    return pd.DataFrame(rec,columns=['date','gross','matched','turnover']).set_index('date')

def p64_frame(close):
    a=rank_frame(close,CROSS,2); b=rank_frame(close,IND,3); idx=a.index.intersection(b.index)
    return pd.DataFrame({'candidate':.5*(a.loc[idx].gross-a.loc[idx].turnover*P64_BP/10000)+.5*(b.loc[idx].gross-b.loc[idx].turnover*P64_BP/10000),'matched':.5*a.loc[idx].matched+.5*b.loc[idx].matched},index=idx)

def p36_frame(close):
    c=close[['SOXX','QQQ']].dropna().sort_index(); idx=c.index; m=c.resample('ME').last(); rel=m.SOXx.pct_change(6)-m.QQQ.pct_change(6) if 'SOXx' in m.columns else m.SOXx

def p36_exact(close):
    c=close[['SOXX','QQQ']].dropna().sort_index(); idx=c.index; m=c.resample('ME').last(); rel=m['SOXX'].pct_change(6)-m['QQQ'].pct_change(6); sig={pd.Timestamp(dt):(1.0 if rel.loc[dt]>0 else 0.0) for dt in m.index if pd.notna(rel.loc[dt])}; labels=list(sig); prev=None; rec=[]
    for i in range(len(labels)-1):
        dt,nxt=labels[i],labels[i+1]; a0=idx.get_indexer([dt],method='pad')[0]+1; z0=idx.get_indexer([nxt],method='pad')[0]+1
        if a0<0 or z0<0 or z0>=len(idx): continue
        w=sig[dt]; ar=float(c.iloc[z0].SOXX/c.iloc[a0].SOXX-1); qr=float(c.iloc[z0].QQQ/c.iloc[a0].QQQ-1); turn=1.0 if prev is None else abs(w-prev); rec.append((idx[z0],w*ar+(1-w)*qr-turn*P36_BP/10000,.5*ar+.5*qr)); prev=w
    z=pd.DataFrame(rec,columns=['date','candidate','matched']).set_index('date'); z.index=z.index.to_period('M').to_timestamp('M'); return z

def folds(c,b,extra_bps=0):
    out=[]
    for i,ix in enumerate(np.array_split(np.arange(len(c)),5),1):
        cc=endpoint_cost(c.iloc[ix],extra_bps); bb=endpoint_cost(b.iloc[ix],extra_bps); out.append({'fold':i,'excess_cagr':metrics(cc)['cagr']-metrics(bb)['cagr']})
    return out

def compare(sv,svm,other,name):
    x=sv.to_frame('sv').join(svm.rename('svm')).join(other.rename(columns={'candidate':'other','matched':'otherm'}),how='inner').dropna(); rows={}
    for wn,start in WINDOWS.items():
        q=x.loc[x.index>=pd.Timestamp(start)].copy(); svnet=endpoint_cost(q.sv,SV_BP); svmnet=endpoint_cost(q.svm,SV_BP); blend=.5*q.sv+.5*q.other; blendm=.5*q.svm+.5*q.otherm; blend=endpoint_cost(blend,SV_BP/2); blendm=endpoint_cost(blendm,SV_BP/2); ex1=q.sv-q.svm; ex2=q.other-q.otherm; fs=folds(.5*q.sv+.5*q.other,.5*q.svm+.5*q.otherm,SV_BP/2)
        sp=close_month['SPY'].pct_change().reindex(q.index); qq=close_month['QQQ'].pct_change().reindex(q.index)
        rows[wn]={'months':len(q),'smallvalue':metrics(svnet),'other':metrics(q.other),'fixed_50_50_blend':metrics(blend),'matched_blend':metrics(blendm),'blend_excess_cagr':metrics(blend)['cagr']-metrics(blendm)['cagr'],'excess_return_corr':float(ex1.corr(ex2)),'positive_matched_folds':sum(z['excess_cagr']>0 for z in fs),'folds':fs,'blend_vs_spy_cagr':metrics(blend)['cagr']-metrics(endpoint_cost(sp,SV_BP/2))['cagr'],'blend_vs_qqq_cagr':metrics(blend)['cagr']-metrics(endpoint_cost(qq,SV_BP/2))['cagr']}
    a=rows['2020']; b=rows['2022']; ok=abs(a['excess_return_corr'])<=.5 and a['blend_excess_cagr']>0 and b['blend_excess_cagr']>0 and a['positive_matched_folds']>=3
    return {'comparator':name,'tests':rows,'complementarity_supported':bool(ok)}

raw=yf.download(list(ALL),start=START,end='2026-09-03',auto_adjust=True,progress=False,threads=False); close=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw; close=close.dropna(how='all').astype(float); close_month=close.resample('ME').last()
p64=p64_frame(close); p36=p36_exact(close); a=p64.copy(); a.index=a.index.to_period('M').to_timestamp('M'); p82=a.join(p36,lsuffix='_p64',rsuffix='_p36',how='inner'); p82=pd.DataFrame({'candidate':.5*p82.candidate_p64+.5*p82.candidate_p36,'matched':.5*p82.matched_p64+.5*p82.matched_p36},index=p82.index)
svm=close_month[['AVUV','AVDV','IJR','VSS']].pct_change().dropna(); sv=.5*svm.AVUV+.5*svm.AVDV; svctrl=.5*svm.IJR+.5*svm.VSS
comparisons={'P64':compare(sv,svctrl,p64,'P64'),'P36':compare(sv,svctrl,p36,'P36'),'P82_FIXED_BLEND':compare(sv,svctrl,p82,'P82_FIXED_BLEND')}
out={'schema':'research.p248_smallvalue_survivor_complementarity_r1','parent':'P239/P240/P241/P242/P243/P245','claim':'The fixed AVUV/AVDV small-value survivor contributes orthogonal matched excess when paired 50/50 with established P64/P36/P82 research survivors without optimizing weights.','contract':{'smallvalue_weights':{'AVUV':.5,'AVDV':.5},'smallvalue_matched':{'IJR':.5,'VSS':.5},'smallvalue_endpoint_cost_bps':SV_BP,'survivor_costs_preserved':{'P64_bps':P64_BP,'P36_bps':P36_BP},'blend_weight':[.5,.5],'windows':WINDOWS,'complementarity_gate':'abs excess-return correlation <=0.5; positive fixed-blend matched excess in 2020+ and 2022+; >=3/5 positive matched folds in 2020+','opportunity_controls':['SPY','QQQ'],'no_weight_window_fund_or_parameter_search':True},'comparisons':comparisons,'decision':'P248_COMPLEMENTARITY_SUPPORTED' if any(v['complementarity_supported'] for v in comparisons.values()) else 'P248_COMPLEMENTARITY_NOT_SUPPORTED','limitations':['common history begins with AVUV/AVDV availability','Yahoo adjusted prices are research-only','fixed 50/50 blend is a scientific discriminator, not portfolio allocation authority'],'boundaries':{'portfolio_ranking':False,'allocation_authority':False,'live_trading':False}}
Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p248_smallvalue_survivor_complementarity_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))