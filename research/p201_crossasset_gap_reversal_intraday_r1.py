import hashlib,json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
A=["SPY","QQQ","IWM"]
COSTS=(1,5,10)
PC=5
WINDOWS={"2005":"2005-01-01","2010":"2010-01-01","2015":"2015-01-01","2020":"2020-01-01"}
def met(r):
 r=pd.Series(r).dropna(); e=(1+r).cumprod(); n=len(r)
 if n==0:return {"cagr":None,"sharpe":None,"maxdd":None}
 c=float(e.iloc[-1]**(252/n)-1); v=float(r.std(ddof=0)*math.sqrt(252))
 return {"cagr":c,"sharpe":float(r.mean()*252/v) if v else None,"maxdd":float((e/e.cummax()-1).min())}
def ev(z,c):
 fee=2*c/10000
 cand=z.candidate_gross-fee; matched=z.matched_gross-fee; spread=cand-matched
 mc,mm=met(cand),met(matched); fs=[]
 for i,ix in enumerate(np.array_split(np.arange(len(z)),5),1):
  q=z.iloc[ix]; qc=q.candidate_gross-fee; qm=q.matched_gross-fee
  fs.append({"fold":i,"candidate":met(qc),"matched":met(qm),"excess_cagr":met(qc)["cagr"]-met(qm)["cagr"],"mean_daily_spread":float((qc-qm).mean())})
 return {"days":len(z),"candidate":mc,"matched":mm,"matched_excess_cagr":mc["cagr"]-mm["cagr"],"mean_daily_spread":float(spread.mean()),"positive_excess_folds":sum(x["excess_cagr"]>0 for x in fs),"folds":fs}
raw=yf.download(A,start="2004-01-01",end="2026-09-03",auto_adjust=True,progress=False,group_by="column",threads=False)
if not isinstance(raw.columns,pd.MultiIndex): raise RuntimeError("expected MultiIndex OHLC panel")
op=raw["Open"][A].dropna(how="any"); cl=raw["Close"][A].dropna(how="any"); idx=op.index.intersection(cl.index); op=op.loc[idx]; cl=cl.loc[idx]
prev=cl.shift(1); gap=op/prev-1; intraday=cl/op-1
rows=[]
for dt in idx[1:]:
 g=gap.loc[dt]
 if g.isna().any(): continue
 pick=str(g.idxmin()); cg=float(intraday.loc[dt,pick]); mg=float(intraday.loc[dt].mean())
 rows.append({"date":dt,"pick":pick,"worst_gap":float(g.min()),"candidate_gross":cg,"matched_gross":mg})
z=pd.DataFrame(rows).set_index("date")
tests={str(cb):{k:ev(z.loc[pd.Timestamp(st):],cb) for k,st in WINDOWS.items()} for cb in COSTS}
p=tests[str(PC)]["2010"]; p15=tests[str(PC)]["2015"]; p10=tests["10"]["2010"]
decision="P201_CROSSASSET_GAP_REVERSAL_SURVIVOR" if p["matched_excess_cagr"]>0 and p15["matched_excess_cagr"]>0 and p["positive_excess_folds"]>=4 and p["candidate"]["cagr"]>0 and p10["matched_excess_cagr"]>0 else "P201_CROSSASSET_GAP_REVERSAL_REJECT"
out={"schema":"research.p201_crossasset_gap_reversal_intraday_r1","parent":"P201","hypothesis":"At each liquid US equity ETF open, buying the ETF with the worst causal overnight gap among SPY/QQQ/IWM and exiting at that close captures a cross-sectional intraday reversal premium over equal-weight intraday exposure.","contract":{"assets":A,"signal":"current open / previous close - 1, choose minimum; signal known at executable open","holding":"selected ETF open-to-close only; flat overnight","matched":"equal-weight SPY/QQQ/IWM open-to-close on identical days with identical daily round-trip cost","cost_bps_one_way":COSTS,"primary_cost_bps":PC,"windows":WINDOWS,"folds":5,"gate":"2010+ and 2015+ positive matched excess CAGR; >=4/5 positive 2010 chronological folds; positive candidate CAGR; positive 2010 matched excess at 10 bps","no_asset_threshold_lookback_cost_or_chronology_search":True},"source":{"provider":"Yahoo Finance via yfinance; research-only","rows":len(idx),"last":str(idx[-1]),"panel_sha256":hashlib.sha256(pd.concat({"open":op,"close":cl},axis=1).to_csv().encode()).hexdigest()},"tests":tests,"selection_counts":z.pick.value_counts().to_dict(),"decision":decision,"boundaries":{"portfolio_ranking":False,"product_runtime":False,"broker":False,"live_trading":False}}
Path("artifacts").mkdir(exist_ok=True); Path("artifacts/p201_crossasset_gap_reversal_intraday_r1.json").write_text(json.dumps(out,sort_keys=True,indent=2)); print(json.dumps(out,sort_keys=True))