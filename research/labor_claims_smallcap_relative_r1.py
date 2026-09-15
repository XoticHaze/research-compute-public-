from __future__ import annotations
import io,json,math
from pathlib import Path
import pandas as pd,requests,yfinance as yf
CSV="https://fred.stlouisfed.org/graph/fredgraph.csv?id=ICNSA"
ASSETS=["IWM","SPY"]; COST=25/10000
FOLDS=[("2010-01-01","2014-12-31"),("2015-01-01","2019-12-31"),("2020-01-01","2022-12-31"),("2023-01-01","2026-09-11")]
def cagr(r):
 r=r.dropna(); years=(r.index[-1]-r.index[0]).days/365.25 if len(r)>1 else 0; total=float((1+r).prod()); return None if years<=0 or total<=0 else total**(1/years)-1
def stats(r):
 r=r.dropna(); eq=(1+r).cumprod(); return {"days":len(r),"cagr":cagr(r),"vol":None if len(r)<2 else float(r.std()*math.sqrt(252)),"max_drawdown":None if r.empty else float((eq/eq.cummax()-1).min())}
def evalw(d,a,b,w):
 z=d.loc[a:b]; matched=w*z.IWM+(1-w)*z.SPY; sc=cagr(z.strategy); mc=cagr(matched); sp=cagr(z.SPY)
 return {"window":[a,b],"strategy":stats(z.strategy),"matched_static":stats(matched),"IWM":stats(z.IWM),"SPY":stats(z.SPY),"matched_excess_cagr":None if sc is None or mc is None else sc-mc,"spy_excess_cagr":None if sc is None or sp is None else sc-sp,"mean_iwm_exposure":None if z.empty else float(z.iwm.mean()),"switches":int(z.switch.sum()) if not z.empty else 0}
def main():
 r=requests.get(CSV,timeout=(15,60)); r.raise_for_status(); x=pd.read_csv(io.BytesIO(r.content)); x.columns=["date","claims"]; x.date=pd.to_datetime(x.date); x.claims=pd.to_numeric(x.claims,errors="coerce"); s=x.dropna().set_index("date").claims.sort_index()
 four=s.rolling(4,min_periods=4).sum(); yoy=four/four.shift(52); state=(yoy.shift(2)<=1.0).astype(float).dropna() # 1=IWM, 0=SPY; two-observation revision guard
 raw=yf.download(ASSETS,start="2008-01-01",end="2026-09-12",auto_adjust=True,progress=False,threads=False); close=raw["Close"] if isinstance(raw.columns,pd.MultiIndex) else raw; ret=close[ASSETS].dropna(how="any").pct_change(fill_method=None).dropna(how="any")
 sig=pd.Series(index=ret.index,dtype=float); events=[]
 for obs,v in state.items():
  eligible=ret.index[ret.index>obs+pd.Timedelta(days=5)]
  if len(eligible): sig.loc[eligible[0]]=float(v); events.append((obs,eligible[0],v))
 sig=sig.ffill(); first=sig.first_valid_index(); d=ret.loc[first:].copy(); d["iwm"]=sig.loc[d.index]; d=d.dropna(subset=["iwm"]); d["switch"]=d.iwm.diff().abs().fillna(0); d["strategy"]=d.iwm*d.IWM+(1-d.iwm)*d.SPY-d.switch*COST
 w=float(d.iwm.mean()); overall=evalw(d,str(d.index.min().date()),"2026-09-11",w); folds=[evalw(d,a,b,w) for a,b in FOLDS]; pos=sum(f["matched_excess_cagr"] is not None and f["matched_excess_cagr"]>0 for f in folds); passed=overall["matched_excess_cagr"] is not None and overall["matched_excess_cagr"]>0 and overall["spy_excess_cagr"] is not None and overall["spy_excess_cagr"]>0 and pos>=3
 out={"schema":"research.labor_claims_smallcap_relative_r1","identity":"LABOR_CLAIMS_SMALLCAP_RELATIVE_R1","claim":"A causally lagged deterioration in actual initial unemployment claims should identify periods when small caps underperform large caps after switching costs.","source":{"fred_series":"ICNSA","first":str(s.index.min().date()),"last":str(s.index.max().date()),"observations":len(s)},"contract":{"signal":"4-week ICNSA sum / 4-week sum 52 observations earlier, shifted 2 observations for revision guard","iwm_when":"ratio <= 1.0","spy_when":"ratio > 1.0","availability":"first trading session strictly after indexed observation + 5 calendar days","switch_cost_bps":25,"no_parameter_rescue":True},"diagnostics":{"effective_events":len(events),"mean_iwm_exposure":w,"switches":int(d.switch.sum())},"overall":overall,"folds":folds,"positive_matched_folds":pos,"decision":"LABOR_CLAIMS_SMALLCAP_RELATIVE_SUPPORTED" if passed else "LABOR_CLAIMS_SMALLCAP_RELATIVE_NOT_SUPPORTED_NO_RESCUE","boundaries":{"portfolio_ranking":False,"allocation_authority":False,"runtime":False,"broker":False,"live_trading":False}}
 Path("artifacts").mkdir(exist_ok=True); Path("artifacts/labor_claims_smallcap_relative_r1.json").write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps({"decision":out["decision"],"matched_excess":overall["matched_excess_cagr"],"spy_excess":overall["spy_excess_cagr"],"positive_folds":pos,"mean_iwm_exposure":w},sort_keys=True))
if __name__=="__main__":main()
