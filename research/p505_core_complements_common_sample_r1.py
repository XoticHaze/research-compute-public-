from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

OUT = Path('research/artifacts/p505_core_complements_common_sample_r1.json')
OUT.parent.mkdir(parents=True, exist_ok=True)

CROSS=('SPY','QQQ','TLT','GLD','DBC')
IND=('SOXX','XBI','XHB','KRE','ITA','IGV','IYT','XRT','XOP','IHI')
IND2=('XAR','XBI','XHB','XME','XOP','XPH','XRT','XSD','XSW','XTN','KRE')
EXTRA=('AVUV','AVDV','IJR','VSS','HYG','SHY','SRLN','JAAA','SGOV','EFA','IDMO')
T=list(dict.fromkeys((*CROSS,*IND,*IND2,*EXTRA)))
P64BP=50; P36BP=50; SVBP=10; INDBP=25; COMPLEMENT_ENDPOINT_BP=25

raw=yf.download(T,start='2005-01-01',end='2026-09-11',auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw).dropna(how='all').astype(float)
m=c.resample('ME').last(); r=m.pct_change(fill_method=None)

def stats(s):
    q=pd.Series(s,dtype=float).dropna(); n=len(q)
    if not n: return {'months':0,'cagr':None,'sharpe':None,'max_drawdown':None}
    w=(1+q).cumprod(); vol=q.std(ddof=1)*math.sqrt(12)
    return {'months':int(n),'cagr':float(w.iloc[-1]**(12/n)-1),'sharpe':float(q.mean()*12/vol) if vol>0 else None,'max_drawdown':float((w/w.cummax()-1).min())}

def endpoint(s,bps):
    q=pd.Series(s,dtype=float).dropna().copy(); f=bps/10000
    if len(q): q.iloc[0]-=f; q.iloc[-1]-=f
    return q

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
p64=pd.DataFrame({'x':.5*(a.loc[ix].gross-a.loc[ix].turn*P64BP/10000)+.5*(b.loc[ix].gross-b.loc[ix].turn*P64BP/10000),'ctl':.5*a.loc[ix].matched+.5*b.loc[ix].matched},index=ix)
p64.index=p64.index.to_period('M').to_timestamp('M')

def p36():
    z=c[['SOXX','QQQ']].dropna(); idx=z.index; mm=z.resample('ME').last(); rel=mm['SOXX'].pct_change(6)-mm['QQQ'].pct_change(6)
    sig={dt:(1. if rel.loc[dt]>0 else 0.) for dt in mm.index if pd.notna(rel.loc[dt])}; labs=list(sig); prev=None; rows=[]
    for i in range(len(labs)-1):
        dt,nxt=labs[i],labs[i+1]; i0=idx.get_indexer([dt],method='pad')[0]+1; i1=idx.get_indexer([nxt],method='pad')[0]+1
        if i0<0 or i1<0 or i1>=len(idx): continue
        w=sig[dt]; ar=float(z.iloc[i1].SOXX/z.iloc[i0].SOXX-1); qr=float(z.iloc[i1].QQQ/z.iloc[i0].QQQ-1)
        to=1. if prev is None else abs(w-prev); rows.append((idx[i1],w*ar+(1-w)*qr-to*P36BP/10000,.5*(ar+qr))); prev=w
    q=pd.DataFrame(rows,columns=['date','x','ctl']).set_index('date'); q.index=q.index.to_period('M').to_timestamp('M'); return q

p36x=p36(); svr=m[['AVUV','AVDV','IJR','VSS']].pct_change(fill_method=None)
sv=.5*(svr.AVUV+svr.AVDV); svctl=.5*(svr.IJR+svr.VSS)
base=sv.to_frame('sv').join(svctl.rename('svctl')).join(p64.rename(columns={'x':'p64','ctl':'p64ctl'})).join(p36x.rename(columns={'x':'p36','ctl':'p36ctl'})).dropna()
p249=pd.DataFrame({'x':(base.sv+base.p64+base.p36)/3,'ctl':(base.svctl+base.p64ctl+base.p36ctl)/3},index=base.index)

def industry():
    mm=m[list(IND2)].dropna(); ret=mm.pct_change(); score=mm.shift(1)/mm.shift(12)-1; w=pd.DataFrame(0.,index=mm.index,columns=IND2)
    for dt,row in score.iterrows():
        if row.notna().sum()==len(IND2): w.loc[dt,row.nlargest(3).index]=1/3
    gross=(w*ret).sum(axis=1); turn=.5*w.diff().abs().sum(axis=1); active=w.sum(axis=1)>0
    if active.any(): turn.loc[active.idxmax()]=1.
    cand=gross-turn*INDBP/10000; ctl=ret.mean(axis=1).copy()
    if active.any(): ctl.loc[active.idxmax()]-=INDBP/10000
    return pd.DataFrame({'x':cand,'ctl':ctl})

