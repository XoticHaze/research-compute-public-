from __future__ import annotations
import io, json, math, urllib.request, zipfile
from pathlib import Path
import numpy as np, pandas as pd
URL='https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/10_Industry_Portfolios_CSV.zip'; COST_BPS=25; TOP_K=3
raw=urllib.request.urlopen(URL,timeout=30).read(); zf=zipfile.ZipFile(io.BytesIO(raw)); text=zf.read(zf.namelist()[0]).decode('latin1'); lines=text.splitlines()
start=next(i for i,l in enumerate(lines) if l.strip().startswith('Average Equal Weighted Returns -- Monthly'))+1
rows=[]
for l in lines[start:]:
    if not l.strip():
        if rows: break
        continue
    parts=[x.strip() for x in l.split(',')]
    if parts[0].isdigit() and len(parts[0])==6: rows.append(parts)
cols=['date','NoDur','Durbl','Manuf','Enrgy','HiTec','Telcm','Shops','Hlth','Utils','Other']; df=pd.DataFrame(rows,columns=cols); df['date']=pd.to_datetime(df.date,format='%Y%m'); r=df.set_index('date').astype(float)/100.0
score=((1+r).rolling(11).apply(np.prod,raw=True)-1).shift(1); outrows=[]
for dt in r.index:
    s=score.loc[dt].dropna()
    if len(s)<TOP_K: continue
    top=s.nlargest(TOP_K).index; cur=r.loc[dt]; outrows.append((dt,float(cur[top].mean()),float(cur.mean()),tuple(top)))
x=pd.DataFrame(outrows,columns=['date','gross','matched','top']).set_index('date'); prev=set(); net=[]; turns=[]
for _,row in x.iterrows():
    cur=set(row.top); turn=1.0 if not prev else 1.0-len(prev&cur)/TOP_K; net.append(row.gross-turn*COST_BPS/10000); turns.append(turn); prev=cur
x['strategy']=net; x['turnover']=turns
def stats(s):
    s=s.dropna(); w=(1+s).cumprod(); yrs=len(s)/12; sd=s.std(); return {'months':int(len(s)),'cagr':float(w.iloc[-1]**(1/yrs)-1),'sharpe':float(s.mean()/sd*math.sqrt(12)) if sd>0 else 0.0,'max_drawdown':float((w/w.cummax()-1).min())}
res={}
for name,startd in {'2000_plus':'2000-01-01','2005_plus':'2005-01-01','2010_plus':'2010-01-01','2015_plus':'2015-01-01','2020_plus':'2020-01-01'}.items():
    q=x.loc[startd:]; a,b=stats(q.strategy),stats(q.matched); res[name]={'strategy':a,'equal_industry_matched':b,'matched_excess_cagr':a['cagr']-b['cagr'],'mean_turnover':float(q.turnover.mean())}
q=x.loc['2000-01-01':]; folds=[stats(f.strategy)['cagr']-stats(f.matched)['cagr'] for f in np.array_split(q,5)]; passed=all(v['matched_excess_cagr']>0 for v in res.values()) and sum(v>0 for v in folds)>=3
decision='P341_FRENCH_EQUALWEIGHT_INDUSTRY_MOMENTUM_SUPPORTED' if passed else 'P341_FRENCH_EQUALWEIGHT_INDUSTRY_MOMENTUM_NOT_SUPPORTED'
out={'schema':'research.p341_french_equalweight_industry_momentum_r1','parent':'P341','claim':'Orthogonal weighting-representation adjudicator for P340: apply the unchanged causal 12-1-equivalent top-3 rule to Kenneth French equal-weighted 10 Industry Portfolios, with identical 25bp one-way turnover friction, equal-industry matched control, windows and folds. No signal, top-k, industry-set, cost, or date tuning.','source':URL,'representation':'Average Equal Weighted Returns -- Monthly','top_k':TOP_K,'cost_bps':COST_BPS,'results':res,'chronology_fold_matched_excess_cagr':folds,'positive_folds':sum(v>0 for v in folds),'decision_rule':'Support weighting robustness only if after-cost matched excess is positive in all fixed windows and >=3/5 chronology folds. Failure narrows mechanism robustness to the value-weighted representation without parameter rescue.','decision':decision,'limitations':['academic industry portfolios are not direct executable ETF sleeves','same academic source as P340 but independent weighting representation','no portfolio ranking/allocation/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p341_french_equalweight_industry_momentum_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
