import hashlib,json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
from pandas_datareader import data as web
A=["SPY","IEF"]
COSTS=(5,10,25)
PC=10
WINDOWS={"2005":"2005-01-01","2010":"2010-01-01","2015":"2015-01-01","2020":"2020-01-01"}
def met(r):
 r=pd.Series(r).dropna(); e=(1+r).cumprod(); n=len(r)
 c=float(e.iloc[-1]**(12/n)-1); v=float(r.std(ddof=0)*math.sqrt(12))
 return {"cagr":c,"sharpe":float(r.mean()*12/v) if v else None,"maxdd":float((e/e.cummax()-1).min())}
def ev(z,c):
 cand=z.gross-z.turn*c/10000; matched=z.matched-z.matched_turn*c/10000; spy=z.spy
 mc,mm,ms=met(cand),met(matched),met(spy); fs=[]
 for i,ix in enumerate(np.array_split(np.arange(len(z)),5),1):
  q=z.iloc[ix]; qc=q.gross-q.turn*c/10000; qm=q.matched-q.matched_turn*c/10000
  fs.append({"fold":i,"candidate":met(qc),"matched":met(qm),"matched_excess_cagr":met(qc)["cagr"]-met(qm)["cagr"]})
 return {"months":len(z),"candidate":mc,"matched":mm,"spy":ms,"matched_excess_cagr":mc["cagr"]-mm["cagr"],"spy_excess_cagr":mc["cagr"]-ms["cagr"],"positive_matched_folds":sum(x["matched_excess_cagr"]>0 for x in fs),"mean_turnover":float(z.turn.mean()),"folds":fs}
raw=yf.download(A,start="2003-01-01",end="2026-09-03",auto_adjust=True,progress=False,group_by="column",threads=False)
cl=raw["Close"][A] if isinstance(raw.columns,pd.MultiIndex) else raw[A]
cl=cl.dropna(how="any"); m=cl.resample("ME").last(); rets=m.pct_change()
y=web.DataReader(["DGS10","DTB3"],"fred","2003-01-01","2026-09-03").ffill(); spread=(y["DGS10"]-y["DTB3"]).resample("ME").last()
idx=rets.index.intersection(spread.index); rets=rets.loc[idx]; spread=spread.loc[idx]
rows=[]; prev=pd.Series([0.,0.],index=A); matched_w=pd.Series([0.5,0.5],index=A); prev_m=pd.Series([0.,0.],index=A)
for i in range(1,len(idx)):
 dt=idx[i]; sig=float(spread.iloc[i-1]); w=pd.Series([1.,0.],index=A) if sig>=0 else pd.Series([0.,1.],index=A)
 rr=rets.loc[dt]; turn=float((w-prev).abs().sum()/2); mt=float((matched_w-prev_m).abs().sum()/2); rows.append({"date":dt,"spread_signal":sig,"risk_on":bool(sig>=0),"gross":float((w*rr).sum()),"matched":float((matched_w*rr).sum()),"spy":float(rr["SPY"]),"turn":turn,"matched_turn":mt}); prev=w; prev_m=matched_w
z=pd.DataFrame(rows).set_index("date"); tests={str(cb):{k:ev(z.loc[pd.Timestamp(st):],cb) for k,st in WINDOWS.items()} for cb in COSTS}; p=tests[str(PC)]["2010"]; p15=tests[str(PC)]["2015"]; p25=tests["25"]["2010"]
decision="P202_YIELDCURVE_REGIME_SURVIVOR" if p["matched_excess_cagr"]>0 and p15["matched_excess_cagr"]>0 and p["positive_matched_folds"]>=4 and p25["matched_excess_cagr"]>0 and p["candidate"]["maxdd"]>=p["matched"]["maxdd"] else "P202_YIELDCURVE_REGIME_REJECT"
out={"schema":"research.p202_yieldcurve_regime_allocation_r1","parent":"P202","hypothesis":"A fixed causal 10Y-minus-3M Treasury-curve sign regime can improve SPY/IEF capital allocation: hold SPY when prior month-end spread is nonnegative and IEF when inverted.","contract":{"assets":A,"macro_series":["DGS10","DTB3"],"signal":"prior month-end DGS10-DTB3 sign","allocation":"SPY if spread>=0 else IEF for next completed month","matched":"static 50/50 SPY/IEF","opportunity_cost":"SPY buy-and-hold over identical monthly rows","cost_bps_one_way":COSTS,"primary_cost_bps":PC,"windows":WINDOWS,"folds":5,"gate":"2010+ and 2015+ positive matched excess; >=4/5 positive 2010 folds; positive matched excess at 25 bps; max drawdown no worse than matched","no_threshold_lookback_asset_cost_or_chronology_search":True},"source":{"prices":"Yahoo Finance via yfinance; research-only","macro":"FRED DGS10/DTB3 via pandas_datareader","price_rows":len(cl),"last_price":str(cl.index[-1]),"panel_sha256":hashlib.sha256(cl.to_csv().encode()).hexdigest(),"macro_sha256":hashlib.sha256(y.to_csv().encode()).hexdigest()},"tests":tests,"risk_on_months":int(z.risk_on.sum()),"risk_off_months":int((~z.risk_on).sum()),"decision":decision,"boundaries":{"portfolio_ranking":False,"product_runtime":False,"broker":False,"live_trading":False}}
Path("artifacts").mkdir(exist_ok=True); Path("artifacts/p202_yieldcurve_regime_allocation_r1.json").write_text(json.dumps(out,sort_keys=True,indent=2)); print(json.dumps(out,sort_keys=True))