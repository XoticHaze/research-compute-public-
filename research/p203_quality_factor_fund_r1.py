import hashlib,json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
A=["QUAL","SPY","IWF"]
WINDOWS={"2014":"2014-01-01","2018":"2018-01-01","2020":"2020-01-01"}
COST_BPS=10

def met(r):
 r=pd.Series(r).dropna(); e=(1+r).cumprod(); n=len(r)
 c=float(e.iloc[-1]**(12/n)-1); v=float(r.std(ddof=0)*math.sqrt(12))
 return {"cagr":c,"sharpe":float(r.mean()*12/v) if v else None,"maxdd":float((e/e.cummax()-1).min())}

def after_entry_exit_cost(r,bps=COST_BPS):
 q=pd.Series(r).dropna().copy()
 if len(q):
  q.iloc[0]=(1+q.iloc[0])*(1-bps/10000)-1
  q.iloc[-1]=(1+q.iloc[-1])*(1-bps/10000)-1
 return q

def ev(df):
 q=after_entry_exit_cost(df.QUAL); s=after_entry_exit_cost(df.SPY); g=after_entry_exit_cost(df.IWF)
 mq,ms,mg=met(q),met(s),met(g); folds=[]
 for i,ix in enumerate(np.array_split(np.arange(len(df)),5),1):
  d=df.iloc[ix]; fq=met(after_entry_exit_cost(d.QUAL)); fs=met(after_entry_exit_cost(d.SPY)); fg=met(after_entry_exit_cost(d.IWF))
  folds.append({"fold":i,"qual":fq,"spy":fs,"iwf":fg,"excess_spy":fq["cagr"]-fs["cagr"],"excess_iwf":fq["cagr"]-fg["cagr"]})
 return {"months":len(df),"qual":mq,"spy":ms,"iwf":mg,"excess_spy":mq["cagr"]-ms["cagr"],"excess_iwf":mq["cagr"]-mg["cagr"],"positive_spy_folds":sum(x["excess_spy"]>0 for x in folds),"positive_iwf_folds":sum(x["excess_iwf"]>0 for x in folds),"folds":folds}

raw=yf.download(A,start="2013-07-16",end="2026-09-03",auto_adjust=True,progress=False,group_by="column",threads=False)
cl=raw["Close"][A] if isinstance(raw.columns,pd.MultiIndex) else raw[A]
cl=cl.dropna(how="any"); m=cl.resample("ME").last(); r=m.pct_change().dropna(how="any")
tests={k:ev(r.loc[pd.Timestamp(st):]) for k,st in WINDOWS.items()}
p=tests["2014"]; p18=tests["2018"]; p20=tests["2020"]
decision="P203_QUALITY_FACTOR_FUND_SURVIVOR" if p["excess_spy"]>0 and p["excess_iwf"]>0 and p18["excess_spy"]>0 and p18["excess_iwf"]>0 and p20["excess_spy"]>0 and p20["excess_iwf"]>0 and p["positive_spy_folds"]>=3 and p["positive_iwf_folds"]>=3 and p["qual"]["maxdd"]>=p["iwf"]["maxdd"] else "P203_QUALITY_FACTOR_FUND_REJECT"
out={"schema":"research.p203_quality_factor_fund_r1","parent":"P203","hypothesis":"A fundamentals-driven quality ETF implementation (QUAL) creates durable net-of-fund-cost excess beyond both broad US equity exposure (SPY) and a growth-style control (IWF), so apparent quality alpha is not merely growth beta.","contract":{"candidate":"QUAL adjusted total-return history; fund expense effects embedded in market price/NAV return","controls":{"broad":"SPY","style":"IWF growth control"},"windows":WINDOWS,"folds":5,"external_cost_bps_one_way":COST_BPS,"cost_application":"one entry and one exit charge applied identically to candidate and controls; internal ETF expenses already embedded","gate":"2014+, 2018+, and 2020+ positive CAGR excess versus both SPY and IWF; >=3/5 positive 2014 folds versus each control; QUAL max drawdown no worse than IWF","no_asset_window_cost_or_control_search":True},"source":{"provider":"Yahoo Finance via yfinance; research-only","rows":len(cl),"first":str(cl.index[0]),"last":str(cl.index[-1]),"panel_sha256":hashlib.sha256(cl.to_csv().encode()).hexdigest()},"tests":tests,"decision":decision,"boundaries":{"portfolio_ranking":False,"product_runtime":False,"broker":False,"live_trading":False}}
Path("artifacts").mkdir(exist_ok=True); Path("artifacts/p203_quality_factor_fund_r1.json").write_text(json.dumps(out,sort_keys=True,indent=2)); print(json.dumps(out,sort_keys=True))