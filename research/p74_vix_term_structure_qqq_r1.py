from __future__ import annotations
import hashlib,json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
START="2007-01-01"; SYMBOLS=("^VIX","^VIX3M","QQQ","SHY","SPY"); COSTS=(10,25,50)
def metric(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); y=len(r)/12; c=float(e.iloc[-1]**(1/y)-1); a=float(r.mean()*12); v=float(r.std(ddof=0)*math.sqrt(12)); d=e/e.cummax()-1; m=float(d.min()); return {"cagr":c,"annualized_vol":v,"sharpe_rf0":a/v if v else float('nan'),"max_drawdown_monthly":m,"calmar":c/abs(m) if m<0 else float('nan')}
def folds(c,b):
 out=[]
 for n,idx in enumerate(np.array_split(np.arange(len(c)),5),1):
  cm,bm=metric(c.iloc[idx]),metric(b.iloc[idx]); out.append({"fold":n,"excess_cagr":cm["cagr"]-bm["cagr"]})
 return sum(x["excess_cagr"]>0 for x in out),out
def main():
 data=yf.download(list(SYMBOLS),start=START,auto_adjust=True,progress=False,threads=False); close=data["Close"] if isinstance(data.columns,pd.MultiIndex) else data[["Close"]]; close=close.loc[:,list(SYMBOLS)].astype(float); sha=hashlib.sha256(close.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest(); m=close.resample('ME').last(); rec=[]; prev=0.0
 for i,dt in enumerate(m.index[:-1]):
  nxt=m.index[i+1]
  if m.loc[[dt,nxt],list(SYMBOLS)].isna().any().any(): continue
  exp=1.0 if float(m.at[dt,"^VIX"])<float(m.at[dt,"^VIX3M"]) else 0.0; q=float(m.at[nxt,'QQQ']/m.at[dt,'QQQ']-1); shy=float(m.at[nxt,'SHY']/m.at[dt,'SHY']-1); spy=float(m.at[nxt,'SPY']/m.at[dt,'SPY']-1); rec.append({'return_month':str(nxt.date()),'gross':exp*q+(1-exp)*shy,'qqq':q,'shy':shy,'spy':spy,'qqq_exposure':exp,'turnover':abs(exp-prev),'vix_ratio':float(m.at[dt,'^VIX']/m.at[dt,'^VIX3M'])}); prev=exp
 fr=pd.DataFrame(rec); avg=float(fr.qqq_exposure.mean()); matched=avg*fr.qqq+(1-avg)*fr.shy; out={'schema':'research.p74_vix_term_structure_qqq_r1','hypothesis':'Prior month-end VIX below VIX3M identifies a causal normal-volatility risk state that can improve QQQ/SHY allocation beyond raw QQQ and an exposure-matched static blend.','scientific_contract':{'signal':'prior month-end VIX < VIX3M','risk_on':'QQQ','risk_off':'SHY','costs_bps':list(COSTS),'matched_control':'static QQQ/SHY at candidate mean QQQ exposure','no_threshold_smoothing_or_allocation_tuning':True},'source':{'provider':'Yahoo Finance via yfinance','normalized_panel_sha256':sha},'window':{'start':fr.iloc[0].return_month,'end':fr.iloc[-1].return_month,'months':int(len(fr))},'mean_qqq_exposure':avg,'mean_annual_turnover':float(fr.turnover.mean()*12),'costs':{}}
 for bp in COSTS:
  c=fr.gross-fr.turnover*bp/10000; cm,mm,qm,sm=metric(c),metric(matched),metric(fr.qqq),metric(fr.spy); pos,fs=folds(c,matched); out['costs'][str(bp)]={'candidate':cm,'matched_static_exposure':mm,'qqq':qm,'spy':sm,'excess_cagr_vs_matched':cm['cagr']-mm['cagr'],'excess_cagr_vs_qqq':cm['cagr']-qm['cagr'],'excess_cagr_vs_spy':cm['cagr']-sm['cagr'],'positive_folds_vs_matched':int(pos),'folds_vs_matched':fs}
 p,s=out['costs']['25'],out['costs']['50']; out['decision']='SUPPORTED_VIX_TERM_QQQ_CANDIDATE' if p['excess_cagr_vs_matched']>0.01 and p['positive_folds_vs_matched']>=3 and p['excess_cagr_vs_qqq']>0 and s['excess_cagr_vs_matched']>0 else 'NOT_SUPPORTED_VIX_TERM_QQQ_ROTATE'; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p74_vix_term_structure_qqq_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'window':out['window'],'mean_qqq_exposure':avg,'turnover':out['mean_annual_turnover'],'25':{k:p[k] for k in ('excess_cagr_vs_matched','excess_cagr_vs_qqq','excess_cagr_vs_spy','positive_folds_vs_matched')},'50':{k:s[k] for k in ('excess_cagr_vs_matched','excess_cagr_vs_qqq','excess_cagr_vs_spy')}},sort_keys=True))
if __name__=='__main__': main()
