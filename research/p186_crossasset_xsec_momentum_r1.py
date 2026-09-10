import hashlib,json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf

ASSETS=["SPY","IEF","GLD","DBC"]; COSTS=[25,50,100]; PC=50; WINDOWS={"2010":"2010-01-01","2015":"2015-01-01","2020":"2020-01-01"}; TOP=2

def cagr(r):
 r=pd.Series(r).dropna(); return float((1+r).prod()**(12/len(r))-1)
def maxdd(r):
 e=(1+pd.Series(r).fillna(0)).cumprod(); return float((e/e.cummax()-1).min())
def sharpe(r):
 r=pd.Series(r).dropna(); s=r.std(ddof=1); return float(np.sqrt(12)*r.mean()/s) if s>0 else None
def met(r): return {"cagr":cagr(r),"maxdd":maxdd(r),"sharpe":sharpe(r)}
def ev(z,c):
 cand=z.gross-z.turn*c/10000; ew=z.equal_weight; spy=z.SPY_ret
 return {"candidate":met(cand),"equal_weight":met(ew),"spy":met(spy),"excess_equal_weight":cagr(cand)-cagr(ew),"excess_spy":cagr(cand)-cagr(spy),"months":len(z),"mean_turnover":float(z.turn.mean())}
def folds(z,c):
 out=[]
 for i,idx in enumerate(np.array_split(np.arange(len(z)),5),1):
  x=ev(z.iloc[idx],c); out.append({"fold":i,"equal_weight_excess":x["excess_equal_weight"],"spy_excess":x["excess_spy"]})
 return out
raw=yf.download(ASSETS,start="2007-01-01",end="2026-09-03",auto_adjust=True,progress=False,group_by="column",threads=False); close=raw["Close"][ASSETS] if isinstance(raw.columns,pd.MultiIndex) else raw[ASSETS]; close=close.dropna(how="all").ffill().dropna(); m=close.resample("ME").last(); ret=m.pct_change(); mom=m.shift(1)/m.shift(12)-1; rows=[]; prev=None
for i in range(12,len(m)-1):
 dt,nxt=m.index[i],m.index[i+1]; score=mom.loc[dt].dropna().sort_values(ascending=False)
 if len(score)<TOP: continue
 chosen=list(score.index[:TOP]); w=pd.Series(0.,index=ASSETS); w.loc[chosen]=1/TOP; r=ret.loc[nxt]; vec=w.to_numpy(); turn=0 if prev is None else float(np.abs(vec-prev).sum()/2); rows.append({"date":nxt,"gross":float((w*r[ASSETS]).sum()),"turn":turn,"equal_weight":float(r[ASSETS].mean()),"SPY_ret":float(r.SPY),"selected":",".join(chosen)}); prev=vec.copy()
z=pd.DataFrame(rows).set_index("date"); out={"schema":"research.p186_crossasset_xsec_momentum_r1","parent":"P186","hypothesis":"A fixed 12-1 relative-momentum top-2 selector across equities, Treasuries, gold and commodities creates durable after-cost excess that the failed per-sleeve absolute trend architecture did not.","contract":{"universe":ASSETS,"signal":"completed-month 12-1 return excluding most recent month; hold top 2 equally next month","top_k":TOP,"cost_bps":COSTS,"primary_cost_bps":PC,"windows":WINDOWS,"matched":"static equal-weight same four assets","opportunity_control":"SPY","predeclared_gate":"2015+ at 50 bps: positive excess vs equal-weight and SPY, >=3/5 positive equal-weight folds, max drawdown no worse than equal-weight","no_search":True},"source":{"provider":"Yahoo Finance via yfinance; research-only","rows":len(close),"last":str(close.index[-1]),"panel_sha256":hashlib.sha256(close.to_csv().encode()).hexdigest()},"tests":{}}
for c in COSTS:
 out["tests"][str(c)]={}
 for k,s in WINDOWS.items():
  q=z.loc[pd.Timestamp(s):]; x=ev(q,c); fs=folds(q,c); x["folds"]=fs; x["positive_equal_weight_folds"]=sum(a["equal_weight_excess"]>0 for a in fs); x["positive_spy_folds"]=sum(a["spy_excess"]>0 for a in fs); out["tests"][str(c)][k]=x
p=out["tests"][str(PC)]["2015"]; out["decision"]="P186_CROSSASSET_XSEC_SURVIVOR" if p["excess_equal_weight"]>0 and p["excess_spy"]>0 and p["positive_equal_weight_folds"]>=3 and p["candidate"]["maxdd"]>=p["equal_weight"]["maxdd"] else "P186_CROSSASSET_XSEC_REJECT"; Path("artifacts").mkdir(exist_ok=True); Path("artifacts/p186_crossasset_xsec_momentum_r1.json").write_text(json.dumps(out,sort_keys=True,indent=2)); print(json.dumps(out,sort_keys=True))
