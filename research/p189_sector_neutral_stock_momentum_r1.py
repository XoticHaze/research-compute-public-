import hashlib,json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
SECTORS={"tech":["MSFT","AAPL","ORCL"],"financial":["JPM","BAC","GS"],"healthcare":["JNJ","UNH","MRK"],"industrial":["CAT","HON","MMM"],"staples":["WMT","PG","KO"],"energy":["XOM","CVX","COP"]}
STOCKS=[s for xs in SECTORS.values() for s in xs]; ALL=STOCKS+["SPY"]; COSTS=(25,50,100); PC=50; WINDOWS={"2010":"2010-01-01","2015":"2015-01-01","2020":"2020-01-01"}
def met(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); c=float(e.iloc[-1]**(12/len(r))-1); v=float(r.std(ddof=0)*math.sqrt(12)); return {"cagr":c,"sharpe":float(r.mean()*12/v) if v else None,"maxdd":float((e/e.cummax()-1).min())}
def ev(z,c):
 net=z.gross-z.turn*c/10000; a,b,s=met(net),met(z.matched),met(z.spy); fs=[]
 for i,ix in enumerate(np.array_split(np.arange(len(z)),5),1):
  q=z.iloc[ix]; n=q.gross-q.turn*c/10000; fs.append({"fold":i,"matched_excess":met(n)["cagr"]-met(q.matched)["cagr"],"spy_excess":met(n)["cagr"]-met(q.spy)["cagr"]})
 return {"months":len(z),"candidate":a,"matched":b,"spy":s,"excess_matched":a["cagr"]-b["cagr"],"excess_spy":a["cagr"]-s["cagr"],"positive_matched_folds":sum(x["matched_excess"]>0 for x in fs),"positive_spy_folds":sum(x["spy_excess"]>0 for x in fs),"mean_turnover":float(z.turn.mean()),"folds":fs}
raw=yf.download(ALL,start="2007-01-01",end="2026-09-03",auto_adjust=True,progress=False,group_by="column",threads=False); close=raw["Close"][ALL] if isinstance(raw.columns,pd.MultiIndex) else raw[ALL]; close=close.dropna(how="all").ffill().dropna(); m=close.resample("ME").last(); mom=m[STOCKS].shift(1)/m[STOCKS].shift(12)-1; rows=[]; prev=pd.Series(0.,index=STOCKS)
for i in range(12,len(m)-1):
 dt,nxt=m.index[i],m.index[i+1]; w=pd.Series(0.,index=STOCKS); picks=[]
 for sec,names in SECTORS.items():
  sc=mom.loc[dt,names].dropna()
  if len(sc)!=len(names): picks=[]; break
  p=sc.sort_values(ascending=False).index[0]; picks.append(p); w[p]=1/len(SECTORS)
 if len(picks)!=len(SECTORS): continue
 rr=m.loc[nxt,STOCKS]/m.loc[dt,STOCKS]-1
 if rr.isna().any(): continue
 turn=float(np.abs(w-prev).sum()/2); rows.append({"date":nxt,"gross":float((w*rr).sum()),"matched":float(rr.mean()),"spy":float(m.loc[nxt,"SPY"]/m.loc[dt,"SPY"]-1),"turn":turn,"selected":",".join(picks)}); prev=w
z=pd.DataFrame(rows).set_index("date"); tests={str(c):{k:ev(z.loc[pd.Timestamp(s):],c) for k,s in WINDOWS.items()} for c in COSTS}; p=tests[str(PC)]["2015"]; decision="P189_SECTOR_NEUTRAL_STOCK_MOMENTUM_SURVIVOR" if p["excess_matched"]>0 and p["excess_spy"]>0 and p["positive_matched_folds"]>=3 and p["candidate"]["maxdd"]>=p["matched"]["maxdd"] else "P189_SECTOR_NEUTRAL_STOCK_MOMENTUM_REJECT"
out={"schema":"research.p189_sector_neutral_stock_momentum_r1","parent":"P189","hypothesis":"Within-sector 12-1 stock momentum across a frozen heterogeneous large-cap universe creates durable after-cost excess beyond passive exposure to the identical stocks and SPY.","contract":{"sectors":SECTORS,"signal":"completed-month 12-1 return excluding most recent month; choose strongest one of three stocks within each sector for next month","portfolio":"equal-weight one selected stock from each of six sectors","cost_bps":COSTS,"primary_cost_bps":PC,"matched":"equal-weight same 18-stock universe, therefore same static sector weights","opportunity_control":"SPY","windows":WINDOWS,"folds":5,"gate":"2015+ at 50 bps: positive excess vs matched and SPY, >=3/5 positive matched folds, max drawdown no worse than matched","no_search":True},"source":{"provider":"Yahoo Finance via yfinance; research-only","rows":len(close),"last":str(close.index[-1]),"panel_sha256":hashlib.sha256(close.to_csv().encode()).hexdigest()},"tests":tests,"decision":decision,"boundaries":{"portfolio_ranking":False,"product_runtime":False,"broker":False,"live_trading":False}}
Path("artifacts").mkdir(exist_ok=True); Path("artifacts/p189_sector_neutral_stock_momentum_r1.json").write_text(json.dumps(out,sort_keys=True,indent=2)); print(json.dumps(out,sort_keys=True))