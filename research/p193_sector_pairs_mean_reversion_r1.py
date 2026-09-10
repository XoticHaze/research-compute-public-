import hashlib,json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
PAIRS=[("MSFT","ORCL"),("JPM","BAC"),("JNJ","MRK"),("CAT","HON"),("PG","KO"),("XOM","CVX")]; STOCKS=sorted({x for p in PAIRS for x in p}); ALL=STOCKS+["SPY"]; COSTS=(2,5,10); PC=5; WINDOWS={"2010":"2010-01-01","2015":"2015-01-01","2020":"2020-01-01"}
def met(r,ann=252):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); c=float(e.iloc[-1]**(ann/len(r))-1); v=float(r.std(ddof=0)*math.sqrt(ann)); return {"cagr":c,"sharpe":float(r.mean()*ann/v) if v else None,"maxdd":float((e/e.cummax()-1).min())}
def evalw(z,c):
 net=z.gross-z.turn*c/10000; a,st,sp=met(net),met(z.static),met(z.spy); fs=[]
 for i,ix in enumerate(np.array_split(np.arange(len(z)),5),1):
  q=z.iloc[ix]; n=q.gross-q.turn*c/10000; fs.append({"fold":i,"cash_excess":met(n)["cagr"],"static_excess":met(n)["cagr"]-met(q.static)["cagr"]})
 return {"days":len(z),"candidate":a,"static_pair_control":st,"spy":sp,"excess_cash":a["cagr"],"excess_static":a["cagr"]-st["cagr"],"excess_spy_opportunity":a["cagr"]-sp["cagr"],"positive_cash_folds":sum(x["cash_excess"]>0 for x in fs),"positive_static_folds":sum(x["static_excess"]>0 for x in fs),"mean_turnover":float(z.turn.mean()),"mean_gross_exposure":float(z.gross_exposure.mean()),"folds":fs}
raw=yf.download(ALL,start="2007-01-01",end="2026-09-03",auto_adjust=True,progress=False,group_by="column",threads=False); c=raw["Close"][ALL] if isinstance(raw.columns,pd.MultiIndex) else raw[ALL]; c=c.dropna(how="all").ffill().dropna(); dr=c.pct_change().fillna(0); weights=pd.DataFrame(0.,index=c.index,columns=STOCKS); states={p:0 for p in PAIRS}
for p in PAIRS:
 a,b=p; lr=np.log(c[a]/c[b]); mu=lr.rolling(60,min_periods=60).mean().shift(1); sd=lr.rolling(60,min_periods=60).std(ddof=0).shift(1); z=(lr.shift(1)-mu)/sd
 for dt in c.index:
  q=z.loc[dt]
  if not np.isfinite(q): continue
  st=states[p]
  if st==0:
   if q>=2: st=-1
   elif q<=-2: st=1
  elif abs(q)<=0.5: st=0
  states[p]=st
  if st: weights.loc[dt,a]+=st/(2*len(PAIRS)); weights.loc[dt,b]+=-st/(2*len(PAIRS))
prev=weights.shift(1).fillna(0); turn=(weights-prev).abs().sum(axis=1); gross=(weights.shift(1).fillna(0)*dr[STOCKS]).sum(axis=1); static=sum((dr[a]-dr[b])/(2*len(PAIRS)) for a,b in PAIRS); spy=dr.SPY; rows=pd.DataFrame({"gross":gross,"static":static,"spy":spy,"turn":turn,"gross_exposure":weights.abs().sum(axis=1)}).iloc[61:]
tests={str(cb):{k:evalw(rows.loc[pd.Timestamp(st):],cb) for k,st in WINDOWS.items()} for cb in COSTS}; p=tests[str(PC)]["2015"]; pair_attr={}
for a,b in PAIRS:
 lr=np.log(c[a]/c[b]); mu=lr.rolling(60,min_periods=60).mean().shift(1); sd=lr.rolling(60,min_periods=60).std(ddof=0).shift(1); zz=(lr.shift(1)-mu)/sd; st=0; rr=[]
 for i,dt in enumerate(c.index):
  q=zz.loc[dt]
  if not np.isfinite(q) or i==0: rr.append(0); continue
  if st==0:
   if q>=2: st=-1
   elif q<=-2: st=1
  elif abs(q)<=0.5: st=0
  rr.append(st*0.5*(dr.loc[dt,a]-dr.loc[dt,b]))
 pair_attr[f"{a}/{b}"]=met(pd.Series(rr,index=c.index).loc['2015-01-01':])["cagr"]
decision="P193_SECTOR_PAIRS_MEAN_REVERSION_SURVIVOR" if p["excess_cash"]>0 and p["excess_static"]>0 and p["positive_cash_folds"]>=3 and p["candidate"]["sharpe"]>=0.5 and p["candidate"]["maxdd"]>=-0.20 and sum(v>0 for v in pair_attr.values())>=4 else "P193_SECTOR_PAIRS_MEAN_REVERSION_REJECT"; out={"schema":"research.p193_sector_pairs_mean_reversion_r1","parent":"P193","hypothesis":"A frozen set of economically related same-sector stock pairs exhibits tradable medium-horizon price-ratio mean reversion after realistic turnover costs.","contract":{"pairs":PAIRS,"signal":"60-session lagged log-price-ratio z-score; enter at abs(z)>=2 against deviation, exit at abs(z)<=0.5","portfolio":"equal gross allocation across six market-neutral pairs; no leverage scaling","cost_bps_one_way":COSTS,"primary_cost_bps":PC,"matched_controls":["cash zero-return for market-neutral alpha","static always-long-first/short-second same pairs","SPY opportunity cost"],"windows":WINDOWS,"folds":5,"gate":"2015+ at 5 bps: positive CAGR vs cash and static-pair control, >=3/5 positive cash folds, Sharpe >=0.5, max drawdown >=-20%, >=4/6 pair contributions positive","no_pair_threshold_lookback_cost_or_chronology_search":True},"source":{"provider":"Yahoo Finance via yfinance; research-only","rows":len(c),"last":str(c.index[-1]),"panel_sha256":hashlib.sha256(c.to_csv().encode()).hexdigest()},"tests":tests,"pair_2015_gross_attribution":pair_attr,"decision":decision,"boundaries":{"portfolio_ranking":False,"product_runtime":False,"broker":False,"live_trading":False}}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p193_sector_pairs_mean_reversion_r1.json').write_text(json.dumps(out,sort_keys=True,indent=2)); print(json.dumps(out,sort_keys=True))