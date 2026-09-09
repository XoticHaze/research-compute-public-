from __future__ import annotations
import hashlib,json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf

START='2000-01-01'; SYMBOLS=('SMH','QQQ','SPY'); COSTS=(25,50); RNG_SEED=760036; BOOT=5000

def metric(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); y=len(r)/12; c=float(e.iloc[-1]**(1/y)-1); a=float(r.mean()*12); v=float(r.std(ddof=0)*math.sqrt(12)); d=e/e.cummax()-1; m=float(d.min()); return {'cagr':c,'annualized_vol':v,'sharpe_rf0':a/v if v else float('nan'),'max_drawdown_monthly':m,'calmar':c/abs(m) if m<0 else float('nan')}

def rolling(c,b,n):
 xs=[]
 for i in range(n-1,len(c)):
  cm,bm=metric(c.iloc[i-n+1:i+1]),metric(b.iloc[i-n+1:i+1]); xs.append(cm['cagr']-bm['cagr'])
 a=np.array(xs,float); return {'windows':int(len(a)),'positive_fraction':float(np.mean(a>0)),'median_excess_cagr':float(np.median(a)),'p10_excess_cagr':float(np.quantile(a,.1)),'worst_excess_cagr':float(np.min(a))}

def block_bootstrap(active,block=12):
 x=np.asarray(active,float); rng=np.random.default_rng(RNG_SEED); n=len(x); vals=[]
 starts=np.arange(max(1,n-block+1))
 for _ in range(BOOT):
  sample=[]
  while len(sample)<n:
   s=int(rng.choice(starts)); sample.extend(x[s:s+block])
  vals.append(float(np.mean(sample[:n])*12))
 a=np.array(vals); return {'block_months':block,'draws':BOOT,'annualized_mean_excess':float(np.mean(x)*12),'bootstrap_95pct':[float(np.quantile(a,.025)),float(np.quantile(a,.975))],'p_excess_le_zero':float(np.mean(a<=0))}

def main():
 data=yf.download(list(SYMBOLS),start=START,auto_adjust=True,progress=False,threads=False); close=data['Close'] if isinstance(data.columns,pd.MultiIndex) else data[['Close']]; close=close.loc[:,list(SYMBOLS)].astype(float)
 current_end=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp('M'); monthly=close.resample('ME').last(); monthly=monthly.loc[monthly.index<current_end]
 sha=hashlib.sha256(monthly.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest(); mom6=monthly[['SMH','QQQ']].pct_change(6); rec=[]; prev={'SMH':0.0,'QQQ':0.0}
 for i,dt in enumerate(monthly.index[:-1]):
  nxt=monthly.index[i+1]
  if mom6.loc[dt].isna().any() or monthly.loc[[dt,nxt],list(SYMBOLS)].isna().any().any(): continue
  pick='SMH' if float(mom6.at[dt,'SMH'])>float(mom6.at[dt,'QQQ']) else 'QQQ'; w={'SMH':1.0 if pick=='SMH' else 0.0,'QQQ':1.0 if pick=='QQQ' else 0.0}; turn=.5*sum(abs(w[s]-prev[s]) for s in w); smh=float(monthly.at[nxt,'SMH']/monthly.at[dt,'SMH']-1); q=float(monthly.at[nxt,'QQQ']/monthly.at[dt,'QQQ']-1); spy=float(monthly.at[nxt,'SPY']/monthly.at[dt,'SPY']-1); rec.append({'return_month':str(nxt.date()),'gross':smh if pick=='SMH' else q,'matched':.5*smh+.5*q,'qqq':q,'spy':spy,'turnover':turn,'pick':pick}); prev=w
 fr=pd.DataFrame(rec); out={'schema':'research.p76_p36_serial_persistence_r1','parents':['P36'],'hypothesis':'The frozen six-month SMH-versus-QQQ relative-strength selector has serially persistent after-cost excess versus the exact static 50/50 SMH-QQQ control, not merely full-sample alpha.','scientific_contract':{'signal':'prior complete month-end 6m SMH return versus QQQ 6m return; hold leader next month','matched_control':'static 50/50 SMH-QQQ same months','costs_bps':list(COSTS),'rolling_windows_months':[36,60],'bootstrap':'5000 draws of 12-month moving blocks of candidate-minus-matched monthly active return','incomplete_months_excluded':True,'no_parameter_or_threshold_tuning':True},'source':{'provider':'Yahoo Finance via yfinance','complete_month_panel_sha256':sha},'window':{'start':fr.iloc[0].return_month,'end':fr.iloc[-1].return_month,'months':int(len(fr))},'mean_annual_turnover':float(fr.turnover.mean()*12),'costs':{}}
 for bp in COSTS:
  c=fr.gross-fr.turnover*bp/10000; cm,mm,qm,sm=metric(c),metric(fr.matched),metric(fr.qqq),metric(fr.spy); active=c-fr.matched; out['costs'][str(bp)]={'candidate':cm,'matched':mm,'qqq':qm,'spy':sm,'excess_cagr_vs_matched':cm['cagr']-mm['cagr'],'excess_cagr_vs_qqq':cm['cagr']-qm['cagr'],'rolling36_vs_matched':rolling(c,fr.matched,36),'rolling60_vs_matched':rolling(c,fr.matched,60),'block_bootstrap_vs_matched':block_bootstrap(active)}
 p,s=out['costs']['25'],out['costs']['50']; out['decision']='SUPPORTED_P36_SERIAL_PERSISTENCE' if p['excess_cagr_vs_matched']>0 and p['rolling60_vs_matched']['positive_fraction']>=.6 and p['block_bootstrap_vs_matched']['p_excess_le_zero']<=.10 and s['excess_cagr_vs_matched']>0 else 'P36_SERIAL_PERSISTENCE_NOT_STRONG_ENOUGH_PARK'
 Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p76_p36_serial_persistence_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'window':out['window'],'turnover':out['mean_annual_turnover'],'25':{'excess_matched':p['excess_cagr_vs_matched'],'excess_qqq':p['excess_cagr_vs_qqq'],'r36':p['rolling36_vs_matched'],'r60':p['rolling60_vs_matched'],'bootstrap':p['block_bootstrap_vs_matched']},'50':{'excess_matched':s['excess_cagr_vs_matched'],'r60_positive':s['rolling60_vs_matched']['positive_fraction'],'bootstrap_p':s['block_bootstrap_vs_matched']['p_excess_le_zero']}},sort_keys=True))
if __name__=='__main__': main()
