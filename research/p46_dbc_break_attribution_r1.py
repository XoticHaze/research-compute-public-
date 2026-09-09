from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
S=('SPY','QQQ','TLT','GLD','DBC');BREAK=pd.Timestamp('2025-11-10')
def metrics(r):
 r=pd.Series(r).dropna();eq=(1+r).cumprod();years=len(r)/12;return {'months':len(r),'cagr':float(eq.iloc[-1]**(1/years)-1) if len(r) else None,'total_return':float(eq.iloc[-1]-1) if len(r) else None}
def main():
 c=yf.download(list(S),start='2015-01-01',auto_adjust=True,progress=False,threads=False)['Close'][list(S)].dropna();m=c.resample('ME').last();dr=c.pct_change(fill_method=None);maps={'mom6':m.pct_change(6),'trend200':(c/c.rolling(200,min_periods=160).mean()-1).resample('ME').last(),'low_vol6':-(dr.rolling(126,min_periods=100).std(ddof=0)*math.sqrt(252)).resample('ME').last(),'drawdown6':(c/c.rolling(126,min_periods=100).max()-1).resample('ME').last()};prev={s:0.0 for s in S};rows=[]
 for dt in m.index:
  b=pd.DataFrame({k:v.loc[dt,list(S)] for k,v in maps.items()},index=list(S))
  if b.isna().any().any():continue
  ch=tuple(b.rank(axis=0,pct=True).mean(axis=1).sort_values(ascending=False).head(2).index);loc=m.index.get_loc(dt)
  if not isinstance(loc,(int,np.integer)) or loc+1>=len(m):continue
  nxt=m.index[loc+1];ret=m.loc[nxt,list(S)]/m.loc[dt,list(S)]-1;w={s:(.5 if s in ch else 0) for s in S};turn=.5*sum(abs(w[s]-prev[s]) for s in S);gross=sum(w[s]*float(ret[s]) for s in S);dbc_contrib=w['DBC']*float(ret['DBC']);rows.append({'feature_month':str(dt.date()),'return_month':str(nxt.date()),'dbc_selected':'DBC' in ch,'chosen':list(ch),'gross':gross,'ew':float(ret.mean()),'turnover':turn,'dbc_contribution':dbc_contrib});prev=w
 f=pd.DataFrame(rows);f['return_month_ts']=pd.to_datetime(f.return_month);post=f[f.return_month_ts>=BREAK];pre=f[f.return_month_ts<BREAK];
 def part(x):return {'months':len(x),'dbc_selected_months':int(x.dbc_selected.sum()),'dbc_selection_rate':float(x.dbc_selected.mean()) if len(x) else None,'mean_dbc_contribution_when_selected':float(x.loc[x.dbc_selected,'dbc_contribution'].mean()) if x.dbc_selected.any() else None,'candidate_50bps':metrics(x.gross-x.turnover*0.005),'matched_ew':metrics(x.ew)}
 out={'schema':'research.p46_dbc_break_attribution_r1','parent':'P46','break_date':'2025-11-10','contract':{'selector':'frozen P46 four-factor top-2','returns':'Yahoo auto-adjusted realized fund returns','purpose':'scope realized P46 dependence on DBC around provider methodology break','no_parameter_tuning':True},'pre_break':part(pre),'post_break':part(post),'post_break_rows':post[['feature_month','return_month','dbc_selected','chosen','dbc_contribution']].to_dict('records'),'decision':'DBC_BREAK_EXPOSURE_PROFILED'};Path('artifacts').mkdir(exist_ok=True);Path('artifacts/p46_dbc_break_attribution_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True));print(json.dumps({'pre':out['pre_break'],'post':out['post_break']},sort_keys=True))
if __name__=='__main__':main()
