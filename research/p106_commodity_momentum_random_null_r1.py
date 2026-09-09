from __future__ import annotations
import json,hashlib
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
U=['GLD','SLV','USO','UNG','DBA','DBB']; ALL=U+['SPY']; LB=12; SKIP=1; TOPK=2; BP=50; REPS=2000; SEED=10601

def cagr(r):
 r=np.asarray(r,float); return float(np.prod(1+r)**(12/len(r))-1)
def build():
 raw=yf.download(ALL,start='2007-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna().astype(float); last=pd.Timestamp(raw.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cutoff=last.to_period('M').start_time-pd.Timedelta(days=1); m=raw.resample('ME').last(); m=m[m.index<=cutoff]; rows=[]
 for i in range(LB+SKIP,len(m)-1):
  score=np.array([float(m[s].iloc[i-SKIP]/m[s].iloc[i-LB]-1) for s in U]); r=np.array([float(m[s].iloc[i+1]/m[s].iloc[i]-1) for s in U]); actual=np.argsort(-score)[:TOPK]; rows.append((m.index[i+1],r,actual))
 return raw,m,rows

def stream(rows,picks):
 prev=np.zeros(len(U)); out=[]
 for (_,r,_),ix in zip(rows,picks):
  w=np.zeros(len(U)); w[ix]=1/TOPK; turn=.5*np.abs(w-prev).sum(); out.append(float(w@r-turn*BP/10000)); prev=w
 return np.array(out)
def test(rows,start):
 q=[x for x in rows if x[0]>=pd.Timestamp(start)]; actual_picks=[x[2] for x in q]; actual=stream(q,actual_picks); matched=np.array([x[1].mean() for x in q]); actual_excess=cagr(actual)-cagr(matched); rng=np.random.default_rng(SEED+int(start[:4])); null=[]
 for _ in range(REPS):
  picks=[rng.choice(len(U),size=TOPK,replace=False) for _ in q]; n=stream(q,picks); null.append(cagr(n)-cagr(matched))
 null=np.array(null); return {'months':len(q),'actual_excess_cagr':actual_excess,'actual_cagr':cagr(actual),'matched_cagr':cagr(matched),'null_mean_excess_cagr':float(null.mean()),'null_p95_excess_cagr':float(np.quantile(null,.95)),'null_p99_excess_cagr':float(np.quantile(null,.99)),'actual_percentile':float((null<actual_excess).mean()),'p_null_ge_actual':float((null>=actual_excess).mean()),'replications':REPS}
def main():
 raw,m,rows=build(); tests={k:test(rows,v) for k,v in {'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01'}.items()}; a=tests['2015']; b=tests['2020']; ok=a['actual_excess_cagr']>0 and b['actual_excess_cagr']>0 and a['p_null_ge_actual']<=.10 and b['p_null_ge_actual']<=.10
 out={'schema':'research.p106_commodity_momentum_random_null_r1','parent':'P106','hypothesis':'P106 same-universe commodity excess is selection-specific rather than an artifact of randomly rotating two commodity ETFs.','contract':{'universe':U,'actual_signal':'lagged 12-to-1 top2 momentum','cost_bps_turnover':BP,'null':'2000 independent monthly random top2 selectors with identical turnover accounting','seed':SEED,'matched_control':'same-universe equal weight','windows':['2010','2015','2020'],'no_parameter_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(m.index[-1].date()),'panel_sha256':hashlib.sha256(m.reset_index().to_csv(index=False).encode()).hexdigest()},'tests':tests,'decision':'P106_SELECTION_SPECIFICITY_SUPPORTED' if ok else 'P106_SELECTION_SPECIFICITY_NOT_SUPPORTED'}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p106_commodity_momentum_random_null_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
