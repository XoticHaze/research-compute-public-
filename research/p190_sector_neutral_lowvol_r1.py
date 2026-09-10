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
raw=yf.download(ALL,start="2007-01-01",end="2026-09-03",auto_adjust=True,progress=False,group_by="column",threads=False); close=raw["Close"][ALL] if isinstance(raw.columns,pd.MultiIndex) else raw[ALL]; close=close.dropna(how="all").ffill().dropna(); dret=close[STOCKS].pct_change(); vol=(dret.rolling(126,min_periods=100).std(ddof=0)*math.sqrt(252)).resample("ME").last(); m=close.resample("ME").last(); rows=[]; prev=pd.Series(0.,index=STOCKS)
for i in range(len(m)-1):
 dt,nxt=m.index[i],m.index[i+1]; w=pd.Series(0.,index=STOCKS); picks=[]
 if dt not in vol.index: continue
 for sec,names in SECTORS.items():
  sc=vol.loc[dt,names].dropna()
  if len(sc)!=len(names): picks=[]; break
  p=sc.sort_values().index[0]; picks.append(p); w[p]=1/len(SECTORS)
 if len(picks)!=len(SECTORS): continue
 rr=m.loc[nxt,STOCKS]/m.loc[dt,STOCKS]-1
 if rr.isna().any(): continue
 turn=float(np.abs(w-prev).sum()/2); rows.append({"date":nxt,"gross":float((w*rr).sum()),"matched":float(rr.mean()),"spy":float(m.loc[nxt,"SPY"]/m.loc[dt,"SPY"]-1),"turn":turn,"selected":",".join(picks)}); prev=w
z=pd.DataFrame(rows).set_index("date"); tests={str(c):{k:ev(z.loc[pd.Timestamp(s):],c) for k,s in WINDOWS.items()} for c in COSTS}; p=tests[str(PC)]["2015"]; decision="P190_SECTOR_NEUTRAL_LOWVOL_SURVIVOR" if p["excess_matched"]>0 and p["excess_spy"]>0 and p["positive_matched_folds"]>=3 and p["candidate"]["sharpe"]>=p["matched"]["sharpe"] and p["candidate"]["maxdd"]>=p["matched"]["maxdd"] else "P190_SECTOR_NEUTRAL_LOWVOL_REJECT"
out={"schema":"research.p190_sector_neutral_lowvol_r1","parent":"P190","hypothesis":"Within-sector low-volatility selection across a frozen heterogeneous large-cap universe creates durable after-cost excess rather than merely reducing risk through sector tilts.","contract":{"sectors":SECTORS,"signal":"lowest trailing 126-session realized volatility among three stocks within each sector at completed month-end; hold next month","portfolio":"equal-weight one selected stock from each of six sectors","cost_bps":COSTS,"primary_cost_bps":PC,"matched":"equal-weight same 18-stock universe, therefore same static sector weights","opportunity_control":"SPY","windows":WINDOWS,"folds":5,"gate":"2015+ at 50 bps: positive excess vs matched and SPY, >=3/5 positive matched folds, Sharpe and max drawdown no worse than matched","no_search":True},"source":{"provider":"Yahoo Finance via yfinance; research-only","rows":len(close),"last":str(close.index[-1]),"panel_sha256":hashlib.sha256(close.to_csv().encode()).hexdigest()},"tests":tests,"decision":decision,"boundaries":{"portfolio_ranking":False,"product_runtime":False,"broker":False,"live_trading":False}}
Path("artifacts").mkdir(exist_ok=True); Path("artifacts/p190_sector_neutral_lowvol_r1.json").write_text(json.dumps(out,sort_keys=True,indent=2)); print(json.dumps(out,sort_keys=True))