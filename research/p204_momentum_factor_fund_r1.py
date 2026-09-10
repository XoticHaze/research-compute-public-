import hashlib,json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
A=["MTUM","SPY","IWF"]
WINDOWS={"2014":"2014-01-01","2018":"2018-01-01","2020":"2020-01-01"}; COST_BPS=10
def met(r):
 r=pd.Series(r).dropna(); e=(1+r).cumprod(); n=len(r); c=float(e.iloc[-1]**(12/n)-1); v=float(r.std(ddof=0)*math.sqrt(12)); return {"cagr":c,"sharpe":float(r.mean()*12/v) if v else None,"maxdd":float((e/e.cummax()-1).min())}
def cost(r):
 q=pd.Series(r).dropna().copy()
 if len(q): q.iloc[0]=(1+q.iloc[0])*(1-COST_BPS/10000)-1; q.iloc[-1]=(1+q.iloc[-1])*(1-COST_BPS/10000)-1
 return q
def ev(df):
 q,s,g=cost(df.MTUM),cost(df.SPY),cost(df.IWF); mq,ms,mg=met(q),met(s),met(g); folds=[]
 for i,ix in enumerate(np.array_split(np.arange(len(df)),5),1):
  d=df.iloc[ix]; fq,fs,fg=met(cost(d.MTUM)),met(cost(d.SPY)),met(cost(d.IWF)); folds.append({"fold":i,"mtum":fq,"spy":fs,"iwf":fg,"excess_spy":fq['cagr']-fs['cagr'],"excess_iwf":fq['cagr']-fg['cagr']})
 return {"months":len(df),"mtum":mq,"spy":ms,"iwf":mg,"excess_spy":mq['cagr']-ms['cagr'],"excess_iwf":mq['cagr']-mg['cagr'],"positive_spy_folds":sum(x['excess_spy']>0 for x in folds),"positive_iwf_folds":sum(x['excess_iwf']>0 for x in folds),"folds":folds}
raw=yf.download(A,start='2013-04-18',end='2026-09-03',auto_adjust=True,progress=False,group_by='column',threads=False); cl=raw['Close'][A] if isinstance(raw.columns,pd.MultiIndex) else raw[A]; cl=cl.dropna(how='any'); r=cl.resample('ME').last().pct_change().dropna(how='any'); tests={k:ev(r.loc[pd.Timestamp(st):]) for k,st in WINDOWS.items()}; p,p18,p20=tests['2014'],tests['2018'],tests['2020']; decision='P204_MOMENTUM_FACTOR_FUND_SURVIVOR' if p['excess_spy']>0 and p['excess_iwf']>0 and p18['excess_spy']>0 and p18['excess_iwf']>0 and p20['excess_spy']>0 and p20['excess_iwf']>0 and p['positive_spy_folds']>=3 and p['positive_iwf_folds']>=3 and p['mtum']['maxdd']>=p['iwf']['maxdd'] else 'P204_MOMENTUM_FACTOR_FUND_REJECT'
out={'schema':'research.p204_momentum_factor_fund_r1','parent':'P204','hypothesis':'A live momentum-factor ETF implementation (MTUM) creates durable net-of-fund-cost excess beyond both broad US equity exposure (SPY) and a growth-style control (IWF), distinguishing momentum premium from growth beta.','contract':{'candidate':'MTUM adjusted total-return history; internal fund expenses embedded','controls':{'broad':'SPY','style':'IWF'},'windows':WINDOWS,'folds':5,'external_cost_bps_one_way':COST_BPS,'cost_application':'one entry and one exit charge identically applied','gate':'2014+, 2018+, 2020+ positive CAGR excess versus SPY and IWF; >=3/5 positive 2014 folds versus each; MTUM max drawdown no worse than IWF','no_asset_window_cost_or_control_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','rows':len(cl),'first':str(cl.index[0]),'last':str(cl.index[-1]),'panel_sha256':hashlib.sha256(cl.to_csv().encode()).hexdigest()},'tests':tests,'decision':decision,'boundaries':{'portfolio_ranking':False,'product_runtime':False,'broker':False,'live_trading':False}}
Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p204_momentum_factor_fund_r1.json').write_text(json.dumps(out,sort_keys=True,indent=2)); print(json.dumps(out,sort_keys=True))