ind=industry(); p272base=base.join(ind.rename(columns={'x':'ind','ctl':'indctl'})).dropna()
p272=pd.DataFrame({'x':(p272base.sv+p272base.p64+p272base.p36+p272base.ind)/4,'ctl':(p272base.svctl+p272base.p64ctl+p272base.p36ctl+p272base.indctl)/4},index=p272base.index)

# Existing causal SRLN control: rolling 24-month nonnegative HYG/SHY replication estimated only from prior data.
loan_rows=[]
rr=m[['SRLN','HYG','SHY']].pct_change(fill_method=None)
for i in range(len(rr)):
    hist=rr[['SRLN','HYG','SHY']].iloc[max(0,i-24):i].dropna()
    if len(hist)<24: loan_rows.append((np.nan,np.nan)); continue
    beta=np.linalg.lstsq(hist[['HYG','SHY']].values,hist.SRLN.values,rcond=None)[0]; beta=np.clip(beta,0,1)
    if beta.sum()>1: beta=beta/beta.sum()
    loan_rows.append(tuple(map(float,beta)))
loan_w=pd.DataFrame(loan_rows,index=rr.index,columns=['hyg','shy']).shift(1)
loan_ctl=loan_w.hyg*rr.HYG+loan_w.shy*rr.SHY

intl=.5*(r.AVDV+r.IDMO); intl_ctl=.5*(r.VSS+r.EFA)
q=p249.rename(columns={'x':'p249','ctl':'p249ctl'}).join(p272.rename(columns={'x':'core','ctl':'corectl'})).join(r.SRLN.rename('loan')).join(loan_ctl.rename('loanctl')).join(r.JAAA.rename('clo')).join(r.SGOV.rename('cloctl')).join(intl.rename('intl')).join(intl_ctl.rename('intlctl')).join(r.SPY.rename('spy')).dropna()
q=q.loc['2021-01-01':]
idx=q.index; periods=idx.to_period('M').astype(int); contiguous=bool(len(idx)>1 and np.all(np.diff(periods)==1)); n=len(q)
sizes=[n//3,n//3,n-2*(n//3)] if n else [0,0,0]
eligible=n>=54 and contiguous and min(sizes)>=18
if not eligible:
    out={'schema':'research.p505_core_complements_common_sample_r1.v1','workload_id':'P505_CORE_COMPLEMENTS_COMMON_SAMPLE_R1','decision':'COMMON_SAMPLE_COVERAGE_NOT_READY','coverage':{'start':str(idx.min().date()) if n else None,'end':str(idx.max().date()) if n else None,'months':n,'contiguous':contiguous,'block_sizes':sizes},'predeclared_minimum':{'months':54,'block_months':18},'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
    OUT.write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True)); raise SystemExit(0)

# Prospectively frozen diagnostics. Each single complement receives a fixed 25% capital dose.
# Joint complement uses 50% unchanged P249+P266 core and equal 1/6 capital to P373, AAA CLO, and AVDV+IDMO.
def series_for(z):
    raw_series={
      'P249':z.p249,
      'P249_P266_CORE':z.core,
      'CORE_PLUS_P373':.75*z.core+.25*z.loan,
      'CORE_PLUS_AAA':.75*z.core+.25*z.clo,
      'CORE_PLUS_AVDV_IDMO':.75*z.core+.25*z.intl,
      'CORE_PLUS_JOINT':.50*z.core+(z.loan+z.clo+z.intl)/6,
    }
    raw_ctl={
      'P249':z.p249ctl,
      'P249_P266_CORE':z.corectl,
      'CORE_PLUS_P373':.75*z.corectl+.25*z.loanctl,
      'CORE_PLUS_AAA':.75*z.corectl+.25*z.cloctl,
      'CORE_PLUS_AVDV_IDMO':.75*z.corectl+.25*z.intlctl,
      'CORE_PLUS_JOINT':.50*z.corectl+(z.loanctl+z.cloctl+z.intlctl)/6,
    }
    out={}
    for k,s in raw_series.items():
        cost=(SVBP/4 if k=='P249_P266_CORE' else (SVBP/3 if k=='P249' else COMPLEMENT_ENDPOINT_BP))
        ss=endpoint(s,cost); cc=endpoint(raw_ctl[k],cost); sm=stats(ss); cm=stats(cc)
        out[k]={**sm,'matched_control_cagr':cm['cagr'],'matched_excess_cagr':sm['cagr']-cm['cagr'],'vs_core_cagr':sm['cagr']-stats(endpoint(z.core,SVBP/4))['cagr'],'vs_p249_cagr':sm['cagr']-stats(endpoint(z.p249,SVBP/3))['cagr']}
    ret=pd.DataFrame({k:endpoint(s,(SVBP/4 if k=='P249_P266_CORE' else (SVBP/3 if k=='P249' else COMPLEMENT_ENDPOINT_BP))) for k,s in raw_series.items()}).dropna()
    out['correlation']=ret.corr().to_dict()
    core_ret=ret['P249_P266_CORE']
    for k in ['CORE_PLUS_P373','CORE_PLUS_AAA','CORE_PLUS_AVDV_IDMO','CORE_PLUS_JOINT']:
        resid=ret[k]-core_ret
        out[k]['incremental_residual_mean_ann']=float(resid.mean()*12)
        out[k]['incremental_residual_vol_ann']=float(resid.std(ddof=1)*math.sqrt(12))
    return out

