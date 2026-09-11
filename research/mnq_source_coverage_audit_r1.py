from __future__ import annotations
import json,re,subprocess,tempfile
from collections import Counter,defaultdict
from datetime import datetime
from pathlib import Path
SOURCE_REPO='https://github.com/mbytes21/MNQ_DATA.git'
SOURCE_COMMIT='fc5508e2c152938d6d9eb70a36b888ae26107176'
OUT=Path('research/artifacts/mnq_source_coverage_audit_r1.json')
PAT=re.compile(r'^(?P<date>\d{8})\.Last\.csv$')

def main():
  with tempfile.TemporaryDirectory(prefix='mnq-source-') as td:
    root=Path(td)/'repo'
    subprocess.run(['git','clone','--filter=blob:none',SOURCE_REPO,str(root)],check=True,stdout=subprocess.DEVNULL)
    subprocess.run(['git','checkout',SOURCE_COMMIT],cwd=root,check=True,stdout=subprocess.DEVNULL)
    rows=[]
    for d in sorted(root.glob('MNQ ??-??')):
      if not d.is_dir(): continue
      dates=[]
      for p in d.glob('*.Last.csv'):
        m=PAT.match(p.name)
        if m: dates.append(datetime.strptime(m.group('date'),'%Y%m%d').date())
      if dates: rows.append({'contract':d.name,'sessions':len(dates),'first':min(dates).isoformat(),'last':max(dates).isoformat()})
    all_dates=sorted({datetime.strptime(PAT.match(p.name).group('date'),'%Y%m%d').date() for d in root.glob('MNQ ??-??') if d.is_dir() for p in d.glob('*.Last.csv') if PAT.match(p.name)})
    by_year=Counter(d.year for d in all_dates)
    if not all_dates: raise SystemExit('NO_MNQ_LAST_SESSIONS')
    result={'schema':'research.mnq_source_coverage_audit_r1.v1','source_repo':'mbytes21/MNQ_DATA','source_commit':SOURCE_COMMIT,'contracts':rows,'contract_count':len(rows),'unique_session_count':len(all_dates),'first_session':all_dates[0].isoformat(),'last_session':all_dates[-1].isoformat(),'sessions_by_year':{str(k):v for k,v in sorted(by_year.items())},'covers_2022':2022 in by_year,'covers_2023':2023 in by_year,'covers_2024':2024 in by_year,'covers_2025':2025 in by_year,'covers_pre_2021':any(y<2021 for y in by_year),'covers_2008':2008 in by_year,'covers_2020':2020 in by_year,'authority':'source_coverage_only','scientific_promotion':False,'runtime_authority':False,'broker_authority':False,'live_trading_change':False}
    OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n'); print(json.dumps(result,sort_keys=True))
if __name__=='__main__': main()
