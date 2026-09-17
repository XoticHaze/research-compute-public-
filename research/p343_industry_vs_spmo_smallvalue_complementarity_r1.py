from __future__ import annotations
import json
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
SECTORS=['XLB','XLE','XLF','XLI','XLK','XLP','XLU','XLV','XLY']; ALL=SECTORS+['SPY','SPMO','IJS','IJR']; START='2015-01-01'; END='2026-09-10'; COST_BPS=25; TOP_K=3
raw=yf.download(ALL,start=START,end=END,auto_adjust=True,progress=False,threads=False); px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[ALL].dropna().resample('ME').last(); ret=px.pct_change(); score=px.shift(1)/px.shift(12)-1
rows=[]
for dt in ret.index:
 s=score.loc[dt,SECTORS].dropna(); rr=ret.loc[dt,SECTORS].dropna(); avail=s.index.intersection(rr.index)
 if len(avail)<TOP_K: continue
 top=s.loc[avail].nlargest(TOP_K).index; rows.append((dt,float(rr.loc[top].mean()),float(rr.loc[avail].mean()),tuple(top)))
sec=pd.DataFrame(rows,columns=['date','gross','matched','top']).set_index('date'); prev=set(); net=[]
for _,r in sec.iterrows():
 cur=set(r.top); turn=1.0 if not prev else 1.0-len(prev&cur)/TOP_K; net.append(r.gross-turn*COST_BPS/10000); prev=cur
sec['excess']=np.array(net)-sec.matched
m=ret[['SPMO','SPY','IJS','IJR']].dropna(); combo=.5*m.SPMO+.5*m.IJS; drift=.5*(1+m.SPMO)/(1+combo); turnover=2*(drift-.5).abs(); combo_net=combo-turnover*(COST_BPS/10000); combo_excess=combo_net-(.5*m.SPY+.5*m.IJR)
z=pd.concat([sec.excess.rename('industry_excess'),combo_excess.rename('combo_excess')],axis=1).loc['2017-01-01':].dropna()
blocks={'2017_2019':('2017-01-01','2019-12-31'),'2020_2022':('2020-01-01','2022-12-31'),'2023_plus':('2023-01-01','2026-12-31')}; bc={k:float(z.loc[a:b].corr().iloc[0,1]) for k,(a,b) in blocks.items()}; overall=float(z.corr().iloc[0,1]); passes=abs(overall)<0.4 and sum(abs(v)<0.4 for v in bc.values())>=2
decision='P343_COMPLEMENTARITY_SUPPORTED' if passes else 'P343_COMPLEMENTARITY_NOT_SUPPORTED'
out={'schema':'research.p343_industry_vs_spmo_smallvalue_complementarity_r1','parent':'P330/P304','claim':'Orthogonal combination-information discriminator: compare monthly matched-excess streams of the frozen corrected nine-sector top-3 industry-momentum survivor and the frozen 50/50 SPMO+IJS survivor versus its 50/50 SPY+IJR matched control. No blend weights, ranking, universe, signal, dates, or cost tuning; this tests whether two supported mechanisms carry distinct excess-return information before any combination experiment.','cost_bps':COST_BPS,'overall_excess_correlation':overall,'block_excess_correlations':bc,'observations':int(len(z)),'decision_rule':'Complementarity is supported only if absolute overall excess correlation is <0.40 and at least 2/3 fixed calendar blocks are also <0.40. Failure means do not assume independent alpha sources; preserve each standalone survivor evidence.','decision':decision,'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p343_industry_vs_spmo_smallvalue_complementarity_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))