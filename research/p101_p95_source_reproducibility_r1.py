from __future__ import annotations
import hashlib,json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
SYMS=("SPY","QQQ","TLT","GLD","DBC"); START="2006-01-01"
def canonical_hash(df):
 x=df.copy(); x.index=pd.to_datetime(x.index).tz_localize(None); x=x.sort_index().sort_index(axis=1); payload=x.to_csv(float_format='%.12g').encode(); return hashlib.sha256(payload).hexdigest()
def load():
 d=yf.download(list(SYMS),start=START,auto_adjust=True,progress=False,threads=False); c=d['Close'] if isinstance(d.columns,pd.MultiIndex) else d[['Close']]; c=c.loc[:,list(SYMS)].dropna(how='all').astype(float); last=pd.Timestamp(c.index.max()); last=last.tz_localize(None) if last.tzinfo is not None else last; return c.loc[c.index<=last.normalize()]
def calc(close,bps=25):
 m=close.resample('ME').last(); trend=(close/close.rolling(200,min_periods=160).mean()-1).resample('ME').last(); dd=(close/close.rolling(126,min_periods=100).max()-1).resample('ME').last(); mom=m.pct_change(6); pa={s:0. for s in SYMS}; ph={s:0. for s in SYMS}; rb=[]; rh=[]
 for dt in m.index:
  b=pd.DataFrame({'mom6':mom.loc[dt,list(SYMS)],'trend200':trend.loc[dt,list(SYMS)],'drawdown6':dd.loc[dt,list(SYMS)]},index=list(SYMS))
  if b.isna().any().any() or pd.isna(mom.loc[dt,'SPY']): continue
  loc=m.index.get_loc(dt)
  if not isinstance(loc,(int,np.integer)) or loc+1>=len(m): continue
  nxt=m.index[loc+1]; r=m.loc[nxt,list(SYMS)]/m.loc[dt,list(SYMS)]-1
  if r.isna().any(): continue
  chosen=b.rank(axis=0,pct=True,method='average').mean(axis=1).sort_values(ascending=False).head(2).index; wa={s:(.5 if s in chosen else 0.) for s in SYMS}; wh=wa if float(mom.loc[dt,'SPY'])>0 else {s:.2 for s in SYMS}; ta=.5*sum(abs(wa[s]-pa[s]) for s in SYMS); th=.5*sum(abs(wh[s]-ph[s]) for s in SYMS); rb.append(sum(wa[s]*float(r[s]) for s in SYMS)-ta*bps/10000); rh.append(sum(wh[s]*float(r[s]) for s in SYMS)-th*bps/10000); pa,ph=wa,wh
 def cagr(a):
  a=pd.Series(a,dtype=float); return float((1+a).prod()**(12/len(a))-1)
 return {'months':len(rb),'base_cagr':cagr(rb),'hybrid_cagr':cagr(rh),'incremental_cagr':cagr(rh)-cagr(rb)}
def main():
 a=load(); b=load(); ha,hb=canonical_hash(a),canonical_hash(b); common=a.index.intersection(b.index); delta=float((a.loc[common]-b.loc[common]).abs().max().max()) if len(common) else None; ra,rb=calc(a),calc(b); out={'schema':'research.p101_p95_source_reproducibility_r1','parent_ids':['P95','P97','P100','P101'],'contract':{'purpose':'challenge sign disagreement between P97 and P100 using two sequential same-run Yahoo adjusted-close materializations','symbols':SYMS,'start':START,'auto_adjust':True,'threads':False,'no_model_tuning':True},'materialization_a':{'rows':len(a),'start':str(a.index.min().date()),'end':str(a.index.max().date()),'sha256':ha},'materialization_b':{'rows':len(b),'start':str(b.index.min().date()),'end':str(b.index.max().date()),'sha256':hb},'same_hash':ha==hb,'max_abs_close_difference_on_common_dates':delta,'evaluation_a_25bps':ra,'evaluation_b_25bps':rb}; same=ha==hb and abs(ra['incremental_cagr']-rb['incremental_cagr'])<1e-12; out['decision']='SOURCE_AND_EVALUATION_DETERMINISTIC_WITHIN_RUN_PRIOR_SIGN_CONFLICT_REQUIRES_CODE_LINEAGE_AUDIT' if same else 'SOURCE_MATERIALIZATION_NONDETERMINISM_CONFIRMED_DO_NOT_USE_THIN_P95_DELTA'; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p101_p95_source_reproducibility_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
