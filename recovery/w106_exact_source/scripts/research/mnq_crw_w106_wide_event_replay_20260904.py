from __future__ import annotations

# Exact frozen W106 producer transported from mm-IBKR@76aa7e9bb64a1aca36865076df1fa4b25f1b06a9.
# Research-only transport. No runtime, promotion, broker, or live-trading authority.

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from scripts.research.mnq_crw_canonical_replay_20260901 import EXPECTED_STRATEGY_SPEC_DIGEST, RUNTIME_ID, load_runtime_authority
from scripts.research.mnq_crw_lifecycle_replay_20260901 import replay_lifecycle

WINDOW = 106
ENTRY = -2.7
EXIT = 4.25
LADDER = [2.5, 5.0, 6.0, 8.0]
TRANCHE_FRACTION = 0.2
COMMISSION_POINTS_PER_CONTRACT_SIDE = 0.3
EXPECTED = {"closed_trades":107,"mean_dca_adds":0.5887850467289719,"mean_peak_deployed_fraction_closed":0.3177570093457944,"full_budget_deployed_trade_fraction":0.009345794392523364,"net_points_per_max_contract_equivalent":10208.350000000011,"max_drawdown_points_per_max_contract_equivalent":733.2800000000016,"profit_factor":4.684327348190937}

def wide_params(base: dict[str, Any]) -> dict[str, Any]:
    params=dict(base); params.update({"WINDOW":WINDOW,"window":WINDOW,"ENTRY_EXTREME":ENTRY,"entry_threshold":ENTRY,"EXIT_EXTREME":EXIT,"exit_threshold":EXIT,"DCA_TIER_DRAWDOWNS_PCT":list(LADDER),"dca_tier_drawdowns_pct":list(LADDER),"DCA_MAX_ADDS":len(LADDER),"max_dca_adds":len(LADDER)}); return params

def _sequence_drawdown(values: np.ndarray) -> float:
    curve=np.cumsum(values)
    if len(curve)==0:return 0.0
    augmented=np.r_[0.0,curve]; running_max=np.maximum.accumulate(augmented); return float(np.max(running_max-augmented))

def _normalized_trade_rows(trades: pd.DataFrame) -> pd.DataFrame:
    rows=[]
    for trade_index,trade in trades.reset_index(drop=True).iterrows():
        fills=json.loads(trade["fills_json"]); tranche_units=len(fills)
        if tranche_units != 1+int(trade["dca_count"]): raise ValueError("fill history and dca_count disagree")
        gross=float(trade["gross_contract_points"])*TRANCHE_FRACTION; cost=2*COMMISSION_POINTS_PER_CONTRACT_SIDE*tranche_units*TRANCHE_FRACTION
        rows.append({"trade_index":int(trade_index),"source_contract":str(trade["source_contract"]),"entry_signal_timestamp":str(trade["entry_signal_timestamp"]),"entry_fill_timestamp":str(trade["entry_fill_timestamp"]),"exit_fill_timestamp":str(trade["exit_fill_timestamp"]),"dca_count":int(trade["dca_count"]),"peak_deployed_fraction":float(tranche_units*TRANCHE_FRACTION),"full_budget_deployed":bool(tranche_units==5),"gross_points_per_max_contract_equivalent":gross,"net_points_per_max_contract_equivalent":gross-cost,"fills_json":str(trade["fills_json"])})
    return pd.DataFrame(rows)

def summarize(trades: pd.DataFrame, normalized: pd.DataFrame) -> dict[str, Any]:
    net=normalized["net_points_per_max_contract_equivalent"].to_numpy(float); pos=net[net>0]; neg=net[net<0]
    metrics={"closed_trades":len(normalized),"mean_dca_adds":float(trades["dca_count"].mean()),"mean_peak_deployed_fraction_closed":float(normalized["peak_deployed_fraction"].mean()),"full_budget_deployed_trade_fraction":float(normalized["full_budget_deployed"].mean()),"net_points_per_max_contract_equivalent":float(net.sum()),"max_drawdown_points_per_max_contract_equivalent":_sequence_drawdown(net),"profit_factor":float(pos.sum()/-neg.sum()) if len(neg) else None}
    parity={k:{"actual":metrics[k],"expected":v,"pass":abs(float(metrics[k])-float(v)) <= (1e-9 if k=="closed_trades" else max(1e-9,abs(float(v))*1e-8))} for k,v in EXPECTED.items()}
    return {"schema":"mm.mnq_crw_w106_wide_event_replay.v1","research_only":True,"configuration":{"window":WINDOW,"entry":ENTRY,"exit":EXIT,"ladder_pct":LADDER,"tranche_fraction":TRANCHE_FRACTION},"metrics":metrics,"accepted_screen_parity":parity,"accepted_screen_parity_pass":all(x["pass"] for x in parity.values()),"promotion_authority":False,"runtime_authority":False,"broker_authority":False,"live_trading_change":False}

def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument("--bars",type=Path,required=True); p.add_argument("--runtime-config",type=Path,default=Path("config/selected_runtime_universe_14tu.json")); p.add_argument("--output-root",type=Path,required=True); a=p.parse_args()
    runtime=load_runtime_authority(a.runtime_config,runtime_id=RUNTIME_ID,expected_digest=EXPECTED_STRATEGY_SPEC_DIGEST); params=wide_params(dict(runtime["strategy_spec"]["parameters"])); bars=pd.read_csv(a.bars); trades,lifecycle=replay_lifecycle(bars,strategy_params=params); normalized=_normalized_trade_rows(trades); result=summarize(trades,normalized); result["lifecycle"]=lifecycle
    a.output_root.mkdir(parents=True,exist_ok=True); trades.to_csv(a.output_root/"mnq-w106-wide-trades.csv",index=False); normalized.to_csv(a.output_root/"mnq-w106-wide-capital-normalized-trades.csv",index=False); (a.output_root/"mnq-w106-wide-result.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps(result,sort_keys=True)); return 0

if __name__ == "__main__": raise SystemExit(main())
