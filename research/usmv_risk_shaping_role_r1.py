from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
T=['USMV','SPY','BIL'];COST=.0025;FROZEN_BETA=.701
x=yf.download(T,start='2012-01-01',end='2026-09-10',auto_adjust=True,progress=False,threads=False)
if x.empty:raise SystemExit('SOURCE_FAILURE_EMPTY')
c=x['Close'] if isinstance(x.columns,pd.MultiIndex) else x;r=c[T].resample('ME').last().dropna().pct_change().dropna().loc['2013-01-01':]
def charge(s):
 y=s.copy()
 if len(y):y.iloc[0]-=COST;y.iloc[-1]-=COST
 return y
def stats(s):
 q=charge(pd.Series(s,dtype=float).dropna());n=len(q);w=(1+q).cumprod();vol=q.std(ddof=1)*math.sqrt(12);ann=q.mean()*12
 return {'months':n,'cagr':float(w.iloc[-1]**(12/n)-1),'sharpe':float(ann/vol) if vol else None,'max_drawdown':float((w/w.cummax()-1).min()),'vol':float(vol)}
def ev(a,b=None):
 z=r.loc[a:b];u=charge(z.USMV);m=charge(z.SPY);rf=charge(z.BIL);rm=charge(FROZEN_BETA*z.SPY+(1-FROZEN_BETA)*z.BIL);ux=u-rf;mx=m-rf;beta=float(np.cov(ux,mx,ddof=1)[0,1]/np.var(mx,ddof=1));alpha=float((ux-beta*mx).mean()*12);neg=z.SPY<0;down_u=float(z.loc[neg,'USMV'].mean());down_m=float(z.loc[neg,'SPY'].mean());us,ms,rms=stats(z.USMV),stats(z.SPY),stats(FROZEN_BETA*z.SPY+(1-FROZEN_BETA)*z.BIL)
 return {'usmv':us,'spy':ms,'risk_matched_spy_bil':rms,'raw_spy_opportunity_cost_cagr':us['cagr']-ms['cagr'],'beta_to_spy_excess':beta,'annualized_jensen_alpha':alpha,'down_months':int(neg.sum()),'mean_usmv_when_spy_down':down_u,'mean_spy_when_spy_down':down_m,'downside_capture':down_u/down_m if down_m else None,'risk_matched_delta':{'cagr':us['cagr']-rms['cagr'],'sharpe':us['sharpe']-rms['sharpe'],'max_drawdown':us['max_drawdown']-rms['max_drawdown'],'vol':us['vol']-rms['vol']}}
blocks={'2013_2016':('2013-01-01','2016-12-31'),'2017_2020':('2017-01-01','2020-12-31'),'2021_plus':('2021-01-01',None)};full=ev('2013-01-01');sub={k:ev(a,b) for k,(a,b) in blocks.items()};d=full['risk_matched_delta'];latest=sub['2021_plus'];latest_d=latest['risk_matched_delta'];riskshape=full['annualized_jensen_alpha']>0 and full['beta_to_spy_excess']<.9 and full['usmv']['max_drawdown']>full['spy']['max_drawdown'] and (d['sharpe']>0 or d['max_drawdown']>0) and (latest_d['sharpe']>0 or latest_d['max_drawdown']>0)
redundant=(d['cagr']<=0 and d['sharpe']<=0 and d['max_drawdown']<=0)
if riskshape:decision='RISK_SHAPING_COMPLEMENT'
elif redundant:decision='REDUNDANT_RISK_REDUCTION'
else:decision='NEEDS_CONFIRMATION'
out={'schema':'research.usmv_risk_shaping_role_r1','workload_id':'USMV_RISK_SHAPING_PORTFOLIO_ROLE_R1','claim':'Adjudicate whether fixed USMV low-beta behavior improves drawdown/downside/risk-adjusted capital efficiency versus SPY and a frozen beta-matched SPY+BIL diagnostic, without relabeling lower volatility as raw alpha.','contract':{'candidate':'USMV','broad_market':'SPY','cash_control':'BIL','endpoint_cost_bps_each':25,'risk_matched_diagnostic':'70.1% SPY + 29.9% BIL','risk_match_weight_source':'frozen prior P422 full-sample beta rounded to 0.701; not optimized here','blocks':blocks},'full_sample':full,'chronology':sub,'decision_rule':'RISK_SHAPING_COMPLEMENT only if beta-adjusted alpha remains positive, beta<0.9, drawdown improves versus SPY, USMV beats the frozen beta-matched diagnostic on Sharpe or max drawdown full sample and in the latest weak block. Raw SPY opportunity cost remains explicit. No beta/product/date/window/cost rescue.','decision':decision,'scientific_consequence':'This result concerns risk-shaping utility only. It does not reopen standalone low-vol raw-alpha claims and grants no portfolio ranking/allocation authority.','boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True);Path('research/artifacts/usmv_risk_shaping_role_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False));print(json.dumps({'decision':decision,'beta':round(full['beta_to_spy_excess'],3),'alpha_pp':round(100*full['annualized_jensen_alpha'],3),'spy_opportunity_pp':round(100*full['raw_spy_opportunity_cost_cagr'],3),'downside_capture':round(full['downside_capture'],3),'risk_matched_delta':{k:round(v,4) for k,v in d.items()},'latest_risk_matched_delta':{k:round(v,4) for k,v in latest_d.items()}},sort_keys=True))