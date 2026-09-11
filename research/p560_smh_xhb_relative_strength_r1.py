from __future__ import annotations
import json,math
from pathlib import Path
import pandas as pd,yfinance as yf
END='2026-09-11';COST_BPS=10.0;ASSETS=['SMH','XHB']
FOLDS=[('2007-01-01','2013-12-31'),('2014-01-01','2019-12-31'),('2020-01-01',END)]
def cagr(r):
    if len(r)<2:return None
    y=(r.index[-1]-r.index[0]).days/365.25;t=float((1+r).prod());return None if y<=0 or t<=0 else t**(1/y)-1
def mdd(r):e=(1+r).cumprod();return float((e/e.cummax()-1).min())
def stats(r):return {'cagr':cagr(r),'max_drawdown':mdd(r),'vol':float(r.std()*math.sqrt(252)),'days':int(len(r))}
def ev(d,a,b):
    z=d.loc[a:b];return {'strategy':stats(z.strategy),'control':stats(z.control),'SPY':stats(z.SPY),'SMH':stats(z.SMH),'XHB':stats(z.XHB),'matched_excess_cagr':cagr(z.strategy)-cagr(z.control),'spy_excess_cagr':cagr(z.strategy)-cagr(z.SPY),'switches':int(z.switch.sum()),'smh_weight_mean':float(z.smh_w.mean())}
def main():
    ts=ASSETS+['SPY'];raw=yf.download(ts,start='2006-01-01',end='2026-09-12',auto_adjust=True,progress=False,group_by='column');c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw;c=c[ts].dropna().ffill();r=c.pct_change().dropna();m=c[ASSETS].resample('ME').last();mom=m/m.shift(6)-1;sel=(mom.SMH>mom.XHB).astype(float).rename('smh_w');dw=sel.reindex(r.index,method='ffill').shift(1).dropna();d=r.join(dw).dropna();d['xhb_w']=1-d.smh_w;d['switch']=d.smh_w.diff().abs().fillna(0);d['strategy']=d.smh_w*d.SMH+d.xhb_w*d.XHB-d.switch*(COST_BPS/10000);d['control']=0.5*d.SMH+0.5*d.XHB;overall=ev(d,'2007-01-01',END);folds=[ev(d,*f) for f in FOLDS];mp=sum(x['matched_excess_cagr']>0 for x in folds);sp=sum(x['spy_excess_cagr']>0 for x in folds);decision='P560_SUPPORTED' if overall['matched_excess_cagr']>0 and overall['spy_excess_cagr']>0 and mp>=2 and sp>=2 else 'P560_NOT_SUPPORTED_NO_RESCUE';out={'schema':'research.p560_smh_xhb_relative_strength_r1','parent':'P560','claim':'A frozen monthly six-month relative-strength allocator between semiconductors (SMH) and homebuilders (XHB) can create durable after-cost excess over both a static 50/50 SMH-XHB mix and SPY.','frozen_contract':{'assets':ASSETS,'feature':'six-month total return at month end','signal':'hold whichever asset has higher six-month return','rebalance':'monthly, applied following session','cost_bps_per_full_switch':COST_BPS,'controls':['static 50/50 SMH-XHB','SPY'],'folds':FOLDS,'gate':'positive aggregate excess vs both and >=2/3 positive folds vs each','no_parameter_rescue':True},'overall':overall,'folds':folds,'positive_fold_count_vs_matched':mp,'positive_fold_count_vs_spy':sp,'decision':decision,'boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}};Path('artifacts').mkdir(exist_ok=True);Path('artifacts/p560_smh_xhb_relative_strength_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True));print(json.dumps(out,sort_keys=True))
if __name__=='__main__':main()
