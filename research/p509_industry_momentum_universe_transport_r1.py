from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
OUT=Path('research/artifacts/p509_industry_momentum_universe_transport_r1.json');OUT.parent.mkdir(parents=True,exist_ok=True)
U=['IAI','IAT','IBB','IHF','IHI','ITA','IYT','IYZ','IYW','IYE','IYF'];T=U+['SPY'];TOPK=3;COST_BP=25
WINDOWS={'2012':'2012-01-01','2015':'2015-01-01','2020':'2020-01-01','2022':'2022-01-01'}
raw=yf.download(T,start='2010-01-01',end='2026-09-11',auto_adjust=True,progress=False,threads=False)
c=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[T].dropna(how='all');m=c.resample('ME').last();ret=m[U].pct_change(fill_method=None);score=m[U].shift(1)/m[U].shift(12)-1
w=pd.DataFrame(0.,index=m.index,columns=U)
for dt,row in score.iterrows():
    if row.notna().sum()==len(U):w.loc[dt,row.nlargest(TOPK).index]=1/TOPK
gross=(w*ret).sum(axis=1);turn=.5*w.diff().abs().sum(axis=1);active=w.sum(axis=1)>0
if active.any():turn.loc[active.idxmax()]=1.
cand=gross-turn*COST_BP/10000;ctl=ret.mean(axis=1).copy()
if active.any():ctl.loc[active.idxmax()]-=COST_BP/10000
spy=m.SPY.pct_change(fill_method=None)
def stat(q):
 q=pd.Series(q,dtype=float).dropna();e=(1+q).cumprod();n=len(q);vol=q.std(ddof=1)*math.sqrt(12)
 return {'months':int(n),'cagr':float(e.iloc[-1]**(12/n)-1),'max_drawdown':float((e/e.cummax()-1).min()),'sharpe':float(q.mean()*12/vol) if vol>0 else None}
outw={}
for name,start in WINDOWS.items():
 ix=(m.index>=pd.Timestamp(start))&active;a=cand.loc[ix];b=ctl.loc[ix];s=spy.loc[ix].copy()
 if len(s):s.iloc[0]-=COST_BP/10000
 am,bm,sm=stat(a),stat(b),stat(s);loc=np.flatnonzero(ix);folds=[]
 for i,sub in enumerate(np.array_split(loc,5),1):folds.append({'fold':i,'matched_excess_cagr':stat(cand.iloc[sub])['cagr']-stat(ctl.iloc[sub])['cagr']})
 outw[name]={'candidate':am,'matched_equalweight':bm,'spy':sm,'matched_excess_cagr':am['cagr']-bm['cagr'],'vs_spy_cagr':am['cagr']-sm['cagr'],'positive_matched_folds':sum(x['matched_excess_cagr']>0 for x in folds),'folds':folds,'avg_monthly_turnover':float(turn.loc[ix].mean())}
support=all(outw[x]['matched_excess_cagr']>0 for x in WINDOWS) and outw['2012']['positive_matched_folds']>=4 and outw['2012']['candidate']['max_drawdown']>=outw['2012']['matched_equalweight']['max_drawdown']-.05
decision='P266_UNIVERSE_TRANSPORT_SUPPORTED' if support else 'P266_UNIVERSE_TRANSPORT_NOT_SUPPORTED'
out={'schema':'research.p509_industry_momentum_universe_transport_r1.v1','workload_id':'P509_INDUSTRY_MOMENTUM_UNIVERSE_TRANSPORT_R1','parent':'P266','claim':'Orthogonal universe-dependence adjudicator for the supported P266 mechanism. Hold the 12-1 month-end signal, top-3 equal-weight next-month holding, 25bp one-way turnover cost, same-universe equal-weight control, fixed windows and five chronology folds constant while replacing the original SPDR industry ETF universe with a prospectively fixed independent iShares industry/sub-sector representation. No universe search or rescue after result.','contract':{'transport_universe':U,'signal':'12-1 month-end momentum using information through prior month','top_k':TOPK,'cost_bps_per_one_way_turnover':COST_BP,'matched_control':'same transport-universe equal weight','opportunity_control':'SPY','windows':WINDOWS,'support_rule':'positive matched excess all windows; >=4/5 positive 2012+ folds; maxDD no worse than matched by >5pp','no_universe_product_lookback_topk_window_cost_or_threshold_search':True},'tests':outw,'decision':decision,'scientific_consequence':'If supported, P266 gains independent universe-transport evidence. If unsupported, preserve the original P266 result but narrow it to its original ETF representation and do not tune the alternate universe or signal as rescue.','boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False));print(json.dumps({'decision':decision,'windows':{k:{'matched_excess_pp':round(v['matched_excess_cagr']*100,3),'vs_spy_pp':round(v['vs_spy_cagr']*100,3),'positive_folds':v['positive_matched_folds'],'maxdd':round(v['candidate']['max_drawdown']*100,2)} for k,v in outw.items()}},sort_keys=True))
