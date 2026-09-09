from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
CROSS=("SPY","QQQ","TLT","GLD","DBC"); IND=("SMH","XBI","ITB","KRE","ITA","IGV","IWM","XRT"); ALL=tuple(dict.fromkeys((*CROSS,*IND)))
def metrics(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); y=len(r)/12; c=float(e.iloc[-1]**(1/y)-1); a=float(r.mean()*12); v=float(r.std(ddof=0)*math.sqrt(12)); dd=e/e.cummax()-1; return {"cagr":c,"annualized_mean":a,"annualized_vol":v,"sharpe_rf0":a/v if v else float('nan'),"max_drawdown_monthly":float(dd.min())}
def build():
 d=yf.download(list(ALL),start="2006-01-01",auto_adjust=True,progress=False,threads=False); close=d["Close"] if isinstance(d.columns,pd.MultiIndex) else d[["Close"]]; close=close.loc[:,list(ALL)].dropna(how="all").astype(float); close.index=pd.DatetimeIndex(close.index).tz_localize(None); m=close.resample("ME").last(); dr=close.pct_change(); vol=(dr.rolling(126,min_periods=100).std(ddof=0)*math.sqrt(252)).resample("ME").last(); trend=(close/close.rolling(200,min_periods=160).mean()-1).resample("ME").last(); dd=(close/close.rolling(126,min_periods=100).max()-1).resample("ME").last(); mom=m.pct_change(6); pc={s:0. for s in CROSS}; pi={s:0. for s in IND}; rows=[]
 for i,dt in enumerate(m.index[:-1]):
  nxt=m.index[i+1]; bc=pd.DataFrame({"mom6":mom.loc[dt,list(CROSS)],"trend200":trend.loc[dt,list(CROSS)],"low_vol6":-vol.loc[dt,list(CROSS)],"drawdown6":dd.loc[dt,list(CROSS)]}); bi=pd.DataFrame({"mom6":mom.loc[dt,list(IND)],"trend200":trend.loc[dt,list(IND)],"low_vol6":-vol.loc[dt,list(IND)],"drawdown6":dd.loc[dt,list(IND)]}); r=m.loc[nxt,list(ALL)]/m.loc[dt,list(ALL)]-1
  if bc.isna().any().any() or bi.isna().any().any() or r.isna().any(): continue
  cc=bc.rank(pct=True).mean(axis=1).sort_values(ascending=False).head(2).index; ci=bi.rank(pct=True).mean(axis=1).sort_values(ascending=False).head(3).index; wc={s:(.5 if s in cc else 0.) for s in CROSS}; wi={s:(1/3 if s in ci else 0.) for s in IND}; tc=.5*sum(abs(wc[s]-pc[s]) for s in CROSS); ti=.5*sum(abs(wi[s]-pi[s]) for s in IND); gc=sum(wc[s]*float(r[s]) for s in CROSS); gi=sum(wi[s]*float(r[s]) for s in IND); rows.append({"date":nxt,"cross_gross":gc,"industry_gross":gi,"cross_turn":tc,"industry_turn":ti,"control":.5*float(r.loc[list(CROSS)].mean())+.5*float(r.loc[list(IND)].mean())}); pc,pi=wc,wi
 return pd.DataFrame(rows).set_index("date")
def rolling_fraction(a,b,w):
 vals=[]
 for i in range(w,len(a)+1): vals.append(metrics(a.iloc[i-w:i])["cagr"]-metrics(b.iloc[i-w:i])["cagr"])
 return {"positive_fraction":float(np.mean(np.array(vals)>0)),"median_excess_cagr":float(np.median(vals)),"windows":len(vals)}
def block_bootstrap(a,b,reps=5000,block=6,seed=143):
 x=np.asarray(a-b,float); n=len(x); rng=np.random.default_rng(seed); stats=[]
 for _ in range(reps):
  z=[]
  while len(z)<n:
   st=int(rng.integers(0,max(1,n-block+1))); z.extend(x[st:st+block])
  stats.append(float(np.mean(z[:n])*12))
 arr=np.array(stats); return {"annualized_mean_excess":float(x.mean()*12),"bootstrap_95pct":[float(np.quantile(arr,.025)),float(np.quantile(arr,.975))],"p_excess_le_zero":float(np.mean(arr<=0)),"reps":reps,"block_months":block}
def main():
 f=build(); out={"schema":"research.p143_p89_ensemble_serial_persistence_r1","parent_ids":["P46","P47","P89","P143"],"contract":{"ensemble":"frozen static 50/50 original P46/P47 return streams","matched_control":"frozen static 50/50 exact equal-weight parent-universe controls","comparison":"original P46 cross parent","costs_bps":[25,50],"rolling_windows_months":[36,60],"moving_block_bootstrap":{"reps":5000,"block_months":6,"seed":143},"no_weight_factor_or_parent_tuning":True},"window":{"start":str(f.index.min().date()),"end":str(f.index.max().date()),"months":len(f)},"costs":{}}
 for bps in (25,50):
  cross=f.cross_gross-f.cross_turn*bps/10000; ind=f.industry_gross-f.industry_turn*bps/10000; ens=.5*cross+.5*ind; ctrl=f.control; em,cm,bm=metrics(ens),metrics(cross),metrics(ctrl); out["costs"][str(bps)]={"ensemble":em,"cross_parent":cm,"matched_control":bm,"excess_cagr_vs_control":em["cagr"]-bm["cagr"],"excess_cagr_vs_cross":em["cagr"]-cm["cagr"],"rolling36_vs_control":rolling_fraction(ens,ctrl,36),"rolling60_vs_control":rolling_fraction(ens,ctrl,60),"rolling36_vs_cross":rolling_fraction(ens,cross,36),"rolling60_vs_cross":rolling_fraction(ens,cross,60),"bootstrap_vs_control":block_bootstrap(ens,ctrl),"bootstrap_vs_cross":block_bootstrap(ens,cross,seed=144)}
 p=out["costs"]["25"]; q=out["costs"]["50"]; support=p["excess_cagr_vs_control"]>0 and q["excess_cagr_vs_control"]>0 and p["rolling60_vs_control"]["positive_fraction"]>=.6 and p["bootstrap_vs_control"]["p_excess_le_zero"]<=.1 and p["rolling60_vs_cross"]["positive_fraction"]>=.5 and p["bootstrap_vs_cross"]["p_excess_le_zero"]<=.25
 out["decision"]="P89_ENSEMBLE_SERIAL_PERSISTENCE_SUPPORTED" if support else "P89_ENSEMBLE_SERIAL_PERSISTENCE_INSUFFICIENT"
 Path("artifacts").mkdir(exist_ok=True); Path("artifacts/p143_p89_ensemble_serial_persistence_r1.json").write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({"decision":out["decision"],"window":out["window"],"25":out["costs"]["25"],"50":out["costs"]["50"]},sort_keys=True))
if __name__=="__main__": main()
