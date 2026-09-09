from __future__ import annotations
import hashlib,json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
SECTORS=['XLB','XLE','XLF','XLI','XLK','XLP','XLU','XLV','XLY']; COSTS=(25,50,100)

def cagr(r):
    r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')
def stats(r):
    r=pd.Series(r,dtype=float).dropna(); eq=(1+r).cumprod(); vol=float(r.std(ddof=1)*math.sqrt(12)) if len(r)>1 else float('nan'); ann=float(r.mean()*12) if len(r) else float('nan'); return {'cagr':cagr(r),'sharpe_rf0':ann/vol if vol and np.isfinite(vol) else None,'maxdd':float((eq/eq.cummax()-1).min()) if len(eq) else None}
def evaluate(q,cost):
    z=q.copy(); z['net']=z.gross-z.turnover*cost/10000
    out={k:stats(z[k]) for k in ('net','equal_sector','spy','qqq')}; out.update({'excess_equal_sector':out['net']['cagr']-out['equal_sector']['cagr'],'excess_spy':out['net']['cagr']-out['spy']['cagr'],'excess_qqq':out['net']['cagr']-out['qqq']['cagr'],'months':len(z),'avg_turnover':float(z.turnover.mean())})
    fs=[]
    for j,ii in enumerate(np.array_split(np.arange(len(z)),5),1):
        a=z.iloc[ii]; fs.append({'fold':j,'equal_sector_excess':cagr(a.net)-cagr(a.equal_sector),'spy_excess':cagr(a.net)-cagr(a.spy),'qqq_excess':cagr(a.net)-cagr(a.qqq)})
    out['positive_equal_sector_folds']=sum(x['equal_sector_excess']>0 for x in fs); out['positive_spy_folds']=sum(x['spy_excess']>0 for x in fs); out['positive_qqq_folds']=sum(x['qqq_excess']>0 for x in fs); out['folds']=fs; return out

def main():
    tickers=SECTORS+['SPY','QQQ']; px=yf.download(tickers,start='2000-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna().astype(float)
    last=pd.Timestamp(px.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cut=last.to_period('M').start_time-pd.Timedelta(days=1); px=px.loc[px.index<=cut]
    m=px.resample('ME').last(); r=m.pct_change(fill_method=None); mom=m[SECTORS].pct_change(12); rows=[]; prev=None
    for i,dt in enumerate(m.index[:-1]):
        if i<12 or mom.loc[dt].isna().any(): continue
        nxt=m.index[i+1]; rr=r.loc[nxt]
        if rr[tickers].isna().any(): continue
        sel=tuple(sorted(mom.loc[dt].nlargest(3).index)); w={s:(1/3 if s in sel else 0.) for s in SECTORS}
        turnover=1.0 if prev is None else .5*sum(abs(w[s]-prev[s]) for s in SECTORS); prev=w
        rows.append({'signal_month':dt,'return_month':nxt,'selected':'|'.join(sel),'turnover':turnover,'gross':float(sum(w[s]*rr[s] for s in SECTORS)),'equal_sector':float(rr[SECTORS].mean()),'spy':float(rr.SPY),'qqq':float(rr.QQQ)})
    q=pd.DataFrame(rows).set_index('return_month'); windows={'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01','2022':'2022-01-01'}
    tests={w:{str(c):evaluate(q.loc[pd.Timestamp(s):],c) for c in COSTS} for w,s in windows.items()}; a=tests['2015']['50']; b=tests['2020']['50']
    decision='P142_SECTOR_MOMENTUM_TOP3_SUPPORTED_FOR_INDEPENDENT_VALIDATION' if a['excess_equal_sector']>0 and a['positive_equal_sector_folds']>=3 and b['excess_equal_sector']>0 and b['positive_equal_sector_folds']>=3 and a['excess_spy']>0 else 'P142_SECTOR_MOMENTUM_TOP3_NOT_SUPPORTED'
    out={'schema':'research.p142_sector_momentum_top3_r1','parent':'P142','hypothesis':'A fixed monthly top-three sector selector based on prior completed 12-month momentum creates durable after-cost cross-sectional sector alpha beyond static equal-sector exposure and broad-market controls.','contract':{'signal':'At each completed month-end equally weight the three highest trailing-12-month sector ETF returns for the next month','sectors':SECTORS,'top_n':3,'lookback_months':12,'cost_bps':list(COSTS),'matched_control':'equal-weight nine-sector basket','broad_control':'SPY','growth_opportunity_control':'QQQ','windows':list(windows),'folds':5,'no_lookback_topn_weight_cost_or_universe_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only dynamic source, not promotion-grade','last_complete_month_end':str(cut.date()),'panel_sha256':hashlib.sha256(px.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest()},'tests':tests,'decision':decision}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p142_sector_momentum_top3_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
