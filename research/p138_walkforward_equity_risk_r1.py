from __future__ import annotations
import hashlib,json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression

COSTS=(25,50,100)
FEATURES=('mom1','mom3','mom12','rv21','dd63','qqq_rel3')

def cagr(r):
    r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')
def stats(r):
    r=pd.Series(r,dtype=float).dropna(); eq=(1+r).cumprod(); vol=float(r.std(ddof=1)*math.sqrt(12)) if len(r)>1 else float('nan'); ann=float(r.mean()*12) if len(r) else float('nan')
    return {'cagr':cagr(r),'sharpe_rf0':ann/vol if vol and np.isfinite(vol) else None,'maxdd':float((eq/eq.cummax()-1).min()) if len(eq) else None}
def evaluate(q,cost):
    z=q.copy(); z['turnover']=(z.exposure-z.exposure.shift()).abs(); z.loc[z.index[0],'turnover']=1.; z['net']=z.gross-z.turnover*cost/10000
    mx=float(z.exposure.mean()); z['matched']=mx*z.spy+(1-mx)*z.bil
    out={k:stats(z[k]) for k in ('net','matched','spy')}; out.update({'excess_matched':out['net']['cagr']-out['matched']['cagr'],'excess_spy':out['net']['cagr']-out['spy']['cagr'],'months':len(z),'mean_spy_exposure':mx,'avg_turnover':float(z.turnover.mean()),'mean_probability':float(z.prob.mean())})
    fs=[]
    for j,ii in enumerate(np.array_split(np.arange(len(z)),5),1):
        a=z.iloc[ii]; fs.append({'fold':j,'matched_excess':cagr(a.net)-cagr(a.matched),'spy_excess':cagr(a.net)-cagr(a.spy)})
    out['positive_matched_folds']=sum(x['matched_excess']>0 for x in fs); out['positive_spy_folds']=sum(x['spy_excess']>0 for x in fs); out['folds']=fs; return out

def main():
    px=yf.download(['SPY','BIL','QQQ'],start='2006-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna().astype(float)
    last=pd.Timestamp(px.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cut=last.to_period('M').start_time-pd.Timedelta(days=1); px=px.loc[px.index<=cut]
    d=px.pct_change(fill_method=None); m=px.resample('ME').last(); mr=m.pct_change(fill_method=None)
    feat=[]
    for i,dt in enumerate(m.index[:-1]):
        hist=d.loc[:dt,'SPY'].dropna(); nxt=m.index[i+1]
        if len(hist)<63 or i<12 or nxt not in mr.index: continue
        spy=float(mr.loc[nxt,'SPY']); bil=float(mr.loc[nxt,'BIL'])
        vals={'mom1':float(m.loc[dt,'SPY']/m.iloc[i-1].SPY-1),'mom3':float(m.loc[dt,'SPY']/m.iloc[i-3].SPY-1),'mom12':float(m.loc[dt,'SPY']/m.iloc[i-12].SPY-1),'rv21':float(hist.tail(21).std(ddof=1)*math.sqrt(252)),'dd63':float(px.loc[:dt,'SPY'].tail(63).iloc[-1]/px.loc[:dt,'SPY'].tail(63).cummax().iloc[-1]-1),'qqq_rel3':float((m.loc[dt,'QQQ']/m.iloc[i-3].QQQ)/(m.loc[dt,'SPY']/m.iloc[i-3].SPY)-1)}
        feat.append({'signal_month':dt,'return_month':nxt,**vals,'spy':spy,'bil':bil,'label':int(spy>bil)})
    f=pd.DataFrame(feat)
    rows=[]
    for _,r in f.iterrows():
        train=f[f.return_month<=r.signal_month]
        if len(train)<60 or train.label.nunique()<2: continue
        model=Pipeline([('scale',StandardScaler()),('lr',LogisticRegression(C=1.0,solver='lbfgs',max_iter=1000,random_state=0))])
        model.fit(train[list(FEATURES)],train.label); p=float(model.predict_proba(pd.DataFrame([{k:r[k] for k in FEATURES}]))[0,1]); x=1.0 if p>0.5 else 0.0
        rows.append({'signal_month':r.signal_month,'return_month':r.return_month,'prob':p,'exposure':x,'spy':float(r.spy),'bil':float(r.bil),'gross':x*float(r.spy)+(1-x)*float(r.bil),'train_n':len(train)})
    q=pd.DataFrame(rows).set_index('return_month'); windows={'2015':'2015-01-01','2020':'2020-01-01','2022':'2022-01-01'}
    tests={w:{str(c):evaluate(q.loc[pd.Timestamp(s):],c) for c in COSTS} for w,s in windows.items()}; a=tests['2015']['50']; b=tests['2020']['50']
    decision='P138_WALKFORWARD_EQUITY_RISK_SUPPORTED_FOR_INDEPENDENT_VALIDATION' if a['excess_matched']>0 and a['positive_matched_folds']>=3 and b['excess_matched']>0 and b['positive_matched_folds']>=3 and a['net']['sharpe_rf0']>a['matched']['sharpe_rf0'] else 'P138_WALKFORWARD_EQUITY_RISK_NOT_SUPPORTED'
    out={'schema':'research.p138_walkforward_equity_risk_r1','parent':'P138','hypothesis':'A fixed expanding walk-forward logistic model using only already-observed market state can classify next-month SPY excess over BIL well enough to create after-cost matched alpha without parameter search.','contract':{'model':'StandardScaler + LogisticRegression(C=1.0), expanding monthly retrain, 60 labeled months minimum','features':list(FEATURES),'decision_threshold':0.5,'allocation':'SPY if p>0.5 else BIL','cost_bps':list(COSTS),'matched_control':'static SPY/BIL blend at evaluated-window mean SPY exposure','opportunity_control':'SPY','windows':list(windows),'folds':5,'label_availability':'training rows require target return_month <= current signal_month','no_feature_hyperparameter_threshold_cost_or_asset_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only dynamic source, not promotion-grade','last_complete_month_end':str(cut.date()),'panel_sha256':hashlib.sha256(px.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest()},'tests':tests,'decision':decision}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p138_walkforward_equity_risk_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
