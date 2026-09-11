from __future__ import annotations
import io,json,math
from pathlib import Path
import pandas as pd,requests,yfinance as yf
END='2026-09-11'; COST_BPS=10.0
SOURCES=[('FRED','https://fred.stlouisfed.org/graph/fredgraph.csv?id=DRTSCILM'),('eco3min_fred_mirror','https://eco3min.fr/dataset/us-bank-lending-standards.csv')]
FOLDS=[('2009-01-01','2013-12-31'),('2014-01-01','2019-12-31'),('2020-01-01',END)]
def cagr(r):
    if len(r)<2:return None
    y=(r.index[-1]-r.index[0]).days/365.25;t=float((1+r).prod())
    return None if y<=0 or t<=0 else t**(1/y)-1
def mdd(r):
    e=(1+r).cumprod();return float((e/e.cummax()-1).min())
def stats(r):return {'cagr':cagr(r),'max_drawdown':mdd(r),'vol':float(r.std()*math.sqrt(252)),'days':int(len(r))}
def sloos():
    errors=[]
    for name,url in SOURCES:
        try:
            r=requests.get(url,timeout=(15,35),headers={'User-Agent':'XoticHaze market research'});r.raise_for_status();x=pd.read_csv(io.BytesIO(r.content));x.columns=[str(c).strip() for c in x.columns]
            dc=next((c for c in x.columns if c.lower() in {'date','observation_date'}),x.columns[0]);vc=next((c for c in x.columns if c!=dc and c.lower() in {'drtscilm','net_pct_tightening'}),None) or next(c for c in x.columns if c!=dc)
            x[dc]=pd.to_datetime(x[dc],errors='coerce');x[vc]=pd.to_numeric(x[vc],errors='coerce');s=x.dropna(subset=[dc,vc]).sort_values(dc).set_index(dc)[vc]
            if len(s)<100:raise ValueError(f'insufficient SLOOS observations: {len(s)}')
            sig=(s.resample('ME').last().ffill()>0).astype(float).shift(1).dropna().rename('tightening')
            return sig,{'series':'DRTSCILM','source':name,'url':url,'observations':int(len(s)),'first_observation':str(s.index.min().date()),'last_observation':str(s.index.max().date()),'latest_value':float(s.iloc[-1]),'fallback_errors':errors}
        except Exception as exc:errors.append({'source':name,'error':repr(exc)})
    raise RuntimeError(f'all SLOOS sources failed: {errors}')
def evaluate(d,a,b):
    z=d.loc[a:b];return {'strategy':stats(z.strategy),'control':stats(z.control),'HYG':stats(z.HYG),'LQD':stats(z.LQD),'matched_excess_cagr':cagr(z.strategy)-cagr(z.control),'hyg_excess_cagr':cagr(z.strategy)-cagr(z.HYG),'switches':int(z.switch.sum()),'lqd_weight_mean':float(z.lqd_w.mean())}
def main():
    sig,diag=sloos();raw=yf.download(['HYG','LQD'],start='2008-01-01',end='2026-09-12',auto_adjust=True,progress=False,group_by='column');close=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
    r=close[['HYG','LQD']].dropna().pct_change().dropna();d=r.join(sig.reindex(r.index,method='ffill')).dropna();d['lqd_w']=d.tightening;d['hyg_w']=1-d.lqd_w;d['switch']=d.lqd_w.diff().abs().fillna(0);d['strategy']=d.lqd_w*d.LQD+d.hyg_w*d.HYG-d.switch*(COST_BPS/10000);d['control']=0.5*d.HYG+0.5*d.LQD
    overall=evaluate(d,'2009-01-01',END);folds=[evaluate(d,*f) for f in FOLDS];positive=sum(f['matched_excess_cagr']>0 for f in folds);modern=folds[-1]['matched_excess_cagr']>0
    decision='P556_SUPPORTED' if overall['matched_excess_cagr']>0 and positive>=2 and modern else 'P556_NOT_SUPPORTED_NO_RESCUE'
    out={'schema':'research.p556_sloos_credit_quality_rotation_r1','parent':'P556','claim':'Causally lagged SLOOS C&I tightening can rotate credit exposure from HYG into LQD with durable after-cost excess over a static HYG/LQD mix, including 2020+.','frozen_contract':{'series':'DRTSCILM','signal':'>0 => LQD; <=0 => HYG','lag_months':1,'transition_cost_bps':COST_BPS,'control':'static 50/50 HYG/LQD','folds':FOLDS,'gate':'positive aggregate excess, >=2/3 positive folds, positive 2020+ fold','no_parameter_rescue':True},'source_diagnostics':diag,'overall':overall,'folds':folds,'positive_fold_count':positive,'current_regime_positive':modern,'decision':decision,'boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
    Path('artifacts').mkdir(exist_ok=True);Path('artifacts/p556_sloos_credit_quality_rotation_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True));print(json.dumps(out,sort_keys=True))
if __name__=='__main__':main()
