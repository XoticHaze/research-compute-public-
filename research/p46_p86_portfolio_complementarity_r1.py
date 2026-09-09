from __future__ import annotations
import hashlib, json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

P46_SYMS=("SPY","QQQ","TLT","GLD","DBC")
P86_SYMS=("MTUM","QUAL","USMV","VLUE","SIZE")
ALL=tuple(dict.fromkeys((*P46_SYMS,*P86_SYMS)))
BP=50
WINDOWS={"2015_forward":"2015-01-01","2020_forward":"2020-01-01","2022_forward":"2022-01-01"}


def cagr(r):
    r=pd.Series(r,dtype=float).dropna()
    return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')


def metrics(r):
    r=pd.Series(r,dtype=float).dropna(); eq=(1+r).cumprod(); vol=float(r.std(ddof=1)*math.sqrt(12)); ann=float(r.mean()*12)
    return {"cagr":cagr(r),"vol":vol,"sharpe_rf0":ann/vol if vol else None,"max_drawdown":float((eq/eq.cummax()-1).min())}


def p46_frame(close):
    monthly=close[list(P46_SYMS)].resample('ME').last(); daily=close[list(P46_SYMS)].pct_change()
    maps={
      "mom6":monthly.pct_change(6),
      "trend200":(close[list(P46_SYMS)]/close[list(P46_SYMS)].rolling(200,min_periods=160).mean()-1).resample('ME').last(),
      "low_vol6":-(daily.rolling(126,min_periods=100).std(ddof=0)*math.sqrt(252)).resample('ME').last(),
      "drawdown6":(close[list(P46_SYMS)]/close[list(P46_SYMS)].rolling(126,min_periods=100).max()-1).resample('ME').last(),
    }
    prev={s:0. for s in P46_SYMS}; rows=[]
    for i,dt in enumerate(monthly.index[:-1]):
        block=pd.DataFrame({k:v.loc[dt,list(P46_SYMS)] for k,v in maps.items()},index=list(P46_SYMS))
        if block.isna().any().any(): continue
        score=block.rank(axis=0,pct=True,method='average').mean(axis=1).sort_values(ascending=False)
        nxt=monthly.index[i+1]; realized=monthly.loc[nxt,list(P46_SYMS)]/monthly.loc[dt,list(P46_SYMS)]-1
        if realized.isna().any(): continue
        chosen=set(score.index[:2]); w={s:(.5 if s in chosen else 0.) for s in P46_SYMS}; turn=.5*sum(abs(w[s]-prev[s]) for s in P46_SYMS)
        rows.append({"date":nxt,"gross":sum(w[s]*float(realized[s]) for s in P46_SYMS),"turnover":turn,"matched":float(realized.mean()),"qqq":float(realized['QQQ'])}); prev=w
    return pd.DataFrame(rows).set_index('date')


def p86_frame(close):
    monthly=close[list(P86_SYMS)+['QQQ']].resample('ME').last(); prev=np.zeros(len(P86_SYMS)); rows=[]
    for i in range(6,len(monthly)-1):
        dt=monthly.index[i]; nxt=monthly.index[i+1]
        mom=(monthly.loc[dt,list(P86_SYMS)]/monthly.iloc[i-6][list(P86_SYMS)]-1).sort_values(ascending=False)
        chosen=set(mom.index[:2]); w=np.array([.5 if s in chosen else 0. for s in P86_SYMS]); realized=(monthly.loc[nxt,list(P86_SYMS)]/monthly.loc[dt,list(P86_SYMS)]-1).to_numpy(float)
        turn=.5*float(abs(w-prev).sum()); rows.append({"date":nxt,"gross":float(w@realized),"turnover":turn,"matched":float(np.mean(realized)),"qqq":float(monthly.loc[nxt,'QQQ']/monthly.loc[dt,'QQQ']-1)}); prev=w
    return pd.DataFrame(rows).set_index('date')


