import json,math,hashlib
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
TARGET=.12; COST=(10,25,50); W={'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01','2022':'2022-01-01'}
def met(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); c=float(e.iloc[-1]**(12/len(r))-1); v=float(r.std(ddof=0)*math.sqrt(12)); d=float((e/e.cummax()-1).min()); return {'cagr':c,'vol':v,'sharpe':float(r.mean()*12/v) if v else None,'maxdd':d}
def build():
 d=yf.download('SPY',start='2005-01-01',auto_adjust=True,progress=False,threads=False); px=d['Close']; px=px.iloc[:,0] if isinstance(px,pd.DataFrame) else px; px=px.astype(float).dropna(); last=pd.Timestamp(px.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cut=last.to_period('M').start_time-pd.Timedelta(days=1); px=px.loc[px.index<=cut]; rv=px.pct_change(fill_method=None).rolling(63,min_periods=50).std(ddof=0)*math.sqrt(252); m=px.resample('ME').last(); v=rv.resample('ME').last().reindex(m.index); ret=m.pct_change(fill_method=None); prev=0.; rows=[]
 for i,x in enumerate(m.index[:-1]):
  if pd.isna(v.loc[x]) or v.loc[x]<=0: continue
  w=float(np.clip(TARGET/v.loc[x],0,1)); n=m.index[i+1]; r=float(ret.loc[n]); rows.append({'date':n,'gross':w*r,'turnover':abs(w-prev),'weight':w,'spy':r}); prev=w
 return pd.DataFrame(rows).set_index('date'),px,cut
def ev(z,c):
 net=z.gross-z.turnover*c/10000; mean=float(z.weight.mean()); matched=mean*z.spy; x={'candidate':met(net),'matched':met(matched),'spy':met(z.spy),'mean_exposure':mean,'annualized_turnover':float(z.turnover.mean()*12),'excess_matched':met(net)['cagr']-met(matched)['cagr'],'excess_spy':met(net)['cagr']-met(z.spy)['cagr']}; fs=[]
 for i,ix in enumerate(np.array_split(np.arange(len(z)),5),1):
  a=z.iloc[ix]; n=a.gross-a.turnover*c/10000; mm=float(a.weight.mean())*a.spy; fs.append({'fold':i,'matched_excess':met(n)['cagr']-met(mm)['cagr']})
 x['positive_matched_folds']=sum(f['matched_excess']>0 for f in fs); x['folds']=fs; return x
def main():
 q,px,cut=build(); t={w:{str(c):ev(q.loc[pd.Timestamp(s):],c) for c in COST} for w,s in W.items()}; a=t['2015']['25']; b=t['2020']['25']; ok=a['excess_matched']>0 and a['positive_matched_folds']>=3 and b['excess_matched']>0 and b['positive_matched_folds']>=3; dec='P165_VOL_MANAGED_SPY_SUPPORTED_FOR_INDEPENDENT_VALIDATION' if ok else 'P165_VOL_MANAGED_SPY_NOT_SUPPORTED'; o={'schema':'research.p165_vol_managed_spy_r1','parent':'P165','hypothesis':'A fixed 12% annualized-volatility target, long-only monthly SPY exposure using trailing 63-session realized volatility creates after-cost excess versus static SPY held at the same mean capital exposure.','contract':{'target_vol':TARGET,'lookback_sessions':63,'exposure_bounds':[0,1],'rebalance':'monthly completed-month information','cost_bps':list(COST),'matched':'static SPY at evaluated mean exposure, residual cash','opportunity':'full SPY','windows':list(W),'folds':5,'no_target_lookback_bound_cost_or_window_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(cut.date()),'price_sha256':hashlib.sha256(px.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest()},'tests':t,'decision':dec}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p165_vol_managed_spy_r1.json').write_text(json.dumps(o,indent=2,sort_keys=True)); print(json.dumps(o,sort_keys=True))
if __name__=='__main__': main()
