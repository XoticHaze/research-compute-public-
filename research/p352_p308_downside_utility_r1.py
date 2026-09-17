from __future__ import annotations
import json, importlib.util
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

P248_PATH=Path(__file__).with_name('p248_smallvalue_survivor_complementarity_r1.py')
if not P248_PATH.is_file(): raise RuntimeError('requires admitted P248 source owner')
spec=importlib.util.spec_from_file_location('p248_owner',P248_PATH); p248=importlib.util.module_from_spec(spec); spec.loader.exec_module(p248)
SYMS=['SPMO','SPY','IJS','IJR']; COST_BP=25; SV_BP=10; END='2026-09-10'
raw=yf.download(SYMS,start='2015-01-01',end=END,auto_adjust=True,progress=False,threads=False)
px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[SYMS].dropna(); m=px.resample('ME').last().pct_change().dropna()
gross=.5*m.SPMO+.5*m.IJS; drift=.5*(1+m.SPMO)/(1+gross); p308=gross-2*(drift-.5).abs()*(COST_BP/10000); p308m=.5*m.SPY+.5*m.IJR
svm=p248.close_month[['AVUV','AVDV','IJR','VSS']].pct_change().dropna(); sv=.5*svm.AVUV+.5*svm.AVDV; svmctrl=.5*svm.IJR+.5*svm.VSS
p64=p248.p64.copy(); p64.index=p64.index.to_period('M').to_timestamp('M'); p36=p248.p36.copy(); p36.index=p36.index.to_period('M').to_timestamp('M')
x=sv.to_frame('sv').join(svmctrl.rename('svm')).join(p64.rename(columns={'candidate':'p64','matched':'p64m'})).join(p36.rename(columns={'candidate':'p36','matched':'p36m'})).join(p308.rename('p308')).join(p308m.rename('p308m')).dropna()
p249=(x.sv+x.p64+x.p36)/3; p249m=(x.svm+x.p64m+x.p36m)/3
# Frozen P249 small-value endpoint friction across the full common sample only.
if len(p249):
    p249.iloc[0]-=(SV_BP/3)/10000; p249.iloc[-1]-=(SV_BP/3)/10000
    p249m.iloc[0]-=(SV_BP/3)/10000; p249m.iloc[-1]-=(SV_BP/3)/10000
ex249=p249-p249m; ex308=x.p308-x.p308m
df=pd.DataFrame({'p249':p249,'p249m':p249m,'p308':x.p308,'p308m':x.p308m,'ex249':ex249,'ex308':ex308}).dropna()
WINDOWS={'2020_plus':'2020-01-01','2022_plus':'2022-01-01','2024_plus':'2024-01-01'}

def condition_stats(q,mask):
    z=q.loc[mask]
    return {'months':int(len(z)),'p249_mean_return':float(z.p249.mean()) if len(z) else None,'p308_mean_return':float(z.p308.mean()) if len(z) else None,'p308_mean_matched_excess':float(z.ex308.mean()) if len(z) else None,'p308_positive_excess_rate':float((z.ex308>0).mean()) if len(z) else None,'p308_minus_p249_mean_return':float((z.p308-z.p249).mean()) if len(z) else None}

out={}
for name,start in WINDOWS.items():
    q=df.loc[df.index>=pd.Timestamp(start)].copy()
    q25=float(q.p249.quantile(.25))
    wealth=(1+q.p249).cumprod(); dd=wealth/wealth.cummax()-1
    tests={
        'p249_negative_months':condition_stats(q,q.p249<0),
        'p249_worst_quartile_months':condition_stats(q,q.p249<=q25),
        'p249_drawdown_months':condition_stats(q,dd<0),
    }
    out[name]={'months':int(len(q)),'p249_worst_quartile_threshold':q25,'tests':tests,'overall_excess_corr':float(q.ex249.corr(q.ex308))}

# P308 earns downside-utility support only if it contributes positive matched excess
# in all three predeclared P249 stress sets in at least 2/3 windows, and beats P249
# on raw return in the negative and worst-quartile sets in at least 2/3 windows.
pos_excess_windows=0; raw_help_windows=0
for w,v in out.items():
    t=v['tests']
    if all(t[k]['p308_mean_matched_excess'] is not None and t[k]['p308_mean_matched_excess']>0 for k in t): pos_excess_windows+=1
    if t['p249_negative_months']['p308_minus_p249_mean_return']>0 and t['p249_worst_quartile_months']['p308_minus_p249_mean_return']>0: raw_help_windows+=1
support=pos_excess_windows>=2 and raw_help_windows>=2
decision='P352_P308_DOWNSIDE_COMPLEMENTARITY_SUPPORTED' if support else 'P352_P308_DOWNSIDE_COMPLEMENTARITY_NOT_CONFIRMED'
res={'schema':'research.p352_p308_downside_utility_r1','parent':'P308/FUND_MODEL_SURVIVOR_TOURNAMENT','claim':'Orthogonal adjudicator for P308 after the fixed survivor tournament: test whether its low-correlated matched-excess stream actually helps in P249-negative, P249 worst-quartile, and P249 drawdown months. No blend weights, allocation/ranking, products, thresholds, lookbacks or window search.','contract':{'P249':'frozen equal-third small-value/P64/P36','P308':'frozen 50/50 SPMO+IJS with 25bp rebalance friction','conditions':['P249 return < 0','P249 return <= within-window 25th percentile','P249 in drawdown'],'windows':WINDOWS,'gate':'P308 positive matched excess in all three stress sets in >=2/3 windows AND P308 raw return exceeds P249 in negative and worst-quartile sets in >=2/3 windows','no_optimization':True},'results':out,'gate_counts':{'positive_excess_all_stress_sets_windows':pos_excess_windows,'raw_downside_help_windows':raw_help_windows},'decision':decision,'scientific_consequence':'A pass supports P308 as a conditional complementary return source without granting capital allocation authority. A failure preserves P308 standalone evidence but rejects the stronger downside-utility claim; do not parameter rescue.','limitations':['same adjusted-price provider as tournament','common history constrained by AVUV/AVDV','conditional utility evidence is not portfolio allocation/ranking authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p352_p308_downside_utility_r1.json').write_text(json.dumps(res,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(res,sort_keys=True))
