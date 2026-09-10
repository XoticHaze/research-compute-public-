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
raw=yf.download(ALL,start="2007-01-01",end="2026-09-03",auto_adjust=True,progress=False,group_by="column",threads=False); c=raw["Close"][ALL] if isinstance(raw.columns,pd.MultiIndex) else raw[ALL]; c=c.dropna(how="all").ffill().dropna(); m=c.resample("ME").last(); mom=m[U].shift(1)/m[U].shift(12)-1; vol=(c[U].pct_change().rolling(126,min_periods=100).std(ddof=0)*math.sqrt(252)).resample("ME").last(); rows=[]; prev=pd.Series(0.,index=U)
for i in range(12,len(m)-1):
 dt,nxt=m.index[i],m.index[i+1]; w=pd.Series(0.,index=U); ok=True
 for sec,names in S.items():
  sm=mom.loc[dt,names].dropna(); sv=vol.loc[dt,names].dropna()
  if len(sm)!=len(names) or len(sv)!=len(names): ok=False; break
  pm=sm.sort_values(ascending=False).index[0]; pv=sv.sort_values().index[0]; w[pm]+=0.5/len(S); w[pv]+=0.5/len(S)
 if not ok: continue
 rr=m.loc[nxt,U]/m.loc[dt,U]-1
 if rr.isna().any(): continue
 turn=float(np.abs(w-prev).sum()/2); rows.append({"date":nxt,"gross":float((w*rr).sum()),"matched":float(rr.mean()),"spy":float(m.loc[nxt,"SPY"]/m.loc[dt,"SPY"]-1),"turn":turn}); prev=w
z=pd.DataFrame(rows).set_index("date"); tests={str(cb):{k:ev(z.loc[pd.Timestamp(st):],cb) for k,st in WINDOWS.items()} for cb in COSTS}; p=tests[str(PC)]["2015"]; decision="P192_MOMENTUM_LOWVOL_BLEND_SURVIVOR" if p["excess_matched"]>0 and p["excess_spy"]>0 and p["positive_matched_folds"]>=3 and p["candidate"]["sharpe"]>=p["matched"]["sharpe"] and p["candidate"]["maxdd"]>=p["matched"]["maxdd"] else "P192_MOMENTUM_LOWVOL_BLEND_REJECT"; out={"schema":"research.p192_momentum_lowvol_blend_r1","parent":"P192","hypothesis":"A fixed 50/50 blend of the positive-alpha-but-higher-drawdown P189 momentum component and the lower-drawdown-but-negative-alpha P190 low-vol component preserves enough momentum excess while repairing risk to clear a full investable gate.","contract":{"sectors":S,"components":["P189 12-1 within-sector strongest","P190 126-session within-sector lowest volatility"],"component_weights":[0.5,0.5],"portfolio":"each component selects one stock per sector; component weights combine additively; next-month hold","cost_bps":COSTS,"primary_cost_bps":PC,"matched":"equal-weight identical 18-stock universe","opportunity_control":"SPY","windows":WINDOWS,"folds":5,"gate":"2015+ at 50 bps positive excess vs matched and SPY, >=3/5 positive matched folds, Sharpe and max drawdown no worse than matched","no_weight_signal_universe_cost_or_chronology_search":True},"source":{"provider":"Yahoo Finance via yfinance; research-only","rows":len(c),"last":str(c.index[-1]),"panel_sha256":hashlib.sha256(c.to_csv().encode()).hexdigest()},"tests":tests,"decision":decision,"boundaries":{"portfolio_ranking":False,"product_runtime":False,"broker":False,"live_trading":False}}; Path("artifacts").mkdir(exist_ok=True); Path("artifacts/p192_momentum_lowvol_blend_r1.json").write_text(json.dumps(out,sort_keys=True,indent=2)); print(json.dumps(out,sort_keys=True))