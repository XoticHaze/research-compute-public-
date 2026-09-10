import hashlib,json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

TRAIN=("AMAT","APH","KLAC","LRCX","TXN","NXPI","ADI"); EXT=("NVDA","AMD","MU","AVGO","MRVL","MCHP"); CTX=("SMH","QQQ")
HOLD=20; DELAY=1; FOLDS=6; MIN_TRAIN=756; PURGE=22; COST=25.; EVAL_FIRST=2
FEATURES=["mom5","mom20","mom60","mom100","mom20_z252","mom20_accel5","vol20","vol20_z252","distance_high60","rs_smh20","rs_smh60","rs_qqq20","rs_qqq60","smh_mom20","smh_mom100","qqq_mom20","qqq_mom100","survivor_breadth_positive20","survivor_cross_section_mom20_pct"]
OUT=Path("artifacts/p185_entry_incremental_mom20_control_r1.json")

def fs(n):
 e=np.linspace(MIN_TRAIN,n-(HOLD+DELAY+1),FOLDS+1,dtype=int); return [(int(e[i]),int(e[i+1])) for i in range(FOLDS)]
def fit(t,features):
 m=Pipeline([("scale",StandardScaler()),("ridge",Ridge(alpha=10.0))]); m.fit(t[features].to_numpy(float),t.target.to_numpy(float)); return m
symbols=(*TRAIN,*EXT,*CTX); raw=yf.download(list(symbols),start="2014-01-01",end="2026-09-03",auto_adjust=True,progress=False,group_by="column",threads=False); close=raw["Close"][list(symbols)] if isinstance(raw.columns,pd.MultiIndex) else raw[list(symbols)]; close=close.dropna(how="all").ffill().dropna(); cal=pd.DatetimeIndex(pd.to_datetime(close.index,utc=True)); data={}
for s in symbols:
 d=pd.DataFrame({"price":close[s].to_numpy(float)}); d["ret1"]=d.price.pct_change()
 for n in (5,20,60,100): d[f"mom{n}"]=d.price.pct_change(n)
 d["vol20"]=d.ret1.rolling(20,min_periods=20).std(ddof=0); pm,pv=d.mom20.shift(1),d.vol20.shift(1); mm,ms=pm.rolling(252,min_periods=126).mean(),pm.rolling(252,min_periods=126).std(ddof=0).replace(0,np.nan); vm,vs=pv.rolling(252,min_periods=126).mean(),pv.rolling(252,min_periods=126).std(ddof=0).replace(0,np.nan); d["mom20_z252"]=(d.mom20-mm)/ms; d["vol20_z252"]=(d.vol20-vm)/vs; d["mom20_accel5"]=d.mom20-d.mom20.shift(5); d["distance_high60"]=d.price/d.price.rolling(60,min_periods=60).max()-1; d["target"]=(d.price.shift(-(DELAY+HOLD))/d.price.shift(-DELAY)-1)*10000-COST; data[s]=d
smh,qqq=data["SMH"],data["QQQ"]; surv=pd.DataFrame({s:data[s].mom20 for s in TRAIN}); breadth=(surv>0).mean(axis=1)
for s in (*TRAIN,*EXT):
 d=data[s]; d["rs_smh20"]=d.mom20-smh.mom20; d["rs_smh60"]=d.mom60-smh.mom60; d["rs_qqq20"]=d.mom20-qqq.mom20; d["rs_qqq60"]=d.mom60-qqq.mom60; d["smh_mom20"]=smh.mom20; d["smh_mom100"]=smh.mom100; d["qqq_mom20"]=qqq.mom20; d["qqq_mom100"]=qqq.mom100; d["survivor_breadth_positive20"]=breadth; d["survivor_cross_section_mom20_pct"]=[np.nan if pd.isna(v) else float((surv.iloc[i]<=v).mean()) for i,v in enumerate(d.mom20)]
folds=fs(len(cal))
def frame(ss):
 rr=[]
 for s in ss:
  d=data[s].copy(); d["symbol"]=s; d["i"]=np.arange(len(d)); fc=np.zeros(len(d),dtype=int)
  for f,(a,b) in enumerate(folds,1): fc[a:max(a,b-(DELAY+HOLD))]=f
  d["fold"]=fc; rr.append(d[d.fold>0][["symbol","i","fold",*FEATURES,"target"]])
 return pd.concat(rr,ignore_index=True).replace([np.inf,-np.inf],np.nan).dropna(subset=FEATURES+["target"])