full=series_for(q); blocks={}; off=0
for i,sz in enumerate(sizes,1):
    zz=q.iloc[off:off+sz]; off+=sz; blocks[f'block_{i}']=series_for(zz)

roles={}
for k in ['CORE_PLUS_P373','CORE_PLUS_AAA','CORE_PLUS_AVDV_IDMO','CORE_PLUS_JOINT']:
    f=full[k]; pos=sum(blocks[b][k]['matched_excess_cagr']>0 for b in blocks); corewins=sum(blocks[b][k]['vs_core_cagr']>0 for b in blocks)
    if f['matched_excess_cagr']>0 and f['vs_core_cagr']>0 and pos>=2 and corewins>=2:
        role='ADDITIVE_RETURN_ENHANCER'
    elif f['matched_excess_cagr']>0 and f['max_drawdown']>full['P249_P266_CORE']['max_drawdown'] and pos>=2:
        role='ADDITIVE_RISK_SHAPER'
    elif f['matched_excess_cagr']<=0 and f['vs_core_cagr']<=0 and f['sharpe']<=full['P249_P266_CORE']['sharpe']:
        role='DOMINATED_ON_COMMON_SAMPLE'
    else:
        role='NEEDS_CONFIRMATION'
    roles[k]={'role':role,'positive_matched_excess_blocks':pos,'positive_vs_core_blocks':corewins}

decision='CURRENT_CORE_COMPLEMENT_ROLES_ADJUDICATED'
out={'schema':'research.p505_core_complements_common_sample_r1.v1','workload_id':'P505_CORE_COMPLEMENTS_COMMON_SAMPLE_R1','parent':'FUND_MODEL_SURVIVOR_PORTFOLIO_ALLOCATION_SCIENTIFIC_INPUT','claim':'Prospectively fixed common-sample opportunity-cost test of current P502 P249 and P249+P266 identities against P373/SRLN, AAA CLO/JAAA, and AVDV+IDMO complements. No legacy P249 alias, weight search, date rescue, product substitution, regime search, control substitution, or cost rescue.','identity':{'P249':'equal-third AVUV/AVDV small-value sleeve + P64 + P36 from P502','P249_P266_CORE':'equal-quarter P272 = AVUV/AVDV small-value sleeve + P64 + P36 + fixed P266 12-1 top-3 industry momentum','P373':'SRLN with causal prior-24-month HYG/SHY control','AAA':'JAAA vs SGOV','AVDV_IDMO':'50/50 AVDV+IDMO vs 50/50 VSS+EFA'},'frozen_diagnostic_weights':{'single_complement':'75% P249+P266 core + 25% named complement','joint':'50% P249+P266 core + 1/6 P373 + 1/6 AAA + 1/6 AVDV+IDMO'},'coverage':{'start':str(idx.min().date()),'end':str(idx.max().date()),'months':n,'contiguous':contiguous,'block_sizes':sizes},'full_sample':full,'chronology':blocks,'scientific_portfolio_roles':roles,'decision':decision,'decision_rule':'Single complements qualify as additive return enhancers only with positive full-sample matched excess, positive incremental CAGR versus current P249+P266 core, and >=2/3 positive matched-excess and versus-core chronology blocks. A complement may instead qualify as a risk shaper if matched excess is positive, max drawdown improves versus core, and >=2/3 matched-excess blocks are positive. Otherwise classify dominated or needs confirmation; no allocation decision is made here.','forbidden':['weight optimization','date/window rescue','product substitution','regime threshold search','control substitution','cost rescue','legacy P249 alias'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':decision,'coverage':out['coverage'],'core':{k:round(full['P249_P266_CORE'][k],4) if full['P249_P266_CORE'][k] is not None else None for k in ['cagr','matched_excess_cagr','sharpe','max_drawdown']},'roles':roles,'complements':{k:{m:round(full[k][m],4) if full[k][m] is not None else None for m in ['cagr','matched_excess_cagr','vs_core_cagr','sharpe','max_drawdown']} for k in roles}},sort_keys=True))
