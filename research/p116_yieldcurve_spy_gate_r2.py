from __future__ import annotations
import io,json,math,hashlib,requests
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
COSTS=(10,25,50)
def cg(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1)
def mt(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); v=float(r.std(ddof=1)*math.sqrt(12)); a=float(r.mean()*12); return {'cagr':cg(r),'sharpe_rf0':a/v if v else None,'maxdd':float((e/e.cummax()-1).min())}
def ev(q):
 ex=float(q['exp'].mean()); matched=q['spy']*ex; out={'months':len(q),'avg_exposure':ex,'controls':{'exposure_matched_spy':mt(matched),'full_spy':mt(q['spy'])},'costs':{}}; ids=np.array_split(np.arange(len(q)),5)
 for bp in COSTS:
  n=q['gross']-q['turn']*bp/10000; m=mt(n); fs=[]
  for j,ix in enumerate(ids,1):
   a=q.iloc[ix]; x=a['gross']-a['turn']*bp/10000; z=a['spy']*ex; fs.append({'fold':j,'matched':cg(x)-cg(z),'spy':cg(x)-cg(a['spy'])})
  out['costs'][str(bp)]={'candidate':m,'excess_matched':m['cagr']-out['controls']['exposure_matched_spy']['cagr'],'excess_spy':m['cagr']-out['controls']['full_spy']['cagr'],'positive_matched_folds':sum(x['matched']>0 for x in fs),'positive_spy_folds':sum(x['spy']>0 for x in fs),'folds':fs}
 return out
def main():
 url='https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10,DGS3MO'; resp=requests.get(url,timeout=30); resp.raise_for_status(); rates=pd.read_csv(io.StringIO(resp.text),na_values='.'); date_col=rates.columns[0]; rates[date_col]=pd.to_datetime(rates[date_col]); rates=rates.set_index(date_col).apply(pd.to_numeric,errors='coerce').dropna(); spread=(rates['DGS10']-rates['DGS3MO']).resample('ME').last(); p=yf.download('SPY',start='1993-01-01',auto_adjust=True,progress=False,threads=False)['Close']; p=p.iloc[:,0] if isinstance(p,pd.DataFrame) else p; pm=p.dropna().astype(float).resample('ME').last(); x=pd.concat([pm.rename('px'),spread.rename('spread')],axis=1).dropna(); x['spy']=x['px'].pct_change(); x['exp']=(x['spread'].shift(1)>=0).astype(float); x['turn']=(x['exp']-x['exp'].shift(1).fillna(0)).abs(); x['gross']=x['exp']*x['spy']; q=x[['gross','turn','spy','exp']].dropna(); tests={k:ev(q.loc[v:]) for k,v in {'2000':'2000-01-01','2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01'}.items()}; a=tests['2015']['costs']['25']; b=tests['2020']['costs']['25']; ok=a['excess_matched']>0 and b['excess_matched']>0 and a['positive_matched_folds']>=3 and b['positive_matched_folds']>=3 and b['excess_spy']>0
 out={'schema':'research.p116_yieldcurve_spy_gate_r2','parent':'P116','hypothesis':'A fixed causal 10y-minus-3m Treasury curve gate creates durable after-cost SPY timing excess beyond identical average capital usage and full SPY.','contract':{'asset':'SPY','macro_source':'FRED DGS10 and DGS3MO','signal':'long SPY for month t only when prior month-end 10y minus 3m spread is nonnegative, else cash','cost_bps_per_state_change':list(COSTS),'matched_control':'continuous SPY scaled to candidate average exposure','opportunity_control':'full SPY','windows':['2000','2010','2015','2020'],'folds':5,'no_threshold_search':True},'source':{'fred_url':url,'fred_sha256':hashlib.sha256(resp.content).hexdigest(),'fred_date_column_observed':date_col,'spy_provider':'Yahoo Finance via yfinance; research-only','last_month':str(q.index[-1].date())},'tests':tests,'decision':'P116_YIELDCURVE_SPY_GATE_SUPPORTED_FOR_FURTHER_FALSIFICATION' if ok else 'P116_YIELDCURVE_SPY_GATE_NOT_SUPPORTED'}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p116_yieldcurve_spy_gate_r2.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True,allow_nan=False))
if __name__=='__main__': main()
