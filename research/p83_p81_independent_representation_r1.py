from __future__ import annotations
import hashlib,json,math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

SYMBOLS=("VTI","VEA","IEF","IAU","GSG")
REQUESTED=(*SYMBOLS,"SPY","QQQ")
START="2007-01-01"

def load():
    d=yf.download(list(REQUESTED),start=START,auto_adjust=True,progress=False,threads=False)
    if d.empty: raise RuntimeError("empty_download")
    c=d["Close"] if isinstance(d.columns,pd.MultiIndex) else d[["Close"]]
    if not isinstance(c,pd.DataFrame): c=c.to_frame()
    missing=[s for s in REQUESTED if s not in c.columns]
    if missing: raise RuntimeError(f"missing:{missing}")
    return c.loc[:,list(REQUESTED)].dropna(how="all").astype(float)

def metrics(r):
    r=pd.Series(r,dtype=float).dropna(); eq=(1+r).cumprod(); years=len(r)/12; cagr=float(eq.iloc[-1]**(1/years)-1); ann=float(r.mean()*12); vol=float(r.std(ddof=0)*math.sqrt(12)); dd=eq/eq.cummax()-1; mdd=float(dd.min())
    return {"cagr":cagr,"annualized_mean":ann,"annualized_vol":vol,"sharpe_rf0":ann/vol if vol else float('nan'),"max_drawdown_monthly":mdd,"calmar":cagr/abs(mdd) if mdd<0 else float('nan')}

def folds(c,b):
    out=[]
    for n,idx in enumerate(np.array_split(np.arange(len(c)),5),1):
        cm,bm=metrics(c.iloc[idx]),metrics(b.iloc[idx]); out.append({"fold":n,"excess_cagr":cm['cagr']-bm['cagr']})
    return sum(x['excess_cagr']>0 for x in out),out

def build(close):
    monthly=close.resample('ME').last(); last=pd.Timestamp(close.index.max()); last=last.tz_localize(None) if last.tzinfo is not None else last; monthly=monthly.loc[monthly.index<=last.normalize()].copy(); dr=close.pct_change()
    vol6=(dr.rolling(126,min_periods=100).std(ddof=0)*math.sqrt(252)).resample('ME').last(); trend=(close/close.rolling(200,min_periods=160).mean()-1).resample('ME').last(); dd6=(close/close.rolling(126,min_periods=100).max()-1).resample('ME').last(); mom6=monthly.pct_change(6)
    pa={s:0. for s in SYMBOLS}; ph={s:0. for s in SYMBOLS}; rows=[]
    for month in monthly.index:
        block=pd.DataFrame({'mom6':mom6.loc[month,list(SYMBOLS)],'trend200':trend.loc[month,list(SYMBOLS)],'low_vol6':-vol6.loc[month,list(SYMBOLS)],'drawdown6':dd6.loc[month,list(SYMBOLS)]},index=list(SYMBOLS))
        if block.isna().any().any() or pd.isna(mom6.at[month,'SPY']): continue
        loc=monthly.index.get_loc(month)
        if not isinstance(loc,(int,np.integer)) or loc+1>=len(monthly): continue
        nxt=monthly.index[loc+1]; realized=monthly.loc[nxt,list(REQUESTED)]/monthly.loc[month,list(REQUESTED)]-1
        if realized.isna().any(): continue
        score=block.rank(axis=0,pct=True,method='average').mean(axis=1); chosen=score.sort_values(ascending=False).head(2).index.tolist(); aw={s:(.5 if s in chosen else 0.) for s in SYMBOLS}; risk_on=float(mom6.at[month,'SPY'])>0; hw=aw if risk_on else {s:1/len(SYMBOLS) for s in SYMBOLS}; at=.5*sum(abs(aw[s]-pa[s]) for s in SYMBOLS); ht=.5*sum(abs(hw[s]-ph[s]) for s in SYMBOLS)
        rows.append({'date':nxt,'active_gross':sum(aw[s]*float(realized[s]) for s in SYMBOLS),'hybrid_gross':sum(hw[s]*float(realized[s]) for s in SYMBOLS),'active_turnover':at,'hybrid_turnover':ht,'ew':float(realized.loc[list(SYMBOLS)].mean()),'spy':float(realized['SPY']),'qqq':float(realized['QQQ']),'risk_on':risk_on}); pa,ph=aw,hw
    return pd.DataFrame(rows).set_index('date')

def score(f,bps):
    a=f.active_gross-f.active_turnover*bps/10000; h=f.hybrid_gross-f.hybrid_turnover*bps/10000; ew=f.ew; hm,am,em=metrics(h),metrics(a),metrics(ew); pe,fe=folds(h,ew); pa,fa=folds(h,a)
    return {'hybrid':hm,'original_active':am,'matched_equal_weight':em,'spy':metrics(f.spy),'qqq':metrics(f.qqq),'excess_cagr_vs_equal_weight':hm['cagr']-em['cagr'],'excess_cagr_vs_original_active':hm['cagr']-am['cagr'],'positive_folds_vs_equal_weight':pe,'positive_folds_vs_original_active':pa,'folds_vs_equal_weight':fe,'folds_vs_original_active':fa}

def main():
    close=load(); f=build(close); p25,p50=score(f,25),score(f,50); supported=p25['excess_cagr_vs_equal_weight']>0 and p25['excess_cagr_vs_original_active']>0 and p25['positive_folds_vs_equal_weight']>=3 and p50['excess_cagr_vs_equal_weight']>0 and p50['excess_cagr_vs_original_active']>0
    out={'schema':'research.p83_p81_independent_representation_r1','parent_ids':['P46','P81','P83'],'scientific_contract':{'representation':list(SYMBOLS),'frozen_score':'equal ranks of 6m momentum, SMA200 trend, inverse 6m vol, 6m distance-from-high; top2','frozen_regime':'prior SPY 6m >0 risk-on; otherwise risk-off','mutation':'risk-off exact same-universe equal weight instead of active top2','comparators':['original active composite','same-universe equal weight','SPY','QQQ'],'costs_bps':[25,50],'no_parameter_tuning':True,'complete_months_only':True},'source':{'provider':'Yahoo Finance via yfinance','normalized_panel_sha256':hashlib.sha256(close.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest()},'window':{'start':str(f.index.min().date()),'end':str(f.index.max().date()),'months':len(f)},'risk_on_months':int(f.risk_on.sum()),'risk_off_months':int((~f.risk_on).sum()),'turnover':{'hybrid_annual':float(f.hybrid_turnover.mean()*12),'active_annual':float(f.active_turnover.mean()*12)},'costs':{'25':p25,'50':p50},'decision':'SUPPORTED_INDEPENDENT_REPRESENTATION' if supported else 'NOT_SUPPORTED_INDEPENDENT_REPRESENTATION'}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p83_p81_independent_representation_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'window':out['window'],'25':{'excess_vs_ew':p25['excess_cagr_vs_equal_weight'],'excess_vs_original':p25['excess_cagr_vs_original_active'],'folds_vs_ew':p25['positive_folds_vs_equal_weight'],'folds_vs_original':p25['positive_folds_vs_original_active']},'50':{'excess_vs_ew':p50['excess_cagr_vs_equal_weight'],'excess_vs_original':p50['excess_cagr_vs_original_active']},'turnover':out['turnover']},sort_keys=True))
if __name__=='__main__': main()
