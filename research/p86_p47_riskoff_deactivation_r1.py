from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np,pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
SYMS=base.UNIVERSES['industry']
def build(close):
 m=close.resample('ME').last(); last=pd.Timestamp(close.index.max()); last=last.tz_localize(None) if last.tzinfo is not None else last; m=m.loc[m.index<=last.normalize()]; dr=close.pct_change(); vol=(dr.rolling(126,min_periods=100).std(ddof=0)*math.sqrt(252)).resample('ME').last(); tr=(close/close.rolling(200,min_periods=160).mean()-1).resample('ME').last(); dd=(close/close.rolling(126,min_periods=100).max()-1).resample('ME').last(); mom=m.pct_change(6); pa={s:0. for s in SYMS}; ph={s:0. for s in SYMS}; rows=[]
 for dt in m.index:
  b=pd.DataFrame({'mom6':mom.loc[dt,list(SYMS)],'trend200':tr.loc[dt,list(SYMS)],'low_vol6':-vol.loc[dt,list(SYMS)],'drawdown6':dd.loc[dt,list(SYMS)]},index=list(SYMS))
  if b.isna().any().any() or pd.isna(mom.at[dt,'SPY']): continue
  loc=m.index.get_loc(dt)
  if not isinstance(loc,(int,np.integer)) or loc+1>=len(m): continue
  nxt=m.index[loc+1]; r=m.loc[nxt,list((*SYMS,'SPY','QQQ'))]/m.loc[dt,list((*SYMS,'SPY','QQQ'))]-1
  if r.isna().any(): continue
  sc=b.rank(axis=0,pct=True,method='average').mean(axis=1); ch=sc.sort_values(ascending=False).head(3).index.tolist(); aw={s:(1/3 if s in ch else 0.) for s in SYMS}; hw=aw if float(mom.at[dt,'SPY'])>0 else {s:1/len(SYMS) for s in SYMS}; active_turnover=.5*sum(abs(aw[s]-pa[s]) for s in SYMS); hybrid_turnover=.5*sum(abs(hw[s]-ph[s]) for s in SYMS); rows.append({'date':nxt,'ag':sum(aw[s]*float(r[s]) for s in SYMS),'hg':sum(hw[s]*float(r[s]) for s in SYMS),'active_turnover':active_turnover,'hybrid_turnover':hybrid_turnover,'ew':float(r.loc[list(SYMS)].mean()),'spy':float(r.SPY),'qqq':float(r.QQQ)}); pa,ph=aw,hw
 return pd.DataFrame(rows).set_index('date')
def score(f,bps):
 h=f['hg']-f['hybrid_turnover']*bps/10000; a=f['ag']-f['active_turnover']*bps/10000; hm,am,em=base.metrics(h),base.metrics(a),base.metrics(f['ew']); pe,fe=base.fold_count(h,f['ew']); pa,fa=base.fold_count(h,a); return {'hybrid':hm,'original_active':am,'matched_equal_weight':em,'spy':base.metrics(f['spy']),'qqq':base.metrics(f['qqq']),'excess_cagr_vs_equal_weight':hm['cagr']-em['cagr'],'excess_cagr_vs_original_active':hm['cagr']-am['cagr'],'positive_folds_vs_equal_weight':pe,'positive_folds_vs_original_active':pa,'folds_vs_equal_weight':fe,'folds_vs_original_active':fa}
def main():
 close=base.load(SYMS); f=build(close); p25,p50=score(f,25),score(f,50); ok=p25['excess_cagr_vs_equal_weight']>0 and p25['excess_cagr_vs_original_active']>0 and p25['positive_folds_vs_equal_weight']>=3 and p50['excess_cagr_vs_equal_weight']>0 and p50['excess_cagr_vs_original_active']>0; out={'schema':'research.p86_p47_riskoff_deactivation_r1','parent_ids':['P47','P81','P86'],'scientific_contract':{'mechanism':'P47 frozen four-factor top3 industry composite; prior-SPY-6m <=0 replaces active selection with exact industry-universe equal weight','comparators':['original P47 active','same-universe equal weight','SPY','QQQ'],'costs_bps':[25,50],'no_parameter_tuning':True},'window':{'start':str(f.index.min().date()),'end':str(f.index.max().date()),'months':len(f)},'turnover':{'hybrid_annual':float(f['hybrid_turnover'].mean()*12),'active_annual':float(f['active_turnover'].mean()*12)},'costs':{'25':p25,'50':p50},'decision':'SUPPORTED_P47_REGIME_TRANSFER_REQUIRES_PERSISTENCE' if ok else 'NOT_SUPPORTED_P47_REGIME_TRANSFER'}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p86_p47_riskoff_deactivation_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'window':out['window'],'25':{'excess_vs_ew':p25['excess_cagr_vs_equal_weight'],'excess_vs_original':p25['excess_cagr_vs_original_active'],'folds_vs_ew':p25['positive_folds_vs_equal_weight'],'folds_vs_original':p25['positive_folds_vs_original_active']},'50':{'excess_vs_ew':p50['excess_cagr_vs_equal_weight'],'excess_vs_original':p50['excess_cagr_vs_original_active']},'turnover':out['turnover']},sort_keys=True))
if __name__=='__main__': main()
