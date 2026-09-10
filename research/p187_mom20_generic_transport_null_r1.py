import hashlib,json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

TRAIN=("AMAT","APH","KLAC","LRCX","TXN","NXPI","ADI"); EXT=("CAT","JPM","UNH","WMT","XOM","LIN")
HOLD=20; DELAY=1; FOLDS=6; MIN_TRAIN=756; PURGE=22; COST=25.; EVAL_FIRST=2; NULL_DRAWS=2000; SEED=187013
OUT=Path("artifacts/p187_mom20_generic_transport_null_r1.json")
def fold_bounds(n):
 e=np.linspace(MIN_TRAIN,n-(HOLD+DELAY+1),FOLDS+1,dtype=int); return [(int(e[i]),int(e[i+1])) for i in range(FOLDS)]
def fit(t):
 m=Pipeline([("scale",StandardScaler()),("ridge",Ridge(alpha=10.0))]); m.fit(t[["mom20"]].to_numpy(float),t.target.to_numpy(float)); return m
symbols=(*TRAIN,*EXT); raw=yf.download(list(symbols),start="2014-01-01",end="2026-09-03",auto_adjust=True,progress=False,group_by="column",threads=False); close=raw["Close"][list(symbols)] if isinstance(raw.columns,pd.MultiIndex) else raw[list(symbols)]; close=close.dropna(how="all").ffill().dropna(); cal=pd.DatetimeIndex(pd.to_datetime(close.index,utc=True)); data={}
for s in symbols:
 d=pd.DataFrame({"price":close[s].to_numpy(float)}); d["mom20"]=d.price.pct_change(20); d["target"]=(d.price.shift(-(DELAY+HOLD))/d.price.shift(-DELAY)-1)*10000-COST; data[s]=d
folds=fold_bounds(len(cal))
def frame(ss):
 rr=[]
 for s in ss:
  d=data[s].copy(); d["symbol"]=s; d["i"]=np.arange(len(d)); fc=np.zeros(len(d),dtype=int)
  for f,(a,b) in enumerate(folds,1): fc[a:max(a,b-(DELAY+HOLD))]=f
  d["fold"]=fc; rr.append(d[d.fold>0][["symbol","i","fold","mom20","target"]])
 return pd.concat(rr,ignore_index=True).dropna()
train,test=frame(TRAIN),frame(EXT); rng=np.random.default_rng(SEED); per=[]
for s in EXT:
 fold_rows=[]; cand_all=[]; hard_all=[]; null_fold_specs=[]
 for f in range(EVAL_FIRST,FOLDS+1):
  start,_=folds[f-1]; tr=train[train.i<start-PURGE]; te=test[(test.symbol==s)&(test.fold==f)].copy(); pred=fit(tr).predict(te[["mom20"]].to_numpy(float)); mask=pred>0; cand=te.target.to_numpy(float)[mask]; prior=data[s].iloc[:start-PURGE].mom20.dropna(); th=float(prior.quantile(.70)); hard=te.loc[te.mom20>=th,"target"].to_numpy(float); cand_all.extend(cand); hard_all.extend(hard); null_fold_specs.append((te.target.to_numpy(float),len(cand))); fold_rows.append({"fold":f,"states":len(te),"selected":len(cand),"candidate_mean_bps":None if not len(cand) else float(cand.mean()),"unconditional_mean_bps":float(te.target.mean()),"hard_top30_mean_bps":None if not len(hard) else float(hard.mean()),"hard_top30_count":len(hard)})
 cand=np.asarray(cand_all,float); hard=np.asarray(hard_all,float); null=np.empty(NULL_DRAWS)
 for j in range(NULL_DRAWS):
  picks=[]
  for vals,n in null_fold_specs:
   if n: picks.extend(rng.choice(vals,size=n,replace=False).tolist())
  null[j]=np.mean(picks)
 p=float((1+np.sum(null>=cand.mean()))/(NULL_DRAWS+1)); positive_folds=sum(r["candidate_mean_bps"] is not None and r["candidate_mean_bps"]>r["unconditional_mean_bps"] for r in fold_rows); passed=bool(len(cand)>=50 and cand.mean()>0 and p<=.05 and positive_folds>=3); per.append({"symbol":s,"pass":passed,"selected":len(cand),"candidate_mean_bps":float(cand.mean()),"hard_top30_mean_bps":float(hard.mean()),"random_null_mean_bps":float(null.mean()),"random_null_p_ge_candidate":p,"positive_candidate_vs_unconditional_folds":positive_folds,"folds":fold_rows})
passing=sum(x["pass"] for x in per); out={"schema":"research.p187_mom20_generic_transport_null_r1","parent":"P187","hypothesis":"A simple mom20-only economic-value mapping learned on the original semiconductor survivor names transports genuine selection information to heterogeneous non-semiconductor equities, rather than merely selecting a random subset from positive-drift equity states.","contract":{"train_universe":list(TRAIN),"external_universe":list(EXT),"model":"Ridge(alpha=10)+StandardScaler using mom20 only; causal fold refits on training names only","target":"fixed20 +1-session entry net 25 bps","selection":"predicted value > 0","controls":["2,000 deterministic same-count random selections within every symbol/fold","causal prior-only top-30% mom20 rule","unconditional fold states"],"per_symbol_gate":"candidate mean >0, same-count random-null p<=0.05, and candidate beats unconditional mean in >=3/5 folds","broad_gate":">=4/6 external symbols pass","no_threshold_model_universe_window_or_cost_search":True},"source":{"provider":"Yahoo Finance via yfinance; research-only","rows":len(close),"last":str(close.index[-1]),"panel_sha256":hashlib.sha256(close.to_csv().encode()).hexdigest()},"per_symbol":per,"passing_symbols":passing,"decision":"P187_SIMPLE_MOM20_GENERIC_SELECTION_SUPPORTED" if passing>=4 else "P187_SIMPLE_MOM20_GENERIC_SELECTION_NOT_SUPPORTED","boundaries":{"portfolio_ranking":False,"runtime":False,"broker":False,"live_trading":False}}; OUT.parent.mkdir(exist_ok=True); OUT.write_text(json.dumps(out,sort_keys=True,indent=2)); print(json.dumps(out,sort_keys=True))
