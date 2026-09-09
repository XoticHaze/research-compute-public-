from __future__ import annotations
import json,math,hashlib
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
COSTS=(5,10,25); BETA_WIN=252; Z_WIN=60; ENTRY=1.0

def met(r):
 r=pd.Series(r,dtype=float).dropna(); n=len(r); eq=(1+r).cumprod(); ann=(1+r).prod()**(252/n)-1; vol=r.std(ddof=1)*math.sqrt(252); return {'cagr':float(ann),'sharpe_rf0':float(r.mean()*252/vol) if vol else None,'maxdd':float((eq/eq.cummax()-1).min()),'annual_vol':float(vol)}
def fold_stats(q,bp):
 ids=np.array_split(np.arange(len(q)),5); o=[]
 for j,ix in enumerate(ids,1):
  a=q.iloc[ix]; n=a.gross-a.turn*bp/10000; o.append({'fold':j,'cagr':met(n)['cagr'],'sharpe':met(n)['sharpe_rf0']})
 return o
def evaluate(q):
 z={'days':len(q),'average_gross_exposure':float(q.gex.mean()),'active_fraction':float((q.gex>0).mean()),'controls':{'static_50_50_gdx_gld':met(q.static),'spy':met(q.spy)},'costs':{}}
 for bp in COSTS:
  n=q.gross-q.turn*bp/10000; m=met(n); fs=fold_stats(q,bp); z['costs'][str(bp)]={'candidate':m,'positive_cagr_folds':sum(x['cagr']>0 for x in fs),'positive_sharpe_folds':sum(x['sharpe']>0 for x in fs),'folds':fs}
 return z
def main():
 raw=yf.download(['GDX','GLD','SPY'],start='2006-05-22',auto_adjust=True,progress=False,threads=False)['Close'].dropna().astype(float)
 lp=np.log(raw[['GDX','GLD']]); x=lp.GLD; y=lp.GDX
 mx=x.rolling(BETA_WIN).mean(); my=y.rolling(BETA_WIN).mean(); beta=((x*y).rolling(BETA_WIN).mean()-mx*my)/((x*x).rolling(BETA_WIN).mean()-mx*mx); alpha=my-beta*mx; resid=y-(alpha+beta*x)
 rz=(resid-resid.rolling(Z_WIN).mean())/resid.rolling(Z_WIN).std(ddof=1)
 rows=[]; prev=np.array([0.0,0.0])
 for i in range(BETA_WIN+Z_WIN,len(raw)-1):
  b=float(beta.iloc[i]); z=float(rz.iloc[i]);
  if not np.isfinite(b) or not np.isfinite(z): continue
  if z<=-ENTRY: direction=1.0
  elif z>=ENTRY: direction=-1.0
  else: direction=0.0
  if direction:
   den=1+abs(b); w=np.array([direction/den,-direction*b/den])
  else: w=np.array([0.0,0.0])
  r=(raw[['GDX','GLD']].iloc[i+1]/raw[['GDX','GLD']].iloc[i]-1).to_numpy(float); gross=float(w@r); turn=float(np.abs(w-prev).sum()); static=float(r.mean()); spy=float(raw.SPY.iloc[i+1]/raw.SPY.iloc[i]-1); rows.append({'date':raw.index[i+1],'gross':gross,'turn':turn,'static':static,'spy':spy,'gex':float(np.abs(w).sum())}); prev=w
 f=pd.DataFrame(rows).set_index('date'); tests={k:evaluate(f.loc[v:]) for k,v in {'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01'}.items()}; a=tests['2015']['costs']['10']; b=tests['2020']['costs']['10']; ok=a['candidate']['cagr']>0 and b['candidate']['cagr']>0 and a['positive_cagr_folds']>=3 and b['positive_cagr_folds']>=3 and b['candidate']['sharpe_rf0']>0.5
 out={'schema':'research.p103_gdx_gld_residual_rv_r1','parent':'P103','hypothesis':'A fixed causal residual mean-reversion spread between gold miners and gold produces positive after-cost market-neutral alpha distinct from directional equity timing.','contract':{'pair':['GDX','GLD'],'rolling_log_price_ols_days':BETA_WIN,'residual_z_days':Z_WIN,'entry_abs_z':ENTRY,'signal':'close t residual z; enter normalized beta spread for t to t+1 only when |z|>=1','gross_exposure_normalized':1.0,'cost_bps_per_unit_turnover':list(COSTS),'controls':['cash alpha hurdle (0)','static 50/50 GDX+GLD','SPY opportunity cost'],'windows':['2010','2015','2020'],'folds':5,'no_parameter_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_date':str(raw.index[-1].date()),'panel_sha256':hashlib.sha256(raw.reset_index().to_csv(index=False).encode()).hexdigest()},'tests':tests,'decision':'P103_GDX_GLD_RV_SUPPORTED_FOR_FURTHER_FALSIFICATION' if ok else 'P103_GDX_GLD_RV_NOT_SUPPORTED'}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p103_gdx_gld_residual_rv_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True,allow_nan=False))
if __name__=='__main__': main()
