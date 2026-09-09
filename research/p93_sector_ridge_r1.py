from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

SECTORS=['XLB','XLE','XLF','XLI','XLK','XLP','XLU','XLV','XLY']
ALL=SECTORS+['SPY']; COSTS=(25,50,100)

def cagr(r):
    r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')

def met(r):
    r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); v=float(r.std(ddof=1)*math.sqrt(12)) if len(r)>1 else float('nan'); a=float(r.mean()*12) if len(r) else float('nan'); dd=float((e/e.cummax()-1).min()) if len(r) else float('nan'); return {'cagr':cagr(r),'sharpe_rf0':a/v if v and np.isfinite(v) else None,'max_drawdown':dd}

def main():
    raw=yf.download(ALL,start='1999-01-01',auto_adjust=True,progress=False,threads=False); c=raw['Close'].dropna().astype(float)
    last=pd.Timestamp(c.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cutoff=last.to_period('M').start_time-pd.Timedelta(days=1); m=c.resample('ME').last(); m=m[m.index<=cutoff]
    mr=m.pct_change(); panel=[]
    for i in range(12,len(m)-1):
        dt=m.index[i]; nxt=m.index[i+1]
        for s in SECTORS:
            row={'date':dt,'sector':s,'target':float(m.loc[nxt,s]/m.loc[dt,s]-1),'spy_next':float(m.loc[nxt,'SPY']/m.loc[dt,'SPY']-1)}
            for h in (1,3,6,12):
                row[f'ret{h}']=float(m.loc[dt,s]/m.iloc[i-h][s]-1); row[f'rel{h}']=row[f'ret{h}']-float(m.loc[dt,'SPY']/m.iloc[i-h]['SPY']-1)
            row['vol6']=float(mr[s].iloc[i-5:i+1].std(ddof=1)); panel.append(row)
    p=pd.DataFrame(panel); feat=[f'{k}{h}' for h in (1,3,6,12) for k in ('ret','rel')]+['vol6']; dates=sorted(p.date.unique()); min_train_months=60; rows=[]; prev=np.ones(len(SECTORS))/len(SECTORS)
    for di in range(min_train_months,len(dates)):
        dt=dates[di]; tr=p[p.date<dt]; cur=p[p.date==dt].copy(); model=make_pipeline(StandardScaler(),Ridge(alpha=10.0)); model.fit(tr[feat],tr.target); cur['pred']=model.predict(cur[feat]); chosen=set(cur.nlargest(3,'pred').sector)
        w=np.array([1/3 if s in chosen else 0. for s in SECTORS]); actual=cur.set_index('sector').loc[SECTORS,'target'].to_numpy(float); turn=.5*float(abs(w-prev).sum())
        rows.append({'date':dt,'gross':float(w@actual),'turnover':turn,'matched':float(actual.mean()),'spy':float(cur.spy_next.iloc[0]),'top3_realized':float(cur[cur.sector.isin(chosen)].target.mean())}); prev=w
    f=pd.DataFrame(rows).set_index('date'); out={'schema':'research.p93_sector_ridge_r1','parent':'P93','hypothesis':'A strict expanding-window pooled ridge model can rank nine legacy US sector ETFs and produce durable after-cost top-3 cross-sectional excess.','contract':{'universe':SECTORS,'features':feat,'model':'StandardScaler + Ridge alpha=10 fixed','training':'pooled expanding window, 60-month minimum, no future rows','allocation':'equal weight top 3 predicted next-month sectors','costs_bps':list(COSTS),'matched_control':'static equal weight nine sectors','opportunity_control':'SPY','windows':['all_oos','2015_forward','2020_forward'],'folds':5,'no_hyperparameter_search':True},'tests':{}}
    for name,start in [('all_oos',None),('2015_forward','2015-01-01'),('2020_forward','2020-01-01')]:
        q=f if start is None else f.loc[start:]; z={'months':len(q),'controls':{'matched':met(q.matched),'spy':met(q.spy)},'costs':{}}; ids=np.array_split(np.arange(len(q)),5)
        for bp in COSTS:
            net=q.gross-q.turnover*bp/10000; cm=met(net); folds=[]
            for j,ix in enumerate(ids,1):
                a=q.iloc[ix]; cand=a.gross-a.turnover*bp/10000; folds.append({'fold':j,'excess_cagr_vs_matched':cagr(cand)-cagr(a.matched),'excess_cagr_vs_spy':cagr(cand)-cagr(a.spy)})
            z['costs'][str(bp)]={'candidate':cm,'excess_cagr_vs_matched':cm['cagr']-z['controls']['matched']['cagr'],'excess_cagr_vs_spy':cm['cagr']-z['controls']['spy']['cagr'],'sharpe_delta_vs_matched':cm['sharpe_rf0']-z['controls']['matched']['sharpe_rf0'],'max_drawdown_delta_vs_matched':cm['max_drawdown']-z['controls']['matched']['max_drawdown'],'positive_matched_folds':sum(x['excess_cagr_vs_matched']>0 for x in folds),'folds':folds}
        out['tests'][name]=z
    q=out['tests']['2020_forward']['costs']['50']; out['decision']='P93_SECTOR_RIDGE_SUPPORTED' if q['excess_cagr_vs_matched']>0 and q['positive_matched_folds']>=3 and q['sharpe_delta_vs_matched']>0 else 'P93_SECTOR_RIDGE_NOT_SUPPORTED'
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p93_sector_ridge_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