train,test=frame(TRAIN),frame(EXT); rows=[]
for s in EXT:
 fr=[]; full_all=[]; simple_all=[]; full_out=[]; simple_out=[]
 for f in range(EVAL_FIRST,FOLDS+1):
  start,_=folds[f-1]; tr=train[train.i<start-PURGE]; te=test[(test.symbol==s)&(test.fold==f)].copy(); full=fit(tr,FEATURES).predict(te[FEATURES].to_numpy(float)); simp=fit(tr,["mom20"]).predict(te[["mom20"]].to_numpy(float)); full_mask=full>0; n=int(full_mask.sum()); simple_idx=np.argsort(simp)[-n:] if n else np.array([],dtype=int); fv=te.target.to_numpy(float)[full_mask]; sv=te.target.to_numpy(float)[simple_idx] if n else np.array([]); prior=data[s].iloc[:start-PURGE].mom20.dropna(); th=float(prior.quantile(.70)); outside=(te.mom20.to_numpy(float)<th); fn=int((full_mask&outside).sum()); eligible=np.flatnonzero(outside); simp_out_idx=eligible[np.argsort(simp[eligible])[-fn:]] if fn else np.array([],dtype=int); fov=te.target.to_numpy(float)[full_mask&outside]; sov=te.target.to_numpy(float)[simp_out_idx] if fn else np.array([]); full_all.extend(fv); simple_all.extend(sv); full_out.extend(fov); simple_out.extend(sov); fr.append({"fold":f,"matched_count":n,"full_mean_bps":None if not n else float(fv.mean()),"mom20_only_mean_bps":None if not n else float(sv.mean()),"full_minus_mom20_bps":None if not n else float(fv.mean()-sv.mean()),"outside_matched_count":fn,"full_outside_mean_bps":None if not fn else float(fov.mean()),"mom20_only_outside_mean_bps":None if not fn else float(sov.mean()),"outside_incremental_bps":None if not fn else float(fov.mean()-sov.mean())})
 fa,sa,fo,so=map(lambda x:np.asarray(x,float),(full_all,simple_all,full_out,simple_out)); pf=sum(r["full_minus_mom20_bps"] is not None and r["full_minus_mom20_bps"]>0 for r in fr); po=sum(r["outside_incremental_bps"] is not None and r["outside_incremental_bps"]>0 for r in fr); passed=bool(len(fo)>=20 and fo.mean()>so.mean() and pf>=3 and po>=3); rows.append({"symbol":s,"incremental_pass":passed,"full_trades":len(fa),"full_mean_bps":float(fa.mean()),"mom20_matched_mean_bps":float(sa.mean()),"incremental_mean_bps":float(fa.mean()-sa.mean()),"outside_trades":len(fo),"full_outside_mean_bps":float(fo.mean()),"mom20_outside_matched_mean_bps":float(so.mean()),"outside_incremental_mean_bps":float(fo.mean()-so.mean()),"positive_incremental_folds":pf,"positive_outside_incremental_folds":po,"folds":fr})
passing=sum(r["incremental_pass"] for r in rows); out={"schema":"research.p185_entry_incremental_mom20_control_r1","parent":"P185","hypothesis":"The frozen multifeature semiconductor Ridge contributes economically useful information beyond a softer single-feature 20-session momentum ranking, rather than merely relaxing the incumbent top-30% threshold.","contract":{"train_universe":list(TRAIN),"external_universe":list(EXT),"full_model":"Ridge(alpha=10)+StandardScaler exact frozen feature family","simple_control":"Ridge(alpha=10)+StandardScaler on mom20 only","matching":"within each symbol/fold simple control receives exactly the same selected-trade count as the full predicted-value>0 model; outside-frozen comparison also matches exact count among states below the causal prior-only 70th percentile mom20 threshold","target":"fixed20 +1-session entry net 25 bps","gate":">=4/6 symbols with positive aggregate outside-frozen incremental mean and >=3/5 positive full-vs-simple folds plus >=3/5 positive outside-frozen incremental folds","no_feature_model_threshold_count_or_window_search":True},"source":{"provider":"Yahoo Finance via yfinance; research-only","rows":len(close),"last":str(close.index[-1]),"panel_sha256":hashlib.sha256(close.to_csv().encode()).hexdigest()},"per_symbol":rows,"passing_symbols":passing,"decision":"P185_MULTIFEATURE_INCREMENTAL_SUPPORTED" if passing>=4 else "P185_MULTIFEATURE_INCREMENTAL_NOT_SUPPORTED","boundaries":{"portfolio_ranking":False,"runtime":False,"broker":False,"live_trading":False}}; OUT.parent.mkdir(exist_ok=True); OUT.write_text(json.dumps(out,sort_keys=True,indent=2)); print(json.dumps(out,sort_keys=True))
