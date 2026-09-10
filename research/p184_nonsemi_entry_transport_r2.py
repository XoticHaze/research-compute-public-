from __future__ import annotations

import hashlib,json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

TRAIN=("AMAT","APH","KLAC","LRCX","TXN","NXPI","ADI")
EXTERNAL={"CAT":"industrials","JPM":"financials","UNH":"healthcare","WMT":"consumer","XOM":"energy","LIN":"materials"}
CONTEXT=("SMH","QQQ"); HOLD=20; DELAY=1; FOLDS=6; MIN_TRAIN=756; PURGE=22; BASE_COST=25.; COSTS=(25,50,100,150,200); EVAL_FIRST_FOLD=2
FEATURES=["mom5","mom20","mom60","mom100","mom20_z252","mom20_accel5","vol20","vol20_z252","distance_high60","rs_smh20","rs_smh60","rs_qqq20","rs_qqq60","smh_mom20","smh_mom100","qqq_mom20","qqq_mom100","survivor_breadth_positive20","survivor_cross_section_mom20_pct"]
OUTPUT=Path("artifacts/p184_nonsemi_entry_transport_r2.json")

def folds(n):
 e=np.linspace(MIN_TRAIN,n-(HOLD+DELAY+1),FOLDS+1,dtype=int); return [(int(e[i]),int(e[i+1])) for i in range(FOLDS)]
def fit(t):
 m=Pipeline([("scale",StandardScaler()),("ridge",Ridge(alpha=10.0))]); m.fit(t[FEATURES].to_numpy(float),t.enter20_after25_bps.to_numpy(float)); return m

symbols=(*TRAIN,*EXTERNAL,*CONTEXT)
raw=yf.download(list(symbols),start="2014-01-01",end="2026-09-03",auto_adjust=True,progress=False,group_by="column",threads=False)
close=raw["Close"][list(symbols)] if isinstance(raw.columns,pd.MultiIndex) else raw[list(symbols)]
close=close.dropna(how="all").ffill().dropna()
if len(close)<1500: raise RuntimeError(f"insufficient common calendar {len(close)}")
calendar=pd.DatetimeIndex(pd.to_datetime(close.index,utc=True)); prices={s:pd.Series(close[s].to_numpy(float),index=calendar) for s in symbols}
outd={}
for s,p in prices.items():
 d=pd.DataFrame({"timestamp":calendar,"price":p.to_numpy(float)}); d["ret1"]=d.price.pct_change()
 for n in (5,20,60,100): d[f"mom{n}"]=d.price.pct_change(n)
 d["vol20"]=d.ret1.rolling(20,min_periods=20).std(ddof=0); pm,pv=d.mom20.shift(1),d.vol20.shift(1)
 mm,ms=pm.rolling(252,min_periods=126).mean(),pm.rolling(252,min_periods=126).std(ddof=0).replace(0,np.nan); vm,vs=pv.rolling(252,min_periods=126).mean(),pv.rolling(252,min_periods=126).std(ddof=0).replace(0,np.nan)
 d["mom20_z252"]=(d.mom20-mm)/ms; d["vol20_z252"]=(d.vol20-vm)/vs; d["mom20_accel5"]=d.mom20-d.mom20.shift(5); d["distance_high60"]=d.price/d.price.rolling(60,min_periods=60).max()-1; d["enter20_after25_bps"]=(d.price.shift(-(DELAY+HOLD))/d.price.shift(-DELAY)-1)*10000-BASE_COST; outd[s]=d
smh,qqq=outd["SMH"],outd["QQQ"]; surv=pd.DataFrame({s:outd[s].mom20 for s in TRAIN}); breadth=(surv>0).mean(axis=1)
for s in (*TRAIN,*EXTERNAL):
 d=outd[s]; d["rs_smh20"]=d.mom20-smh.mom20; d["rs_smh60"]=d.mom60-smh.mom60; d["rs_qqq20"]=d.mom20-qqq.mom20; d["rs_qqq60"]=d.mom60-qqq.mom60; d["smh_mom20"]=smh.mom20; d["smh_mom100"]=smh.mom100; d["qqq_mom20"]=qqq.mom20; d["qqq_mom100"]=qqq.mom100; d["survivor_breadth_positive20"]=breadth; d["survivor_cross_section_mom20_pct"]=[np.nan if pd.isna(v) else float((surv.iloc[i]<=v).mean()) for i,v in enumerate(d.mom20)]
fs=folds(len(calendar))
def frame(symbols):
 rr=[]
 for s in symbols:
  d=outd[s].copy(); d["symbol"]=s; d["signal_i"]=np.arange(len(d)); fc=np.zeros(len(d),dtype=int)
  for fold,(a,b) in enumerate(fs,1): fc[a:max(a,b-(DELAY+HOLD))]=fold
  d["fold"]=fc; rr.append(d[d.fold>0][["symbol","signal_i","fold",*FEATURES,"enter20_after25_bps","mom20"]])
 return pd.concat(rr,ignore_index=True).replace([np.inf,-np.inf],np.nan).dropna(subset=FEATURES+["enter20_after25_bps"])
