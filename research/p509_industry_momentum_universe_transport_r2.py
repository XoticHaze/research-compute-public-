from __future__ import annotations
import json, runpy
from pathlib import Path
import yfinance as yf

# Chronology correction only: use completed months through 2026-08-31.
# Universe, 12-1 signal, top-3 rule, costs, controls, windows and gates remain frozen.
_orig_download=yf.download
def _completed_month_download(*args,**kwargs):
    kwargs['end']='2026-09-01'
    return _orig_download(*args,**kwargs)
yf.download=_completed_month_download
runpy.run_path('research/p509_industry_momentum_universe_transport_r1.py',run_name='__main__')
p1=Path('research/artifacts/p509_industry_momentum_universe_transport_r1.json');x=json.loads(p1.read_text())
x['schema']='research.p509_industry_momentum_universe_transport_r2.v1';x['workload_id']='P509_INDUSTRY_MOMENTUM_UNIVERSE_TRANSPORT_R2'
x['data_cutoff_correction']={'last_completed_month':'2026-08-31','supersedes_run_id':34551860278,'reason':'R1 monthly resample could include partial September 2026 as a month-end-labelled observation; R2 excludes the incomplete month without changing the test.'}
p2=Path('research/artifacts/p509_industry_momentum_universe_transport_r2.json');p2.write_text(json.dumps(x,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'revision':'R2_COMPLETED_MONTH_ONLY','decision':x['decision'],'windows':{k:{'matched_excess_pp':round(v['matched_excess_cagr']*100,3),'vs_spy_pp':round(v['vs_spy_cagr']*100,3),'positive_folds':v['positive_matched_folds'],'maxdd':round(v['candidate']['max_drawdown']*100,2)} for k,v in x['tests'].items()}},sort_keys=True))
