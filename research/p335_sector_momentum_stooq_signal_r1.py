from __future__ import annotations
import io,json,math,urllib.request
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
SECTORS=['XLB','XLE','XLF','XLI','XLK','XLP','XLU','XLV','XLY']; ALL=SECTORS+['SPY']; START='2001-01-01'; END='2026-09-10'; COST_BPS=25; TOP_K=3
# Independent signal-source leg: Stooq unadjusted/price Close is used only for cross-sectional ranking, never for realized return estimation.
def stooq(sym):
    url=f'https://stooq.com/q/d/l/?s={sym.lower()}.us&d1=20010101&d2=20260910&i=d'
    with urllib.request.urlopen(url,timeout=30) as f: raw=f.read()
    q=pd.read_csv(io.BytesIO(raw)); q['Date']=pd.to_datetime(q['Date']); q=q.set_index('Date').sort_index(); return q['Close'].rename(sym)
stooq_px=pd.concat([stooq(s) for s in SECTORS],axis=1).resample('ME').last(); score=stooq_px.shift(1)/stooq_px.shift(12)-1
raw=yf.download(ALL,start=START,end=END,auto_adjust=True,progress=False,threads=False); yfpx=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[ALL].resample('ME').last(); ret=yfpx.pct_change()
rows=[]
for dt in ret.index.intersection(score.index):
    s=score.loc[dt,SECTORS].dropna(); rr=ret.loc[dt,SECTORS].dropna(); avail=s.index.intersection(rr.index)
    if len(avail)<TOP_K: continue
    top=s.loc[avail].nlargest(TOP_K).index; rows.append((dt,float(rr.loc[top].mean()),float(rr.loc[avail].mean()),float(ret.loc[dt,'SPY']) if pd.notna(ret.loc[dt,'SPY']) else np.nan,tuple(top)))
z=pd.DataFrame(rows,columns=['date','gross','matched','spy','top']).set_index('date'); prev=set(); net=[]; turns=[]
for _,row in z.iterrows():
    cur=set(row.top); turn=1.0 if not prev else 1.0-len(prev&cur)/TOP_K; net.append(row.gross-turn*COST_BPS/10000); turns.append(turn); prev=cur
z['strategy']=net; z['turnover']=turns
def stats(s):
    s=s.dropna(); w=(1+s).cumprod(); yrs=len(s)/12; sd=s.std(); return {'months':int(len(s)),'cagr':float(w.iloc[-1]**(1/yrs)-1),'sharpe':float(s.mean()/sd*math.sqrt(12)) if sd>0 else 0.0,'max_drawdown':float((w/w.cummax()-1).min())}
res={}
for name,start in {'2005_plus':'2005-01-01','2010_plus':'2010-01-01','2015_plus':'2015-01-01','2020_plus':'2020-01-01'}.items():
    q=z.loc[start:].dropna(subset=['strategy','matched','spy']); a,b,c=stats(q.strategy),stats(q.matched),stats(q.spy); res[name]={'strategy':a,'matched':b,'spy':c,'matched_excess_cagr':a['cagr']-b['cagr'],'spy_gap_cagr':a['cagr']-c['cagr'],'mean_turnover':float(q.turnover.mean())}
q=z.loc['2005-01-01':].dropna(subset=['strategy','matched']); folds=[stats(f.strategy)['cagr']-stats(f.matched)['cagr'] for f in np.array_split(q,5)]; passed=all(res[k]['matched_excess_cagr']>0 for k in res) and sum(x>0 for x in folds)>=3
decision='P335_STOOQ_SIGNAL_REPLICATION_SUPPORTED' if passed else 'P335_STOOQ_SIGNAL_REPLICATION_NOT_SUPPORTED'
out={'schema':'research.p335_sector_momentum_stooq_signal_r1','parent':'P335','claim':'Independent signal-source adjudicator for P330: derive the unchanged 12-1 top-3 monthly sector ranking from Stooq price closes for nine long-history SPDR sectors, while measuring realized returns and the matched equal-sector control with the existing adjusted-price provider. This isolates whether selection depends on the original adjusted-price signal source. Fixed top-k, horizon, sector set, costs, windows, and folds; no tuning.','signal_source':'Stooq daily Close via stooq.com CSV','realized_return_source':'Yahoo Finance adjusted prices via yfinance','sector_universe':SECTORS,'cost_bps':COST_BPS,'results':res,'chronology_fold_matched_excess_cagr':folds,'positive_folds':sum(x>0 for x in folds),'decision_rule':'Support source robustness only if positive after-cost matched excess appears in every fixed window and >=3/5 chronology folds. Failure narrows signal-source robustness but does not erase P330/P332/P333 evidence.','decision':decision,'limitations':['Stooq Close ranking is price-return rather than total-return momentum, intentionally making this an alternate signal representation','XLC and XLRE excluded prospectively because their shorter histories do not span the fixed source-fidelity window','realized returns remain measured on the original adjusted-price provider to isolate the signal-source dimension','no portfolio ranking/allocation/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p335_sector_momentum_stooq_signal_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
