import hashlib,json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
TRAIN=("AMAT","APH","KLAC","LRCX","TXN","NXPI","ADI"); EXT=("CAT","JPM","UNH","WMT","XOM","LIN"); CTX=("SMH","QQQ"); HOLD=20; DELAY=1; FOLDS=6; MIN_TRAIN=756; PURGE=22; COST=25.; EVAL_FIRST=2
FEATURES=["mom5","mom20","mom60","mom100","mom20_z252","mom20_accel5","vol20","vol20_z252","distance_high60","rs_smh20","rs_smh60","rs_qqq20","rs_qqq60","smh_mom20","smh_mom100","qqq_mom20","qqq_mom100","survivor_breadth_positive20","survivor_cross_section_mom20_pct"]
OUT=Path("artifacts/p188_nonsemi_incremental_mom20_control_r1.json")
def bounds(n):
 e=np.linspace(MIN_TRAIN,n-(HOLD+DELAY+1),FOLDS+1,dtype=int); return [(int(e[i]),int(e[i+1])) for i in range(FOLDS)]
def fit(t,features):
 m=Pipeline([("scale",StandardScaler()),("ridge",Ridge(alpha=10.0))]); m.fit(t[features].to_numpy(float),t.target.to_numpy(float)); return m
symbols=(*TRAIN,*EXT,*CTX); raw=yf.download(list(symbols),start="2014-01-01",end="2026-09-03",auto_adjust=True,progress=False,group_by="column",threads=False); close=raw["Close"][list(symbols)] if isinstance(raw.columns,pd.MultiIndex) else raw[list(symbols)]; close=close.dropna(how="all").ffill().dropna(); data={}
for s in symbols:
 d=pd.DataFrame({"price":close[s].to_numpy(float)}); d["ret1"]=d.price.pct_change()
 for n in (5,20,60,100): d[f"mom{n}"]=d.price.pct_change(n)
 d["vol20"]=d.ret1.rolling(20,min_periods=20).std(ddof=0); pm,pv=d.mom20.shift(1),d.vol20.shift(1); mm,ms=pm.rolling(252,min_periods=126).mean(),pm.rolling(252,min_periods=126).std(ddof=0).replace(0,np.nan); vm,vs=pv.rolling(252,min_periods=126).mean(),pv.rolling(252,min_periods=126).std(ddof=0).replace(0,np.nan); d["mom20_z252"]=(d.mom20-mm)/ms; d["vol20_z252"]=(d.vol20-vm)/vs; d["mom20_accel5"]=d.mom20-d.mom20.shift(5); d["distance_high60"]=d.price/d.price.rolling(60,min_periods=60).max()-1; d["target"]=(d.price.shift(-(DELAY+HOLD))/d.price.shift(-DELAY)-1)*10000-COST; data[s]=d
smh,qqq=data["SMH"],data["QQQ"]; surv=pd.DataFrame({s:data[s].mom20 for s in TRAIN}); breadth=(surv>0).mean(axis=1)
for s in (*TRAIN,*EXT):
 d=data[s]; d["rs_smh20"]=d.mom20-smh.mom20; d["rs_smh60"]=d.mom60-smh.mom60; d["rs_qqq20"]=d.mom20-qqq.mom20; d["rs_qqq60"]=d.mom60-qqq.mom60; d["smh_mom20"]=smh.mom20; d["smh_mom100"]=smh.mom100; d["qqq_mom20"]=qqq.mom20; d["qqq_mom100"]=qqq.mom100; d["survivor_breadth_positive20"]=breadth; d["survivor_cross_section_mom20_pct"]=[np.nan if pd.isna(v) else float((surv.iloc[i]<=v).mean()) for i,v in enumerate(d.mom20)]
folds=bounds(len(close))
def frame(ss):
 rr=[]
 for s in ss:
  d=data[s].copy(); d["symbol"]=s; d["i"]=np.arange(len(d)); fc=np.zeros(len(d),dtype=int)
  for f,(a,b) in enumerate(folds,1): fc[a:max(a,b-(DELAY+HOLD))]=f
  d["fold"]=fc; rr.append(d[d.fold>0][["symbol","i","fold",*FEATURES,"target"]])
 return pd.concat(rr,ignore_index=True).replace([np.inf,-np.inf],np.nan).dropna(subset=FEATURES+["target"])
