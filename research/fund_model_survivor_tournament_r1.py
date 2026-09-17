from __future__ import annotations
import json, math, importlib.util
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

P248_PATH=Path(__file__).with_name('p248_smallvalue_survivor_complementarity_r1.py')
if not P248_PATH.is_file():
    raise RuntimeError('requires admitted P248 source owner')
spec=importlib.util.spec_from_file_location('p248_owner',P248_PATH)
p248=importlib.util.module_from_spec(spec); spec.loader.exec_module(p248)

INDUSTRIES=['XAR','XBI','XHB','XME','XOP','XPH','XRT','XSD','XSW','XTN','KRE']
MOM_SYMS=['SPMO','SPY','IJS','IJR']
START='2010-01-01'; END='2026-09-10'
IND_COST_BP=50; MOM_COST_BP=25; SV_BP=10
WINDOWS={'2020_plus':'2020-01-01','2022_plus':'2022-01-01','2024_plus':'2024-01-01'}


def metrics(r):
    q=pd.Series(r,dtype=float).dropna(); e=(1+q).cumprod(); n=len(q)
    ann=float(q.mean()*12); vol=float(q.std(ddof=1)*math.sqrt(12)) if n>1 else 0.0
    return {'months':int(n),'cagr':float(e.iloc[-1]**(12/n)-1),'maxdd':float((e/e.cummax()-1).min()),'sharpe_rf0':float(ann/vol) if vol else None,'worst_rolling_12m':float(((1+q).rolling(12).apply(np.prod,raw=True)-1).min()) if n>=12 else None}


def endpoint_cost(r,bps):
    q=pd.Series(r,dtype=float).dropna().copy(); f=bps/10000
    if len(q): q.iloc[0]-=f; q.iloc[-1]-=f
    return q


def industry_sleeve():
    raw=yf.download(INDUSTRIES,start=START,end=END,auto_adjust=True,progress=False,threads=False)
    close=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[INDUSTRIES].dropna()
    m=close.resample('ME').last(); ret=m.pct_change(); score=m.shift(1)/m.shift(12)-1
    w=pd.DataFrame(0.0,index=m.index,columns=INDUSTRIES)
    for dt,row in score.iterrows():
        if row.notna().sum()==len(INDUSTRIES): w.loc[dt,row.nlargest(3).index]=1/3
    gross=(w*ret).sum(axis=1); turn=.5*w.diff().abs().sum(axis=1); active=w.sum(axis=1).gt(0)
    if active.any(): turn.loc[active.idxmax()]=1.0
    cand=gross-(IND_COST_BP/10000)*turn
    matched=ret.mean(axis=1).copy()
    if active.any(): matched.loc[active.idxmax()]-=IND_COST_BP/10000
    return pd.DataFrame({'ind':cand,'indm':matched})


def p308_sleeve():
    raw=yf.download(MOM_SYMS,start='2015-01-01',end=END,auto_adjust=True,progress=False,threads=False)
    close=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[MOM_SYMS].dropna()
    m=close.resample('ME').last().pct_change().dropna()
    gross=.5*m.SPMO+.5*m.IJS
    drift=.5*(1+m.SPMO)/(1+gross)
    turnover=2*(drift-.5).abs()
    cand=gross-turnover*(MOM_COST_BP/10000)
    matched=.5*m.SPY+.5*m.IJR
    return pd.DataFrame({'p308':cand,'p308m':matched})

svm=p248.close_month[['AVUV','AVDV','IJR','VSS']].pct_change().dropna()
sv=.5*svm.AVUV+.5*svm.AVDV; svctrl=.5*svm.IJR+.5*svm.VSS
p64=p248.p64.copy(); p64.index=p64.index.to_period('M').to_timestamp('M')
p36=p248.p36.copy(); p36.index=p36.index.to_period('M').to_timestamp('M')
ind=industry_sleeve(); ind.index=ind.index.to_period('M').to_timestamp('M')
p308=p308_sleeve(); p308.index=p308.index.to_period('M').to_timestamp('M')

x=sv.to_frame('sv').join(svctrl.rename('svm')).join(p64.rename(columns={'candidate':'p64','matched':'p64m'})).join(p36.rename(columns={'candidate':'p36','matched':'p36m'})).join(ind).join(p308).dropna()
core=(x.sv+x.p64+x.p36)/3
corem=(x.svm+x.p64m+x.p36m)/3
sat=(x.sv+x.p64+x.p36+x.ind)/4
satm=(x.svm+x.p64m+x.p36m+x.indm)/4
# Preserve the already-frozen P249 endpoint small-value friction convention.
core=endpoint_cost(core,SV_BP/3); corem=endpoint_cost(corem,SV_BP/3)
sat=endpoint_cost(sat,SV_BP/4); satm=endpoint_cost(satm,SV_BP/4)
p308c=x.p308.copy(); p308m=x.p308m.copy()

streams=pd.DataFrame({'P249':core,'P249_P266':sat,'P308':p308c,'P249_m':corem,'P249_P266_m':satm,'P308_m':p308m}).dropna()
streams['P249_excess']=streams.P249-streams.P249_m
streams['P249_P266_excess']=streams.P249_P266-streams.P249_P266_m
streams['P308_excess']=streams.P308-streams.P308_m

def downside_overlap(a,b):
    z=pd.DataFrame({'a':a,'b':b}).dropna(); d=z[(z.a<0)|(z.b<0)]
    return {'months':int(len(d)),'both_negative_rate':float(((d.a<0)&(d.b<0)).mean()) if len(d) else None,'downside_corr':float(d.a.corr(d.b)) if len(d)>2 else None}

