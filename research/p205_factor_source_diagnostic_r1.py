import io,json,math,re,zipfile,requests
from pathlib import Path
import numpy as np,pandas as pd
URLS={"ff5":"https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_5_Factors_2x3_CSV.zip","mom":"https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Momentum_Factor_CSV.zip"}
WINDOWS={"2014":201401,"2018":201801,"2020":202001}
def fetch(url):
 b=requests.get(url,timeout=30).content; z=zipfile.ZipFile(io.BytesIO(b)); txt=z.read(z.namelist()[0]).decode('latin1'); rows=[]
 for line in txt.splitlines():
  m=re.match(r'^\s*(\d{6})\s*,(.*)$',line)
  if m: rows.append([int(m.group(1))]+[float(x.strip())/100 for x in m.group(2).split(',') if x.strip()!=''])
 return rows
ff=fetch(URLS['ff5']); mo=fetch(URLS['mom'])
# FF5 monthly columns after YYYYMM: Mkt-RF, SMB, HML, RMW, CMA, RF. Momentum monthly: Mom.
rmw=pd.Series({r[0]:r[4] for r in ff if len(r)>=7},name='RMW'); mom=pd.Series({r[0]:r[1] for r in mo if len(r)>=2},name='MOM')
def diag(s,start):
 x=s[s.index>=start].dropna(); folds=np.array_split(x.to_numpy(),5); ann=float(x.mean()*12); sh=float(x.mean()/x.std(ddof=0)*math.sqrt(12)) if x.std(ddof=0)>0 else None
 return {"months":len(x),"annualized_mean":ann,"sharpe_like":sh,"positive_month_fraction":float((x>0).mean()),"positive_fold_means":sum(float(np.mean(f))>0 for f in folds),"fold_annualized_means":[float(np.mean(f)*12) for f in folds]}
tests={"RMW":{k:diag(rmw,v) for k,v in WINDOWS.items()},"MOM":{k:diag(mom,v) for k,v in WINDOWS.items()}}
out={"schema":"research.p205_factor_source_diagnostic_r1","parent":"P205","purpose":"Independent academic factor-source diagnostic after live QUAL/MTUM fund-wrapper tests. This does not claim investability or after-cost returns; it distinguishes weak underlying factor premia from ETF implementation/style-control failure.","source":{"provider":"Kenneth R. French Data Library","urls":URLS},"tests":tests,"interpretation":{"RMW":"If academic RMW remains positive/fold-persistent while QUAL fails SPY/IWF, treat P203 primarily as fund-wrapper/style-implementation failure rather than proof quality premium vanished.","MOM":"If academic MOM remains positive/fold-persistent while MTUM fails IWF/recent windows, treat P204 as live-wrapper/style/regime weakness rather than proof momentum premium vanished."},"no_parameter_or_period_search":True,"boundaries":{"investable_model_claim":False,"portfolio_ranking":False,"product_runtime":False,"broker":False,"live_trading":False}}
Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p205_factor_source_diagnostic_r1.json').write_text(json.dumps(out,sort_keys=True,indent=2)); print(json.dumps(out,sort_keys=True))