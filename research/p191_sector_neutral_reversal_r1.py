import hashlib,json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
S={"tech":["MSFT","AAPL","ORCL"],"financial":["JPM","BAC","GS"],"healthcare":["JNJ","UNH","MRK"],"industrial":["CAT","HON","MMM"],"staples":["WMT","PG","KO"],"energy":["XOM","CVX","COP"]}; U=[x for v in S.values() for x in v]; ALL=U+["SPY"]; COSTS=(25,50,100); PC=50; WINDOWS={"2010":"2010-01-01","2015":"2015-01-01","2020":"2020-01-01"}
def met(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); c=float(e.iloc[-1]**(12/len(r))-1); v=float(r.std(ddof=0)*math.sqrt(12)); return {"cagr":c,"sharpe":float(r.mean()*12/v) if v else None,"maxdd":float((e/e.cummax()-1).min())}
def ev(z,c):
 n=z.gross-z.turn*c/10000; a,b,s=met(n),met(z.matched),met(z.spy); fs=[]
 for i,ix in enumerate(np.array_split(np.arange(len(z)),5),1):
  q=z.iloc[ix]; qn=q.gross-q.turn*c/10000; fs.append({"fold":i,"matched_excess":met(qn)["cagr"]-met(q.matched)["cagr"],"spy_excess":met(qn)["cagr"]-met(q.spy)["cagr"]})
 return {"months":len(z),"candidate":a,"matched":b,"spy":s,"excess_matched":a["cagr"]-b["cagr"],"excess_spy":a["cagr"]-s["cagr"],"positive_matched_folds":sum(x["matched_excess"]>0 for x in fs),"positive_spy_folds":sum(x["spy_excess"]>0 for x in fs),"mean_turnover":float(z.turn.mean()),"folds":fs}
raw=yf.download(ALL,start="2007-01-01",end="2026-09-03",auto_adjust=True,progress=False,group_by="column",threads=False); c=raw["Close"][ALL] if isinstance(raw.columns,pd.MultiIndex) else raw[ALL]; c=c.dropna(how="all").ffill().dropna(); m=c.resample("ME").last(); r1=m[U].pct_change(); rows=[]; prev=pd.Series(0.,index=U)
for i in range(1,len(m)-1):
 dt,nxt=m.index[i],m.index[i+1]; w=pd.Series(0.,index=U); picks=[]
 for sec,names in S.items():
  sc=r1.loc[dt,names].dropna()
  if len(sc)!=len(names): picks=[]; break
  p=sc.sort_values().index[0]; picks.append(p); w[p]=1/len(S)
 if len(picks)!=len(S): continue
 rr=m.loc[nxt,U]/m.loc[dt,U]-1
 if rr.isna().any(): continue
 turn=float(np.abs(w-prev).sum()/2); rows.append({"date":nxt,"gross":float((w*rr).sum()),"matched":float(rr.mean()),"spy":float(m.loc[nxt,"SPY"]/m.loc[dt,"SPY"]-1),"turn":turn}); prev=w
z=pd.DataFrame(rows).set_index("date"); tests={str(cb):{k:ev(z.loc[pd.Timestamp(st):],cb) for k,st in WINDOWS.items()} for cb in COSTS}; p=tests[str(PC)]["2015"]; decision="P191_SECTOR_NEUTRAL_REVERSAL_SURVIVOR" if p["excess_matched"]>0 and p["excess_spy"]>0 and p["positive_matched_folds"]>=3 and p["candidate"]["maxdd"]>=p["matched"]["maxdd"] else "P191_SECTOR_NEUTRAL_REVERSAL_REJECT"; out={"schema":"research.p191_sector_neutral_reversal_r1","parent":"P191","hypothesis":"One-month within-sector stock underperformance mean-reverts enough to create durable after-cost excess without relying on sector allocation.","contract":{"sectors":S,"signal":"prior completed-month return ascending; choose worst one of three within each sector for next month","portfolio":"equal-weight one stock per six sectors","cost_bps":COSTS,"primary_cost_bps":PC,"matched":"equal-weight identical 18-stock universe","opportunity_control":"SPY","windows":WINDOWS,"folds":5,"gate":"2015+ at 50 bps positive excess vs matched and SPY, >=3/5 positive matched folds, max drawdown no worse than matched","no_search":True},"source":{"provider":"Yahoo Finance via yfinance; research-only","rows":len(c),"last":str(c.index[-1]),"panel_sha256":hashlib.sha256(c.to_csv().encode()).hexdigest()},"tests":tests,"decision":decision,"boundaries":{"portfolio_ranking":False,"product_runtime":False,"broker":False,"live_trading":False}}; Path("artifacts").mkdir(exist_ok=True); Path("artifacts/p191_sector_neutral_reversal_r1.json").write_text(json.dumps(out,sort_keys=True,indent=2)); print(json.dumps(out,sort_keys=True))