out_windows={}
for name,start in WINDOWS.items():
    q=streams.loc[streams.index>=pd.Timestamp(start)]
    row={}
    for k,mk in [('P249','P249_m'),('P249_P266','P249_P266_m'),('P308','P308_m')]:
        s=metrics(q[k]); b=metrics(q[mk]); row[k]={'candidate':s,'matched':b,'matched_excess_cagr':s['cagr']-b['cagr']}
    row['pairwise_return_corr']=q[['P249','P249_P266','P308']].corr().to_dict()
    row['pairwise_excess_corr']=q[['P249_excess','P249_P266_excess','P308_excess']].corr().to_dict()
    row['downside_overlap']={'P249_vs_P249_P266':downside_overlap(q.P249,q.P249_P266),'P249_vs_P308':downside_overlap(q.P249,q.P308),'P249_P266_vs_P308':downside_overlap(q.P249_P266,q.P308)}
    row['incremental']={
        'P266_vs_P249':{'cagr_delta':row['P249_P266']['candidate']['cagr']-row['P249']['candidate']['cagr'],'sharpe_delta':row['P249_P266']['candidate']['sharpe_rf0']-row['P249']['candidate']['sharpe_rf0'],'maxdd_delta':row['P249_P266']['candidate']['maxdd']-row['P249']['candidate']['maxdd'],'matched_excess_delta':row['P249_P266']['matched_excess_cagr']-row['P249']['matched_excess_cagr']},
        'P308_vs_P249':{'cagr_delta':row['P308']['candidate']['cagr']-row['P249']['candidate']['cagr'],'sharpe_delta':row['P308']['candidate']['sharpe_rf0']-row['P249']['candidate']['sharpe_rf0'],'maxdd_delta':row['P308']['candidate']['maxdd']-row['P249']['candidate']['maxdd'],'matched_excess_delta':row['P308']['matched_excess_cagr']-row['P249']['matched_excess_cagr']}}
    out_windows[name]=row

folds=[]
for i,ix in enumerate(np.array_split(np.arange(len(streams)),5),1):
    q=streams.iloc[ix]
    folds.append({'fold':i,'P249_excess_cagr':metrics(q.P249)['cagr']-metrics(q.P249_m)['cagr'],'P249_P266_excess_cagr':metrics(q.P249_P266)['cagr']-metrics(q.P249_P266_m)['cagr'],'P308_excess_cagr':metrics(q.P308)['cagr']-metrics(q.P308_m)['cagr'],'P266_minus_P249_cagr':metrics(q.P249_P266)['cagr']-metrics(q.P249)['cagr'],'P308_minus_P249_cagr':metrics(q.P308)['cagr']-metrics(q.P249)['cagr']})

p266_positive=sum(out_windows[w]['incremental']['P266_vs_P249']['cagr_delta']>0 for w in WINDOWS)
p266_risk=sum(out_windows[w]['incremental']['P266_vs_P249']['maxdd_delta']>=0 and out_windows[w]['incremental']['P266_vs_P249']['sharpe_delta']>=0 for w in WINDOWS)
p308_positive=sum(out_windows[w]['incremental']['P308_vs_P249']['cagr_delta']>0 for w in WINDOWS)
p308_alpha=sum(out_windows[w]['incremental']['P308_vs_P249']['matched_excess_delta']>0 for w in WINDOWS)
p308_excess_corr=float(streams[['P249_excess','P308_excess']].corr().iloc[0,1])

if p308_positive>=2 and p308_alpha>=2:
    p308_role='P308_SCIENTIFIC_RETURN_ADVANTAGE_OVER_P249'
elif abs(p308_excess_corr)<0.40 and sum(out_windows[w]['downside_overlap']['P249_vs_P308']['downside_corr'] is not None and abs(out_windows[w]['downside_overlap']['P249_vs_P308']['downside_corr'])<0.60 for w in WINDOWS)>=2:
    p308_role='P308_DISTINCT_COMPLEMENTARY_RETURN_SOURCE'
else:
    p308_role='P308_REDUNDANT_OR_INFERIOR_TO_P249_ON_FIXED_TEST'

p266_role='P266_INCREMENTAL_CAPITAL_UTILITY_SUPPORTED' if p266_positive>=2 and p266_risk>=2 else 'P266_INCREMENTAL_UTILITY_NOT_CONFIRMED'

res={'schema':'research.fund_model_survivor_tournament_r1','parent':'FUND_MODEL_SURVIVOR_TOURNAMENT','claim':'Fixed common-sample scientific tournament among P249 core, frozen P249+P266 satellite construction, and P308 SPMO+IJS representative. No weights, regimes, thresholds, lookbacks, top-k, products or windows are searched.','participants':{'P249':'equal-third small-value/P64/P36','P249_P266':'equal-quarter small-value/P64/P36/P266 with P266 at 50bp one-way turnover','P308':'fixed 50/50 SPMO+IJS at 25bp rebalance friction'},'windows':WINDOWS,'common_sample':{'start':str(streams.index.min().date()),'end':str(streams.index.max().date()),'months':int(len(streams))},'results':out_windows,'chronology_folds':folds,'overall_pairwise_return_corr':streams[['P249','P249_P266','P308']].corr().to_dict(),'overall_pairwise_excess_corr':streams[['P249_excess','P249_P266_excess','P308_excess']].corr().to_dict(),'scientific_roles':{'P266':p266_role,'P308':p308_role},'decision':'TOURNAMENT_COMPLETE__'+p266_role+'__'+p308_role,'limitations':['scientific capital-utility comparison only, not portfolio ranking or allocation authority','common sample constrained by AVUV/AVDV history','Yahoo adjusted-price research representation','no parameter or weight search'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True)
Path('research/artifacts/fund_model_survivor_tournament_r1.json').write_text(json.dumps(res,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps(res,sort_keys=True))
