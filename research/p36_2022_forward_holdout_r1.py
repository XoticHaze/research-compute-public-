from __future__ import annotations
import hashlib,json
from pathlib import Path
import pandas as pd,yfinance as yf
import p76_p36_serial_persistence_r1 as p76
SYMS=('SMH','QQQ','SPY')
def main():
 data=yf.download(list(SYMS),start='2000-01-01',auto_adjust=True,progress=False,threads=False); close=data['Close'] if isinstance(data.columns,pd.MultiIndex) else data[['Close']]; close=close.loc[:,list(SYMS)].astype(float); end=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp('M'); m=close.resample('ME').last(); m=m.loc[m.index<end]; mom=m[['SMH','QQQ']].pct_change(6); rec=[]; prev={'SMH':0.,'QQQ':0.}
 for i,dt in enumerate(m.index[:-1]):
  nxt=m.index[i+1]
  if mom.loc[dt].isna().any() or m.loc[[dt,nxt],list(SYMS)].isna().any().any(): continue
  pick='SMH' if mom.at[dt,'SMH']>mom.at[dt,'QQQ'] else 'QQQ'; w={'SMH':1. if pick=='SMH' else 0.,'QQQ':1. if pick=='QQQ' else 0.}; turn=.5*sum(abs(w[s]-prev[s]) for s in w); smh=float(m.at[nxt,'SMH']/m.at[dt,'SMH']-1); q=float(m.at[nxt,'QQQ']/m.at[dt,'QQQ']-1); sp=float(m.at[nxt,'SPY']/m.at[dt,'SPY']-1); rec.append({'date':nxt,'gross':smh if pick=='SMH' else q,'matched':.5*(smh+q),'qqq':q,'spy':sp,'turnover':turn}); prev=w
 fr=pd.DataFrame(rec).set_index('date').loc[pd.Timestamp('2022-01-01'):]; tests={}
 for bp in (25,50,100):
  c=fr.gross-fr.turnover*bp/10000; cm,mm,qm,sm=p76.metric(c),p76.metric(fr.matched),p76.metric(fr.qqq),p76.metric(fr.spy); pos,folds=p76.base.fold_count(c,fr.matched) if hasattr(p76,'base') else (None,None); tests[str(bp)]={'candidate':cm,'matched':mm,'QQQ':qm,'SPY':sm,'excess_vs_matched_cagr':cm['cagr']-mm['cagr'],'excess_vs_QQQ_cagr':cm['cagr']-qm['cagr'],'excess_vs_SPY_cagr':cm['cagr']-sm['cagr']}
 supported=tests['50']['excess_vs_matched_cagr']>0 and tests['100']['excess_vs_matched_cagr']>0
 out={'schema':'research.p36_2022_forward_holdout_r1','parent':'P36','scientific_contract':{'signal':'unchanged prior complete month 6m SMH-vs-QQQ leader','holdout':'2022-forward','costs_bps':[25,50,100],'matched_control':'static 50/50 SMH-QQQ','opportunity_controls':['QQQ','SPY'],'no_parameter_tuning':True},'source':{'provider':'Yahoo Finance via yfinance','complete_month_panel_sha256':hashlib.sha256(m.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest()},'window':{'start':str(fr.index.min().date()),'end':str(fr.index.max().date()),'months':len(fr)},'tests':tests,'decision':'P36_RECENT_HOLDOUT_SUPPORTED' if supported else 'P36_RECENT_HOLDOUT_NOT_SUPPORTED'}
 Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p36_2022_forward_holdout_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'window':out['window'],'tests':tests},sort_keys=True))
if __name__=='__main__': main()
