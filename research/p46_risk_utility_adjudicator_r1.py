from __future__ import annotations
import json,math,hashlib
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
U=('SPY','QQQ','TLT','GLD','DBC'); COST=50

def metrics(r):
    r=pd.Series(r,dtype=float).dropna(); eq=(1+r).cumprod(); n=len(r); cg=float(eq.iloc[-1]**(12/n)-1); vol=float(r.std(ddof=1)*math.sqrt(12)); sharpe=float(r.mean()*12/vol) if vol else None; neg=r[r<0]; dvol=float(neg.std(ddof=1)*math.sqrt(12)) if len(neg)>1 else None; sortino=float(r.mean()*12/dvol) if dvol else None; mdd=float((eq/eq.cummax()-1).min()); calmar=float(cg/abs(mdd)) if mdd<0 else None; worst12=float((1+r).rolling(12).apply(np.prod,raw=True).sub(1).min()) if n>=12 else None; return {'cagr':cg,'vol':vol,'sharpe_rf0':sharpe,'sortino_rf0':sortino,'maxdd':mdd,'calmar':calmar,'worst_12m':worst12}
def build():
    d=yf.download(list(U),start='2005-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna(how='all').astype(float); last=pd.Timestamp(d.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cut=last.to_period('M').start_time-pd.Timedelta(days=1); d=d.loc[d.index<=cut]
    m=d.resample('ME').last(); vol=(d.pct_change(fill_method=None).rolling(126,min_periods=100).std(ddof=0)*math.sqrt(252)).resample('ME').last(); trend=(d/d.rolling(200,min_periods=160).mean()-1).resample('ME').last(); dd=(d/d.rolling(126,min_periods=100).max()-1).resample('ME').last(); mom=m.pct_change(6); prev={s:0. for s in U}; rows=[]
    for i,dt in enumerate(m.index[:-1]):
        b=pd.DataFrame({'mom6':mom.loc[dt,list(U)],'trend200':trend.loc[dt,list(U)],'low_vol6':-vol.loc[dt,list(U)],'drawdown6':dd.loc[dt,list(U)]},index=list(U));
        if b.isna().any().any(): continue
        chosen=list(b.rank(axis=0,pct=True,method='average').mean(axis=1).sort_values(ascending=False,kind='mergesort').head(2).index); nxt=m.index[i+1]; rr=m.loc[nxt,list(U)]/m.loc[dt,list(U)]-1
        if rr.isna().any(): continue
        w={s:(.5 if s in chosen else 0.) for s in U}; turn=.5*sum(abs(w[s]-prev[s]) for s in U); gross=sum(w[s]*float(rr[s]) for s in U); rows.append({'date':nxt,'p46':gross-turn*COST/10000,'equal_weight':float(rr.mean()),'spy':float(rr.SPY),'qqq':float(rr.QQQ),'turnover':turn}); prev=w
    return pd.DataFrame(rows).set_index('date'),d,cut

def main():
    q,d,cut=build(); windows={'2015':'2015-01-01','2020':'2020-01-01','2022':'2022-01-01'}; tests={}
    for w,s in windows.items():
        z=q.loc[pd.Timestamp(s):]; tests[w]={k:metrics(z[k]) for k in ('p46','equal_weight','spy','qqq')}; tests[w]['annualized_one_way_turnover']=float(z.turnover.mean()*12)
        tests[w]['deltas_vs_spy']={k:tests[w]['p46'][k]-tests[w]['spy'][k] for k in ('cagr','vol','sharpe_rf0','maxdd','calmar','worst_12m') if tests[w]['p46'][k] is not None and tests[w]['spy'][k] is not None}
        tests[w]['deltas_vs_qqq']={k:tests[w]['p46'][k]-tests[w]['qqq'][k] for k in ('cagr','vol','sharpe_rf0','maxdd','calmar','worst_12m') if tests[w]['p46'][k] is not None and tests[w]['qqq'][k] is not None}
    a=tests['2015']; risk_comp=(a['p46']['maxdd']>a['spy']['maxdd'] and a['p46']['vol']<a['spy']['vol'] and a['p46']['sharpe_rf0']>=a['spy']['sharpe_rf0'])
    decision='P46_RISK_UTILITY_OFFSETS_OPPORTUNITY_COST' if risk_comp else 'P46_RISK_UTILITY_DOES_NOT_OFFSET_OPPORTUNITY_COST'
    out={'schema':'research.p46_risk_utility_adjudicator_r1','parent':'P46','hypothesis':'At frozen 50-bps implementation cost, P46 lower opportunity return is justified by materially superior risk-adjusted utility versus SPY/QQQ.','contract':{'selector':'frozen P46 four-factor top-2 monthly','cost_bps_per_one_way_turnover':COST,'controls':['same-universe equal-weight','SPY','QQQ'],'metrics':['CAGR','volatility','Sharpe','Sortino','max drawdown','Calmar','worst rolling 12m'],'windows':list(windows),'no_signal_weight_cost_or_window_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(cut.date()),'panel_sha256':hashlib.sha256(d.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest()},'tests':tests,'decision':decision}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_risk_utility_adjudicator_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
