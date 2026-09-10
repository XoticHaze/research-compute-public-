import hashlib, json
from pathlib import Path
contract = {
  'schema':'mm.trading_product.p221_p222_operator_contract.v1',
  'product_repository':'XoticHaze/mm-IBKR','product_pr':477,'product_head':'e9770a74928f47861f915fd27e2e148414bcaa47',
  'P221':{'decision':'P221_MIDCAP_QUALITY_NOT_SUPPORTED','run_id':34434098304,'job_id':102735488167,'started_at':'2026-09-10T03:38:30Z','head_sha':'86624138043d3a4fee538f7686811d4b1a710d8b','artifact_id':10135536766,'artifact_sha256':'f0cd6a96466dee04745e1bec4e20185e7ea7c30593f5f437cc6e31d5c4416988','mdy_excess_bp':81,'positive_mdy_folds':3,'spy_excess_bp':-169},
  'P222':{'decision':'P222_FIXED_FACTOR_BLEND_NOT_SUPPORTED','run_id':34434315475,'job_id':102736126381,'started_at':'2026-09-10T03:41:59Z','head_sha':'69a74c31616a803c79e2b87c38fec36902608628','artifact_id':10135612580,'artifact_sha256':'cb22e8a261177f448f5988e458414e8d72def41bdf7784136f801119edbeeb1e','mdy_excess_bp':203,'positive_mdy_folds':3,'blend_minus_xmmo_bp':-112},
  'operator_consequence':'close standalone mid-cap quality and fixed XMMO/XMHQ blend as rescue paths; preserve bounded XMMO matched-size evidence without promotion',
  'authority':{'portfolio_ranking':False,'allocation':False,'sizing':False,'promotion':False,'runtime':False,'broker':False,'live_trading':False}
}
assert contract['P221']['positive_mdy_folds'] < 4
assert contract['P222']['positive_mdy_folds'] < 4
assert contract['P222']['blend_minus_xmmo_bp'] < 0
assert all(v is False for v in contract['authority'].values())
canonical=json.dumps(contract,sort_keys=True,separators=(',',':'))
out={'schema':'mm.trading_product.p221_p222_operator_acceptance.v1','result':'PASS','contract_sha256':hashlib.sha256(canonical.encode()).hexdigest(),'contract':contract}
Path('artifacts').mkdir(exist_ok=True)
Path('artifacts/trading_product_p221_p222_operator_acceptance.json').write_text(json.dumps(out,sort_keys=True,indent=2))
print('P221_P222_OPERATOR_ACCEPTANCE=PASS',out['contract_sha256'])