def score(frame):
    p46=frame.p46_gross-frame.p46_turnover*BP/10000
    p86=frame.p86_gross-frame.p86_turnover*BP/10000
    blend=.5*p46+.5*p86
    out={"p46":metrics(p46),"p86":metrics(p86),"blend_50_50":metrics(blend),"qqq":metrics(frame.qqq)}
    out["blend_excess_cagr_vs_p86"]=out['blend_50_50']['cagr']-out['p86']['cagr']
    out["blend_excess_cagr_vs_p46"]=out['blend_50_50']['cagr']-out['p46']['cagr']
    out["blend_excess_cagr_vs_qqq"]=out['blend_50_50']['cagr']-out['qqq']['cagr']
    out["blend_sharpe_delta_vs_p86"]=out['blend_50_50']['sharpe_rf0']-out['p86']['sharpe_rf0']
    out["blend_sharpe_delta_vs_p46"]=out['blend_50_50']['sharpe_rf0']-out['p46']['sharpe_rf0']
    out["blend_maxdd_delta_vs_p86"]=out['blend_50_50']['max_drawdown']-out['p86']['max_drawdown']
    out["blend_maxdd_delta_vs_p46"]=out['blend_50_50']['max_drawdown']-out['p46']['max_drawdown']
    out["monthly_return_correlation_p46_p86"]=float(p46.corr(p86))
    ids=np.array_split(np.arange(len(frame)),5); folds=[]
    for j,ix in enumerate(ids,1):
        q=frame.iloc[ix]; a=q.p46_gross-q.p46_turnover*BP/10000; b=q.p86_gross-q.p86_turnover*BP/10000; z=.5*a+.5*b
        folds.append({"fold":j,"blend_excess_cagr_vs_p86":cagr(z)-cagr(b),"blend_excess_cagr_vs_qqq":cagr(z)-cagr(q.qqq)})
    out['positive_folds_vs_p86']=sum(x['blend_excess_cagr_vs_p86']>0 for x in folds); out['positive_folds_vs_qqq']=sum(x['blend_excess_cagr_vs_qqq']>0 for x in folds); out['folds']=folds
    return out


def main():
    raw=yf.download(list(ALL),start='2005-01-01',auto_adjust=True,progress=False,threads=False); close=raw['Close'].dropna(how='all').astype(float)
    last=pd.Timestamp(close.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cutoff=last.to_period('M').start_time-pd.Timedelta(days=1); close=close.loc[close.index<=cutoff]
    a=p46_frame(close); b=p86_frame(close); idx=a.index.intersection(b.index); f=pd.DataFrame(index=idx)
    for pfx,x in [('p46',a),('p86',b)]: f[f'{pfx}_gross']=x.loc[idx,'gross']; f[f'{pfx}_turnover']=x.loc[idx,'turnover']
    f['qqq']=a.loc[idx,'qqq']
    tests={name:score(f.loc[start:]) for name,start in WINDOWS.items()}
    t=tests['2020_forward']; decision='P46_P86_COMPLEMENTARITY_SUPPORTED' if t['blend_excess_cagr_vs_p86']>0 and t['blend_sharpe_delta_vs_p86']>0 and t['positive_folds_vs_p86']>=3 else 'P46_P86_COMPLEMENTARITY_NOT_SUPPORTED'
    out={"schema":"research.p46_p86_portfolio_complementarity_r1","parents":["P46","P86"],"hypothesis":"Adding frozen P46 at fixed 50% weight to the frozen P86 factor-rotation survivor improves after-cost portfolio return/risk efficiency versus P86 alone without relying on weight tuning.","contract":{"weights":{"P46":0.5,"P86":0.5},"cost_bps_each_sleeve":BP,"p46":"original five-ETF four-factor top-two monthly selector","p86":"top-two trailing six-month momentum across MTUM/QUAL/USMV/VLUE/SIZE","controls":["P46 standalone","P86 standalone","QQQ"],"windows":WINDOWS,"folds":5,"no_weight_or_parameter_search":True},"source":{"provider":"Yahoo Finance via yfinance; research-only","last_complete_month_end":str(cutoff.date()),"joint_panel_sha256":hashlib.sha256(close.reset_index().to_csv(index=False).encode()).hexdigest()},"tests":tests,"decision":decision}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_p86_portfolio_complementarity_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True,allow_nan=False))

if __name__=='__main__': main()
