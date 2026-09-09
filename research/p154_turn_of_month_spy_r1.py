from __future__ import annotations
import hashlib,json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
COSTS=(25,50,100); WINDOWS={'2005':'2005-01-01','2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01','2022':'2022-01-01'}
def cagr_daily(r):
 r=pd.Series(r,dtype=float).dropna(); years=len(r)/252; return float((1+r).prod()**(1/years)-1) if years else float('nan')
def stats(r):
 r=pd.Series(r,dtype=float).dropna(); eq=(1+r).cumprod(); vol=float(r.std(ddof=1)*math.sqrt(252)); return {'cagr':cagr_daily(r),'sharpe_rf0':float(r.mean()*252/vol) if vol else None,'maxdd':float((eq/eq.cummax()-1).min())}
def evaluate(q,cost_bps):
 z=q.copy(); z['net']=z.gross-z.turnover*cost_bps/10000; ex=float(z.pos.mean()); z['matched']=ex*z.spy
 out={k:stats(z[k]) for k in ('net','matched','spy')}; out.update({'excess_matched':out['net']['cagr']-out['matched']['cagr'],'excess_spy':out['net']['cagr']-out['spy']['cagr'],'days':len(z),'mean_exposure':ex,'annualized_turnover':float(z.turnover.mean()*252)})
 folds=[]
 for j,idx in enumerate(np.array_split(np.arange(len(z)),5),1):
  a=z.iloc[idx]; e=float(a.pos.mean()); m=e*a.spy; folds.append({'fold':j,'matched_excess':cagr_daily(a.net)-cagr_daily(m),'spy_excess':cagr_daily(a.net)-cagr_daily(a.spy)})
 out['positive_matched_folds']=sum(x['matched_excess']>0 for x in folds); out['positive_spy_folds']=sum(x['spy_excess']>0 for x in folds); out['folds']=folds; return out
def main():
 px=yf.download('SPY',start='1999-01-01',auto_adjust=True,progress=False,threads=False)['Close']; px=px.iloc[:,0] if isinstance(px,pd.DataFrame) else px; px=px.dropna().astype(float)
 last=pd.Timestamp(px.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cut=last.to_period('M').start_time-pd.Timedelta(days=1); px=px.loc[px.index<=cut]; ret=px.pct_change(fill_method=None).fillna(0.0)
 frame=pd.DataFrame({'spy':ret}); grp=frame.groupby(frame.index.to_period('M'),sort=False); first3=grp.cumcount()<3; rev=grp.cumcount(ascending=False)==0; frame['pos']=(first3|rev).astype(float); frame['gross']=frame.pos*frame.spy; frame['turnover']=frame.pos.diff().abs().fillna(frame.pos)
 tests={w:{str(c):evaluate(frame.loc[pd.Timestamp(s):],c) for c in COSTS} for w,s in WINDOWS.items()}; a=tests['2015']['50']; b=tests['2020']['50']
 decision='P154_TURN_OF_MONTH_SUPPORTED_FOR_INDEPENDENT_VALIDATION' if a['excess_matched']>0 and a['positive_matched_folds']>=3 and b['excess_matched']>0 and b['positive_matched_folds']>=3 and a['net']['sharpe_rf0']>a['matched']['sharpe_rf0'] else 'P154_TURN_OF_MONTH_NOT_SUPPORTED'
 out={'schema':'research.p154_turn_of_month_spy_r1','parent':'P154','hypothesis':'Holding SPY only on each month first three trading sessions and final trading session produces after-cost excess versus static SPY at identical average capital usage, consistent with a turn-of-month calendar effect.','contract':{'position_days':'first 3 trading sessions and final trading session of each calendar month','return_convention':'close-to-close adjusted SPY return on held trading sessions','cost_bps':list(COSTS),'turnover_cost':'charged on absolute daily position change','matched_control':'static SPY at evaluated mean daily exposure','opportunity_control':'full SPY','windows':list(WINDOWS),'folds':5,'calendar_rule_fixed_no_day_count_cost_or_window_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(cut.date()),'panel_sha256':hashlib.sha256(px.reset_index().to_csv(index=False).encode()).hexdigest()},'tests':tests,'decision':decision}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p154_turn_of_month_spy_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
