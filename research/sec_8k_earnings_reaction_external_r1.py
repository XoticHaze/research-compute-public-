import json
from pathlib import Path
import sec_8k_earnings_reaction_drift_r1 as m

EXPERIMENT_ID='SEC_8K_EARNINGS_REACTION_EXTERNAL_R1_20260913'
OUT=Path('research/results/sec_8k_earnings_reaction_external_r1.json')
T={'ORCL':'XLK','CRM':'XLK','ADBE':'XLK','CSCO':'XLK','MU':'SMH','QCOM':'SMH','TXN':'SMH','KLAC':'SMH','MS':'XLF','C':'XLF','WFC':'XLF','BLK':'XLF','EOG':'XLE','SLB':'XLE','OXY':'XLE','DE':'XLI','UPS':'XLI','RTX':'XLI','PFE':'XLV','ABBV':'XLV','MRK':'XLV','WMT':'XLP','COST':'XLP','MDLZ':'XLP','LOW':'XLY','SBUX':'XLY','TJX':'XLY','DIS':'XLC','T':'XLC','VZ':'XLC','SO':'XLU','AEP':'XLU','NUE':'XLB','SHW':'XLB','EQIX':'XLRE','O':'XLRE'}

def main():
    m.E=EXPERIMENT_ID
    m.T=T
    m.main()
    src=Path('research/results/sec_8k_earnings_reaction_drift_r1.json')
    out=json.loads(src.read_text())
    out['schema']='public_research.sec_8k_earnings_reaction_external_result.v1'
    out['experiment_id']=EXPERIMENT_ID
    out['inherited_learning_ids']=['SLP-20260913-SEC-8K-EARNINGS-REACTION-DRIFT-R1','SLP-20260913-SEC-8K-MANAGEMENT-REACTION-DRIFT-R1']
    out['frozen_specification']['ticker_to_sector']=T
    out['frozen_specification']['disjoint_from_discovery_panel']=True
    r=out['result']
    if r['decision']=='SEC_8K_EARNINGS_REACTION_DRIFT_SURVIVES_R1':r['decision']='SEC_8K_EARNINGS_REACTION_EXTERNAL_SURVIVES_R1'
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    print(json.dumps(r,sort_keys=True))

if __name__=='__main__':main()
