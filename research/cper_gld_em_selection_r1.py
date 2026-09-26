from pathlib import Path
import json
import numpy as np, pandas as pd, yfinance as yf
OUT=Path('artifacts/cper_gld_em_selection_r1.json'); OUT.parent.mkdir(exist_ok=True)
T=['CPER','GLD','EEM','SPY']
px=yf.download(T,start='2011-01-01',end='2026-09-01',auto_adjust=True,progress=False)['Close'].dropna()
m=px.resample('ME').last(); r=m.pct_change()
rel=(m.CPER/m.GLD).pct_change(3)
sig=(rel>0).shift(1).reindex(r.index).fillna(False)
raw=pd.Series(np.where(sig,r.EEM,r.SPY),index=r.index).astype(float)
switch=sig.astype(int).diff().abs().fillna(0); cand=raw-switch*0.001
def stats(x):
 x=x.dropna(); eq=(1+x).cumprod(); yrs=len(x)/12; return {'months':len(x),'cagr':float(eq.iloc[-1]**(1/yrs)-1),'max_drawdown':float((eq/eq.cummax()-1).min())}
def evaluate(start,end=None):
 idx=cand.index[cand.index>=pd.Timestamp(start)]
 if end is not None: idx=idx[idx<=pd.Timestamp(end)]
 p=float(sig.loc[idx].mean())
 ctrl=p*r.loc[idx,'EEM']+(1-p)*r.loc[idx,'SPY']
 a,b=stats(cand.loc[idx]),stats(ctrl)
 return {'candidate':a,'control':b,'eem_participation':p,'excess_cagr':a['cagr']-b['cagr']}
folds=[]
for a,b in [('2012-01-01','2015-12-31'),('2016-01-01','2019-12-31'),('2020-01-01','2022-12-31'),('2023-01-01','2026-08-31')]:
 e=evaluate(a,b); folds.append({'period':f'{a[:4]}-{b[:4]}','eem_participation':e['eem_participation'],'excess_cagr':e['excess_cagr']})
w={k:evaluate(k+'-01-01') for k in ['2012','2018','2022']}; pos=sum(x['excess_cagr']>0 for x in folds)
support=all(x['excess_cagr']>0 for x in w.values()) and pos>=3 and w['2012']['candidate']['max_drawdown']>=w['2012']['control']['max_drawdown']-0.05
decision='CPER_GLD_EM_SELECTION_SUPPORTED' if support else 'CPER_GLD_EM_SELECTION_REJECTED'
out={'workload_id':'CPER_GLD_EM_SELECTION_R1','decision':decision,'frozen':{'signal':'prior completed-month 3m CPER/GLD relative momentum > 0','candidate':'EEM when signal true else SPY','cost':'10bp one-way switch','matched_control':'static EEM/SPY mixture matched to realized EEM participation inside each evaluation slice','windows':['2012+','2018+','2022+'],'support':'positive matched excess all windows; >=3/4 positive chronology; <=5pp 2012+ drawdown deterioration','protected_boundary':'no signal/lookback/threshold/ticker/asset/horizon/cost/date/control/chronology rescue'},'windows':w,'folds':folds,'positive_folds':pos}
OUT.write_text(json.dumps(out,indent=2)); print(json.dumps(out,indent=2))
