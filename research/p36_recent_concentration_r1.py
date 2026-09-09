from __future__ import annotations
import hashlib,json
from pathlib import Path
import pandas as pd,yfinance as yf
import p76_p36_serial_persistence_r1 as p76
SYMS=('SMH','QQQ','SPY')
def cagr(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1)
def main():
 data=yf.download(list(SYMS),start='2000-01-01',auto_adjust=True,progress=False,threads=False); close=data['Close'] if isinstance(data.columns,pd.MultiIndex) else data[['Close']]; close=close.loc[:,list(SYMS)].astype(float); end=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp('M'); m=close.resample('ME').last(); m=m.loc[m.index<end]; mom=m[['SMH','QQQ']].pct_change(6); rec=[]; prev={'SMH':0.,'QQQ':0.}
 for i,dt in enumerate(m.index[:-1]):
  nxt=m.index[i+1]
  if mom.loc[dt].isna().any() or m.loc[[dt,nxt],list(SYMS)].isna().any().any(): continue
  pick='SMH' if mom.at[dt,'SMH']>mom.at[dt,'QQQ'] else 'QQQ'; w={'SMH':1. if pick=='SMH' else 0.,'QQQ':1. if pick=='QQQ' else 0.}; turn=.5*sum(abs(w[s]-prev[s]) for s in w); smh=float(m.at[nxt,'SMH']/m.at[dt,'SMH']-1); q=float(m.at[nxt,'QQQ']/m.at[dt,'QQQ']-1); rec.append({'date':nxt,'gross':smh if pick=='SMH' else q,'matched':.5*(smh+q),'turnover':turn}); prev=w
 fr=pd.DataFrame(rec).set_index('date').loc[pd.Timestamp('2022-01-01'):]; tests={}
 for bp in (25,50):
  c=fr.gross-fr.turnover*bp/10000; active=c-fr.matched; strongest=active.nlargest(5).index; keep=~fr.index.isin(strongest); residual=c[keep]; control=fr.matched[keep]
  tests[str(bp)]={'full_excess_cagr':cagr(c)-cagr(fr.matched),'strongest_relative_months':[str(x.date()) for x in strongest],'strongest_relative_months_sum':float(active.loc[strongest].sum()),'residual_excess_cagr_after_removing_top5':cagr(residual)-cagr(control),'residual_months':int(keep.sum())}
 supported=tests['25']['residual_excess_cagr_after_removing_top5']>0 and tests['50']['residual_excess_cagr_after_removing_top5']>0
 out={'schema':'research.p36_recent_concentration_r1','parent':'P36','scientific_contract':{'signal':'unchanged 6m SMH-vs-QQQ leader','window':'2022-forward complete months','costs_bps':[25,50],'matched_control':'static 50/50 SMH-QQQ','falsification':'remove five strongest candidate-minus-matched months then recompute CAGR difference','no_parameter_tuning':True},'source':{'complete_month_panel_sha256':hashlib.sha256(m.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest()},'tests':tests,'decision':'P36_RECENT_ALPHA_SURVIVES_TOP5_REMOVAL' if supported else 'P36_RECENT_ALPHA_CONCENTRATED'}
 Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p36_recent_concentration_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
