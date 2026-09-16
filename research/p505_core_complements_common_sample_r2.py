from __future__ import annotations
import json, runpy
from pathlib import Path
import yfinance as yf

# Scientific-integrity correction only: prevent the September 2026 partial month
# from being labeled as the completed 2026-09-30 month by pandas resample('ME').
# All P505 identities, weights, costs, controls, gates, and dates otherwise remain frozen.
_orig_download = yf.download
def _completed_month_download(*args, **kwargs):
    kwargs['end'] = '2026-09-01'
    return _orig_download(*args, **kwargs)
yf.download = _completed_month_download

runpy.run_path('research/p505_core_complements_common_sample_r1.py', run_name='__main__')
p1=Path('research/artifacts/p505_core_complements_common_sample_r1.json')
x=json.loads(p1.read_text())
x['schema']='research.p505_core_complements_common_sample_r2.v1'
x['workload_id']='P505_CORE_COMPLEMENTS_COMMON_SAMPLE_R2'
x['data_cutoff_correction']={
  'last_completed_month':'2026-08-31',
  'supersedes_run_id':34551419641,
  'reason':'R1 resample(ME) labeled partial September observations as 2026-09-30; R2 excludes the incomplete current month without changing hypothesis, weights, costs, controls, or gates.'
}
p2=Path('research/artifacts/p505_core_complements_common_sample_r2.json')
p2.write_text(json.dumps(x,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'revision':'R2_COMPLETED_MONTH_ONLY','decision':x['decision'],'coverage':x['coverage'],'core':{k:round(x['full_sample']['P249_P266_CORE'][k],4) for k in ['cagr','matched_excess_cagr','sharpe','max_drawdown']},'roles':x['scientific_portfolio_roles'],'complements':{k:{m:round(x['full_sample'][k][m],4) for m in ['cagr','matched_excess_cagr','vs_core_cagr','sharpe','max_drawdown']} for k in x['scientific_portfolio_roles']}},sort_keys=True))