train,test=frame(TRAIN),frame(EXT); per=[]
for s in EXT:
 fr=[]; A=[];B=[];AO=[];BO=[]
 for f in range(EVAL_FIRST,FOLDS+1):
  start,_=folds[f-1]; tr=train[train.i<start-PURGE]; te=test[(test.symbol==s)&(test.fold==f)].copy(); full=fit(tr,FEATURES).predict(te[FEATURES].to_numpy(float)); simple=fit(tr,["mom20"]).predict(te[["mom20"]].to_numpy(float)); fm=full>0; n=int(fm.sum()); si=np.argsort(simple)[-n:] if n else np.array([],int); truth=te.target.to_numpy(float); fv=truth[fm]; sv=truth[si] if n else np.array([]); prior=data[s].iloc[:start-PURGE].mom20.dropna(); th=float(prior.quantile(.70)); outside=te.mom20.to_numpy(float)<th; no=int((fm&outside).sum()); elig=np.flatnonzero(outside); soi=elig[np.argsort(simple[elig])[-no:]] if no else np.array([],int); fo=truth[fm&outside]; so=truth[soi] if no else np.array([]); A.extend(fv);B.extend(sv);AO.extend(fo);BO.extend(so); fr.append({"fold":f,"matched_count":n,"incremental_bps":None if not n else float(fv.mean()-sv.mean()),"outside_matched_count":no,"outside_incremental_bps":None if not no else float(fo.mean()-so.mean())})
 A,B,AO,BO=map(lambda x:np.asarray(x,float),(A,B,AO,BO)); pf=sum(r["incremental_bps"] is not None and r["incremental_bps"]>0 for r in fr); po=sum(r["outside_incremental_bps"] is not None and r["outside_incremental_bps"]>0 for r in fr); passed=bool(len(AO)>=20 and AO.mean()>BO.mean() and pf>=3 and po>=3); per.append({"symbol":s,"pass":passed,"full_mean_bps":float(A.mean()),"mom20_count_matched_mean_bps":float(B.mean()),"incremental_mean_bps":float(A.mean()-B.mean()),"full_outside_mean_bps":float(AO.mean()),"mom20_outside_count_matched_mean_bps":float(BO.mean()),"outside_incremental_mean_bps":float(AO.mean()-BO.mean()),"positive_incremental_folds":pf,"positive_outside_incremental_folds":po,"folds":fr})
passing=sum(x["pass"] for x in per); out={"schema":"research.p188_nonsemi_incremental_mom20_control_r1","parent":"P188","hypothesis":"The full frozen semiconductor-trained state vector adds incremental selection information over mom20 alone specifically on the heterogeneous non-semiconductor universe where P184 transported 6/6.","contract":{"train_universe":list(TRAIN),"external_universe":list(EXT),"full_model":"Ridge(alpha=10)+StandardScaler frozen feature family","simple_control":"same Ridge on mom20 only","matching":"exact selected-state count by external symbol/fold; outside-top30 exact count matched among causal below-threshold states","target":"fixed20 +1-session net 25 bps","gate":">=4/6 symbols with positive outside incremental mean and >=3/5 positive full-vs-simple and outside-incremental folds","no_search":True},"source":{"provider":"Yahoo Finance via yfinance; research-only","rows":len(close),"last":str(close.index[-1]),"panel_sha256":hashlib.sha256(close.to_csv().encode()).hexdigest()},"per_symbol":per,"passing_symbols":passing,"decision":"P188_NONSEMI_MULTIFEATURE_INCREMENTAL_SUPPORTED" if passing>=4 else "P188_NONSEMI_MULTIFEATURE_INCREMENTAL_NOT_SUPPORTED","boundaries":{"portfolio_ranking":False,"runtime":False,"broker":False,"live_trading":False}}; OUT.parent.mkdir(exist_ok=True); OUT.write_text(json.dumps(out,sort_keys=True,indent=2)); print(json.dumps(out,sort_keys=True))
