from __future__ import annotations
import io, json, math, time, zipfile
from pathlib import Path
import pandas as pd, requests, yfinance as yf
START_YEAR=2018; END_YEAR=2026; END='2026-09-11'; COST_BPS=10.0
BASE='https://www.sec.gov/files/data/fails-deliver-data/cnsfails{ym}{half}.zip'
FOLDS=[('2019-01-01','2021-12-31'),('2022-01-01','2023-12-31'),('2024-01-01',END)]
UA={'User-Agent':'XoticHaze market research contact XoticHaze@users.noreply.github.com'}
def cagr(r):
    if len(r)<2:return None
    y=(r.index[-1]-r.index[0]).days/365.25;t=float((1+r).prod());return None if y<=0 or t<=0 else t**(1/y)-1
def mdd(r):
    e=(1+r).cumprod();return float((e/e.cummax()-1).min())
def stats(r):return {'cagr':cagr(r),'max_drawdown':mdd(r),'vol':float(r.std()*math.sqrt(252)),'days':int(len(r))}
def fetch_ftd():
    rows=[];ok=0;missing=0
    for y in range(START_YEAR,END_YEAR+1):
      for m in range(1,13):
        if y==2026 and m>8:continue
        ym=f'{y}{m:02d}'
        for half in ('a','b'):
          u=BASE.format(ym=ym,half=half)
          try:
            r=requests.get(u,headers=UA,timeout=(10,45))
            if r.status_code==404: missing+=1; continue
            r.raise_for_status(); ok+=1
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
              name=z.namelist()[0]
              d=pd.read_csv(z.open(name),sep='|',dtype=str,encoding_errors='ignore')
            d.columns=[str(c).strip().upper() for c in d.columns]
            sym=next((c for c in d.columns if c in {'SYMBOL','SYMBOLS'}),None)
            qty=next((c for c in d.columns if 'QUANTITY' in c),None)
            price=next((c for c in d.columns if c=='PRICE'),None)
            date=next((c for c in d.columns if 'SETTLEMENT' in c and 'DATE' in c),None)
            if not all([sym,qty,price,date]): continue
            x=d[d[sym].isin(['IWM','SPY'])][[date,sym,qty,price]].copy()
            x['date']=pd.to_datetime(x[date],format='%Y%m%d',errors='coerce')
            x['qty']=pd.to_numeric(x[qty],errors='coerce');x['price']=pd.to_numeric(x[price],errors='coerce')
            x['dollar_ftd']=x['qty']*x['price']; rows.append(x[['date',sym,'dollar_ftd']].rename(columns={sym:'symbol'}))
          except Exception:
            missing+=1
          time.sleep(0.03)
    if not rows:return pd.DataFrame(),{'archives_ok':ok,'archives_missing_or_failed':missing}
    a=pd.concat(rows,ignore_index=True).dropna();a['month']=a.date.dt.to_period('M').dt.to_timestamp('M')
    p=a.groupby(['month','symbol']).dollar_ftd.sum().unstack('symbol').sort_index()
    return p,{'archives_ok':ok,'archives_missing_or_failed':missing,'raw_symbol_days':int(len(a))}
def evaluate(d,a,b):
    z=d.loc[a:b];return {'strategy':stats(z.strategy),'control':stats(z.control),'IWM':stats(z.IWM),'SPY':stats(z.SPY),'matched_excess_cagr':cagr(z.strategy)-cagr(z.control),'spy_excess_cagr':cagr(z.strategy)-cagr(z.SPY),'switches':int(z.switch.sum()),'iwm_weight_mean':float(z.iwm_w.mean())}
def main():
    ftd,diag=fetch_ftd()
    if len(ftd)<24 or not {'IWM','SPY'}.issubset(ftd.columns):
      out={'schema':'research.p553_sec_ftd_smallcap_stress_r1','parent':'P553','decision':'P553_SOURCE_COVERAGE_NOT_READY','source_diagnostics':diag,'months':int(len(ftd))}
    else:
      med=ftd[['IWM','SPY']].expanding(min_periods=12).median();norm=(ftd[['IWM','SPY']]/med).replace([float('inf')],pd.NA)
      # Higher relative IWM settlement stress is treated as a reason to prefer SPY.
      signal=(norm.IWM<=norm.SPY).astype(float).shift(2).dropna().rename('iwm_w')
      raw=yf.download(['IWM','SPY'],start='2018-01-01',end='2026-09-12',auto_adjust=True,progress=False,group_by='column');close=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
      r=close[['IWM','SPY']].dropna().pct_change().dropna();d=r.join(signal.reindex(r.index,method='ffill')).dropna();d['spy_w']=1-d.iwm_w;d['switch']=d.iwm_w.diff().abs().fillna(0);d['strategy']=d.iwm_w*d.IWM+d.spy_w*d.SPY-d.switch*(COST_BPS/10000);d['control']=0.5*d.IWM+0.5*d.SPY
      overall=evaluate(d,'2019-01-01',END);folds=[evaluate(d,*f) for f in FOLDS];positive=sum(f['matched_excess_cagr']>0 for f in folds);decision='P553_SUPPORTED' if overall['matched_excess_cagr']>0 and positive>=2 else 'P553_NOT_SUPPORTED_NO_RESCUE'
      out={'schema':'research.p553_sec_ftd_smallcap_stress_r1','parent':'P553','claim':'Relative SEC fails-to-deliver settlement stress can causally select IWM versus SPY with durable after-cost excess over a static IWM/SPY mix.','frozen_contract':{'source':'SEC Fails-to-Deliver half-month archives','feature':'monthly sum of daily outstanding dollar FTD for IWM and SPY, each normalized by its expanding median after 12 months','signal':'IWM when normalized IWM FTD stress <= normalized SPY stress; otherwise SPY','availability_guard':'two full month-end lag after the settlement month','control':'static 50/50 IWM/SPY','cost_bps_per_full_switch':COST_BPS,'folds':FOLDS,'no_parameter_rescue':True},'overall':overall,'folds':folds,'positive_fold_count':positive,'decision':decision,'source_diagnostics':{**diag,'months':int(len(ftd)),'first_month':str(ftd.index.min().date()),'last_month':str(ftd.index.max().date())},'boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
    Path('artifacts').mkdir(exist_ok=True);Path('artifacts/p553_sec_ftd_smallcap_stress_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True));print(json.dumps(out,sort_keys=True))
if __name__=='__main__':main()
