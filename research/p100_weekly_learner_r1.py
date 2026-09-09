import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
COSTS=(10,25,50); MIN_TRAIN=156

def cagr_blocks(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(252/(5*len(r)))-1)
def metrics(r):
 r=pd.Series(r,dtype=float).dropna(); eq=(1+r).cumprod(); ann=float(r.mean()*252/5); vol=float(r.std(ddof=1)*math.sqrt(252/5)); return {'cagr':cagr_blocks(r),'sharpe':ann/vol if vol else None,'maxdd':float((eq/eq.cummax()-1).min())}
def main():
 raw=yf.download(['QQQ','SPY','TLT','GLD'],start='2000-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna();
 f=pd.DataFrame(index=raw.index); f['q5']=raw.QQQ.pct_change(5); f['q20']=raw.QQQ.pct_change(20); f['q60']=raw.QQQ.pct_change(60); f['rv20']=raw.QQQ.pct_change().rolling(20).std(ddof=1)*math.sqrt(252); f['spy20']=raw.SPY.pct_change(20); f['tlt20']=raw.TLT.pct_change(20); f['gld20']=raw.GLD.pct_change(20); f['rel20']=f.q20-f.spy20
 idx=np.arange(65,len(raw)-6,5); rows=[]
 for t in idx:
  sig=raw.index[t]; ent=raw.index[t+1]; ex=raw.index[t+6]; x=f.iloc[t]; ret=float(raw.QQQ.iloc[t+6]/raw.QQQ.iloc[t+1]-1); rows.append((sig,ent,ex,*x.tolist(),ret))
 cols=['signal','entry','exit','q5','q20','q60','rv20','spy20','tlt20','gld20','rel20','ret']; d=pd.DataFrame(rows,columns=cols).dropna().reset_index(drop=True); feats=['q5','q20','q60','rv20','spy20','tlt20','gld20','rel20']; preds=[]
 for i,row in d.iterrows():
  eligible=d.iloc[:i]; eligible=eligible[eligible['exit']<=row['signal']]
  if len(eligible)<MIN_TRAIN: preds.append(np.nan); continue
  y=(eligible.ret>0).astype(int); model=make_pipeline(StandardScaler(),LogisticRegression(C=1.0,penalty='l2',solver='lbfgs',max_iter=1000,random_state=100)); model.fit(eligible[feats],y); preds.append(float(model.predict_proba(pd.DataFrame([row[feats].values],columns=feats))[0,1]))
 d['p']=preds; d=d.dropna(subset=['p']).copy(); d['active']=d.p>=0.5; d['gross']=np.where(d.active,d.ret,0.0)
 out={'schema':'research.p100_weekly_learner_r1','parent':'P100','hypothesis':'A strict causal fixed logistic model on lagged cross-asset daily features can identify non-overlapping five-day QQQ exposure windows with durable after-cost excess versus static QQQ.','contract':{'signal_to_entry_delay_trading_days':1,'holding_days':5,'rebalance_stride_days':5,'minimum_training_blocks':MIN_TRAIN,'features':feats,'model':'StandardScaler + L2 logistic C=1','costs_bps_roundtrip':list(COSTS),'matched_control':'static QQQ on identical entry/exit blocks','windows':['all_oos','2015','2020'],'folds':5,'no_hyperparameter_search':True,'training_eligibility':'only rows whose exit date is <= current signal date'},'tests':{}}
 for name,start in [('all_oos',None),('2015','2015-01-01'),('2020','2020-01-01')]:
  x=d if start is None else d[d.signal>=pd.Timestamp(start)]; base=metrics(x.ret); z={'blocks':len(x),'active_fraction':float(x.active.mean()),'control':base,'costs':{}}; folds=np.array_split(np.arange(len(x)),5)
  for bp in COSTS:
   cand=x.gross-x.active.astype(float)*bp/10000; cm=metrics(cand); fr=[]
   for j,ix in enumerate(folds,1):
    a=x.iloc[ix]; cr=a.gross-a.active.astype(float)*bp/10000; fr.append({'fold':j,'excess_cagr_vs_qqq':cagr_blocks(cr)-cagr_blocks(a.ret)})
   z['costs'][str(bp)]={'candidate':cm,'excess_cagr_vs_qqq':cm['cagr']-base['cagr'],'sharpe_delta_vs_qqq':cm['sharpe']-base['sharpe'],'maxdd_delta_vs_qqq':cm['maxdd']-base['maxdd'],'positive_excess_folds':sum(v['excess_cagr_vs_qqq']>0 for v in fr),'folds':fr}
  out['tests'][name]=z
 a=out['tests']['2015']['costs']['25']; b=out['tests']['2020']['costs']['25']; out['decision']='P100_WEEKLY_LEARNER_SUPPORTED' if a['excess_cagr_vs_qqq']>0 and b['excess_cagr_vs_qqq']>0 and b['positive_excess_folds']>=3 else 'P100_WEEKLY_LEARNER_NOT_SUPPORTED'; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p100_weekly_learner_r1.json').write_text(json.dumps(out,indent=2,default=str)); print(json.dumps(out,default=str))
if __name__=='__main__': main()