trstates,teststates=frame(TRAIN),frame(tuple(EXTERNAL)); per=[]
for symbol,group in EXTERNAL.items():
 fr=[]; pools={k:[] for k in ("model","outside","frozen","unconditional")}
 for fold in range(EVAL_FIRST_FOLD,FOLDS+1):
  start,_=fs[fold-1]; tr=trstates[trstates.signal_i<start-PURGE]; te=teststates[(teststates.symbol==symbol)&(teststates.fold==fold)]
  if len(tr)<1000 or len(te)<200: raise RuntimeError(f"{symbol} fold {fold}: support train={len(tr)} test={len(te)}")
  pred=fit(tr).predict(te[FEATURES].to_numpy(float)); chosen=te.loc[pred>0].copy(); prior=outd[symbol].iloc[:start-PURGE].mom20.dropna(); threshold=float(prior.quantile(.70)); frozen=te.loc[te.mom20>=threshold]; outside=chosen.loc[chosen.mom20<threshold]
  def gross(x): return x.enter20_after25_bps.to_numpy(float)+BASE_COST
  vals={"model":gross(chosen),"outside":gross(outside),"frozen":gross(frozen),"unconditional":gross(te)}
  for k,v in vals.items(): pools[k].extend(v.tolist())
  fr.append({"fold":fold,"states":len(te),"model_trades":len(vals["model"]),"outside_frozen_trades":len(vals["outside"]),"model_net_mean_25":None if not len(vals["model"]) else float((vals["model"]-25).mean()),"outside_frozen_net_mean_25":None if not len(vals["outside"]) else float((vals["outside"]-25).mean()),"frozen_net_mean_25":None if not len(vals["frozen"]) else float((vals["frozen"]-25).mean()),"unconditional_net_mean_25":float((vals["unconditional"]-25).mean())})
 arr={k:np.asarray(v,float) for k,v in pools.items()}; costs={str(c):{k:{"trades":int(len(v)),"mean_bps":None if not len(v) else float((v-c).mean()),"median_bps":None if not len(v) else float(np.median(v-c))} for k,v in arr.items()} for c in COSTS}; pm=sum((r["model_net_mean_25"] if r["model_net_mean_25"] is not None else -1)>0 for r in fr); po=sum((r["outside_frozen_net_mean_25"] if r["outside_frozen_net_mean_25"] is not None else -1)>0 for r in fr); passed=bool(len(arr["outside"])>=20 and costs["25"]["outside"]["mean_bps"]>0 and pm>=3 and po>=3); per.append({"symbol":symbol,"group":group,"transport_pass":passed,"positive_model_folds":pm,"positive_outside_folds":po,"costs":costs,"folds":fr})
passing=sum(x["transport_pass"] for x in per); sha=hashlib.sha256(close.to_csv().encode()).hexdigest(); out={"schema":"research.p184_nonsemi_entry_transport_r2","parent":"P184","hypothesis":"The frozen semiconductor-trained Ridge positive-value region is sector-specific rather than a generic continuation detector.","contract":{"train_universe":list(TRAIN),"external_universe":EXTERNAL,"model":"exact Ridge(alpha=10)+StandardScaler family; causal fold refits only on seven semiconductor training names","features":FEATURES,"target":"fixed20 net after 25 bps with +1-session delay","selection":"predicted value > 0","comparators":["external symbol causal prior-only top-30% mom20","unconditional external states"],"costs_bps":list(COSTS),"broad_gate":">=4/6 symbols: >=20 outside-frozen trades, positive outside-frozen mean at 25 bps, >=3/5 positive model and outside-frozen folds","interpretation":"PASS falsifies semiconductor specificity; FAIL preserves semiconductor-conditional scope without weakening prior semiconductor evidence","no_external_training":True,"no_search":True},"source":{"provider":"Yahoo Finance via yfinance; research-only","rows":len(close),"last":str(close.index[-1]),"panel_sha256":sha},"per_symbol":per,"passing_symbols":passing,"broad_transport":passing>=4,"decision":"P184_SPECIFICITY_FALSIFIED_GENERIC_TRANSPORT" if passing>=4 else "P184_SPECIFICITY_SUPPORTED_NONSEMI_TRANSPORT_FAIL","boundaries":{"portfolio_ranking":False,"product_runtime":False,"broker":False,"live_trading":False}}; OUTPUT.parent.mkdir(exist_ok=True); OUTPUT.write_text(json.dumps(out,sort_keys=True,indent=2)); print(json.dumps(out,sort_keys=True))
