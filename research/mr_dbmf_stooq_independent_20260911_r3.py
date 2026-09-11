from __future__ import annotations
import json,math,urllib.parse,urllib.request
from pathlib import Path
import numpy as np
import pandas as pd

SYMS=['DBMF','BIL','SPY']; EP=.0025
OUT=Path('research/artifacts/mr_dbmf_stooq_independent_20260911_r3.json'); OUT.parent.mkdir(parents=True,exist_ok=True)

def load(sym):
    q=urllib.parse.urlencode({'assetclass':'etf','fromdate':'01/01/2020','todate':'09/12/2026','limit':5000})
    url=f'https://api.nasdaq.com/api/quote/{sym}/historical?{q}'
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json, text/plain, */*','Referer':f'https://www.nasdaq.com/market-activity/etf/{sym.lower()}/historical'})
    with urllib.request.urlopen(req,timeout=30) as r: obj=json.loads(r.read().decode('utf-8'))
    rows=(((obj.get('data') or {}).get('tradesTable') or {}).get('rows') or [])
    if not rows: raise RuntimeError(f'NASDAQ_SOURCE_FAILURE_{sym}:NO_ROWS')
    vals=[]
    for row in rows:
        d=row.get('date'); c=str(row.get('close','')).replace('$','').replace(',','').strip()
        if d and c: vals.append((pd.to_datetime(d),float(c)))
    if not vals: raise RuntimeError(f'NASDAQ_SOURCE_FAILURE_{sym}:NO_PARSEABLE_ROWS')
    return pd.Series(dict(vals),name=sym,dtype=float).sort_index()
px=pd.concat([load(s) for s in SYMS],axis=1).dropna()
m=px.resample('ME').last().pct_change().dropna().loc['2021-01-01':]
if len(m)<60: raise RuntimeError(f'NASDAQ_SOURCE_COVERAGE_NOT_READY:{len(m)}')

def stats(r,cost=0.0):
    r=r.dropna(); w=(1+r).cumprod()*(1-cost)**2; years=len(r)/12.0; dd=w/w.cummax()-1; sd=r.std(ddof=1)
    return {'months':int(len(r)),'cagr':float(w.iloc[-1]**(1/years)-1),'maxdd':float(dd.min()),'sharpe':float((r.mean()/sd)*math.sqrt(12)) if sd>0 else None}
def ev(a,b=None):
    z=m.loc[a:b]; c=stats(z.DBMF,EP); cash=stats(z.BIL); spy=stats(z.SPY)
    return {'candidate':c,'cash_control':cash,'spy_opportunity':spy,'cash_excess_cagr_pp':100*(c['cagr']-cash['cagr']),'spy_excess_cagr_pp':100*(c['cagr']-spy['cagr']),'spy_corr':float(z.DBMF.corr(z.SPY))}
windows={'2021+':ev('2021-01-01'),'2022+':ev('2022-01-01'),'2024+':ev('2024-01-01')}
blocks={'2021_2022':ev('2021-01-01','2022-12-31'),'2023_2024':ev('2023-01-01','2024-12-31'),'2025_plus':ev('2025-01-01')}
cand=(1+m.DBMF).rolling(12).apply(np.prod,raw=True)*(1-EP)**2-1
cash=(1+m.BIL).rolling(12).apply(np.prod,raw=True)-1
rex=(cand-cash).dropna(); down=m[m.SPY<0]; severe=m[m.SPY<=-0.05]
rolling={'windows':int(len(rex)),'positive_fraction':float((rex>0).mean()),'median_excess_pp':float(100*rex.median())}
conditional={'down_months':int(len(down)),'down_cash_excess_mean_pp':float(100*(down.DBMF-down.BIL).mean()),'severe_months':int(len(severe)),'severe_cash_excess_mean_pp':float(100*(severe.DBMF-severe.BIL).mean())}
positive_windows=sum(v['cash_excess_cagr_pp']>0 for v in windows.values()); positive_blocks=sum(v['cash_excess_cagr_pp']>0 for v in blocks.values())
passed=(positive_windows>=3 and positive_blocks>=2 and windows['2024+']['cash_excess_cagr_pp']>0 and rolling['windows']>=48 and rolling['positive_fraction']>=0.60 and rolling['median_excess_pp']>0 and conditional['down_cash_excess_mean_pp']>0 and conditional['severe_months']>=5 and conditional['severe_down_cash_excess_mean_pp']>0) if False else (positive_windows>=3 and positive_blocks>=2 and windows['2024+']['cash_excess_cagr_pp']>0 and rolling['windows']>=48 and rolling['positive_fraction']>=0.60 and rolling['median_excess_pp']>0 and conditional['down_cash_excess_mean_pp']>0 and conditional['severe_months']>=5 and conditional['severe_cash_excess_mean_pp']>0)
decision='DBMF_INDEPENDENT_SOURCE_VALIDATION_SUPPORTED' if passed else 'DBMF_INDEPENDENT_SOURCE_VALIDATION_NOT_SUPPORTED'
out={'schema':'research.mr_dbmf_independent_20260911_r3.v1','workload_id':'MR_DBMF_INDEPENDENT_20260911_R3','parent':'DBMF_IMPLEMENTATION_SURVIVOR','source':{'provider':'Nasdaq historical ETF endpoint','symbols':SYMS,'endpoint_pattern':'https://api.nasdaq.com/api/quote/{symbol}/historical','independent_from_prior':'Prior R1/R2 used yfinance/Yahoo-derived prices; this challenged R3 uses Nasdaq historical rows after the first Stooq route returned HTTP 404.'},'claim':'The DBMF implementation-specific survivor should reproduce on an independent public price source without changing products, dates, costs, cash hurdle, or orthogonal persistence tests.','contract':{'endpoint_cost_bps_each':25,'cash_control':'BIL','opportunity_control':'SPY','windows':list(windows),'blocks':list(blocks),'rolling_horizon_months':12,'minimum_positive_rolling_fraction':0.60,'severe_spy_month':'<= -5%','parameter_search':False},'windows':windows,'blocks':blocks,'rolling12':rolling,'conditional':conditional,'positive_windows':positive_windows,'positive_blocks':positive_blocks,'decision_rule':'SUPPORTED only if DBMF beats BIL after costs in all 3 fixed windows, >=2/3 chronology blocks, remains positive from 2024+, independently repeats >=60% positive rolling-12m cash excess with positive median, and has positive BIL excess in SPY-down and severe-down months with >=5 severe observations. No source/date/product/cost/threshold rescue.','decision':decision,'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':decision,'positive_windows':positive_windows,'positive_blocks':positive_blocks,'2021_cash_pp':round(windows['2021+']['cash_excess_cagr_pp'],3),'2024_cash_pp':round(windows['2024+']['cash_excess_cagr_pp'],3),'spy_corr':round(windows['2021+']['spy_corr'],3),'roll_pos':round(rolling['positive_fraction'],3),'roll_med_pp':round(rolling['median_excess_pp'],3),'down_pp':round(conditional['down_cash_excess_mean_pp'],3),'severe_n':conditional['severe_months'],'severe_pp':round(conditional['severe_cash_excess_mean_pp'],3)},sort_keys=True))
