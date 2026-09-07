from __future__ import annotations

import bisect
import hashlib
import io
import json
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

import opportunity_cross_family_stagea_capacity_allocator_20260907 as hb_bio
import opportunity_prior_alpha_blend_disjoint_family_confirmation_20260907 as disjoint

OUT = Path("opportunity_option_implied_vol_state_allocator_20260907.json")
FRED_BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv"
SERIES = ("VIXCLS", "VXVCLS")
EVAL_FOLDS = (4, 5, 6)
NORMAL_CAPACITY = 3
STRESS_CAPACITY = 1


def fetch_vol_state():
    query = urlencode({"id": ",".join(SERIES), "cosd": "2014-01-01", "coed": "2026-09-01"})
    url = FRED_BASE + "?" + query
    req = Request(url, headers={"User-Agent": "research-compute-public/1.0", "Accept": "text/csv,*/*"})
    with urlopen(req, timeout=60) as response:
        raw = response.read()
    frame = pd.read_csv(io.BytesIO(raw))
    if frame.columns.tolist() != ["observation_date", *SERIES]:
        raise RuntimeError(f"unexpected FRED columns={frame.columns.tolist()}")
    frame["observation_date"] = pd.to_datetime(frame["observation_date"], errors="raise").dt.date
    for col in SERIES:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.dropna().sort_values("observation_date")
    if len(frame) < 2500:
        raise RuntimeError(f"insufficient VIX/VXV overlap rows={len(frame)}")
    if frame["observation_date"].max().isoformat() < "2026-08-28":
        raise RuntimeError("volatility source unexpectedly stale")
    rows = [
        {
            "date": row.observation_date.isoformat(),
            "vix": float(row.VIXCLS),
            "vix3m": float(row.VXVCLS),
            "front_over_3m": float(row.VIXCLS / row.VXVCLS),
            "backwardation": bool(row.VIXCLS > row.VXVCLS),
        }
        for row in frame.itertuples(index=False)
        if row.VIXCLS > 0 and row.VXVCLS > 0
    ]
    canonical = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return rows, {
        "source": "FRED graph CSV; CBOE VIX/VIX3M daily close series",
        "series": list(SERIES),
        "url_query": query,
        "raw_response_sha256": hashlib.sha256(raw).hexdigest(),
        "canonical_rows_sha256": hashlib.sha256(canonical).hexdigest(),
        "rows": len(rows),
        "first": rows[0]["date"],
        "last": rows[-1]["date"],
        "causal_join": "strictly previous published market close; same-day volatility close is never used for an opportunity entry",
    }


def annotate(records, calendar, vol_rows):
    dates = [pd.Timestamp(row["date"]).date() for row in vol_rows]
    by_date = {pd.Timestamp(row["date"]).date(): row for row in vol_rows}
    out = []
    for record in records:
        entry_date = pd.Timestamp(calendar[int(record["entry_i"])]).date()
        pos = bisect.bisect_left(dates, entry_date) - 1
        if pos < 0:
            continue
        state = by_date[dates[pos]]
        node = dict(record)
        node["vol_state_date"] = state["date"]
        node["vix"] = state["vix"]
        node["vix3m"] = state["vix3m"]
        node["vix_front_over_3m"] = state["front_over_3m"]
        node["vol_stress"] = state["backwardation"]
        out.append(node)
    return out


def simulate(records, fold, stress_scaled):
    grouped = defaultdict(list)
    for record in records:
        if record["fold"] == fold:
            grouped[record["entry_i"]].append(record)
    slots = [
        {"stock": 1.0 / NORMAL_CAPACITY, "etf": 1.0 / NORMAL_CAPACITY, "qqq": 1.0 / NORMAL_CAPACITY, "record": None, "exit_i": -1}
        for _ in range(NORMAL_CAPACITY)
    ]
    accepted = []

    def realize(index):
        for slot in slots:
            rec = slot["record"]
            if rec is not None and slot["exit_i"] <= index:
                slot["stock"] *= 1.0 + rec["stock_net"]
                slot["etf"] *= 1.0 + rec["etf_net"]
                slot["qqq"] *= 1.0 + rec["qqq_net"]
                slot["record"] = None
                slot["exit_i"] = -1

    for entry_i in sorted(grouped):
        realize(entry_i)
        active = [slot for slot in slots if slot["record"] is not None]
        day = grouped[entry_i]
        stress = bool(day[0]["vol_stress"])
        if any(bool(r["vol_stress"]) != stress for r in day):
            raise RuntimeError("same entry index has inconsistent volatility state")
        capacity = STRESS_CAPACITY if stress_scaled and stress else NORMAL_CAPACITY
        available_count = max(0, capacity - len(active))
        if available_count <= 0:
            continue
        free = [slot for slot in slots if slot["record"] is None][:available_count]
        active_symbols = {slot["record"]["symbol"] for slot in active}
        ordered = sorted(day, key=lambda r: (-r["prediction_bps"], r["family"], r["symbol"]))
        for rec in ordered:
            if not free:
                break
            if rec["symbol"] in active_symbols:
                continue
            slot = free.pop(0)
            slot["record"] = rec
            slot["exit_i"] = rec["exit_i"]
            active_symbols.add(rec["symbol"])
            accepted.append(rec)
    realize(10**9)
    stock = float(sum(slot["stock"] for slot in slots))
    etf = float(sum(slot["etf"] for slot in slots))
    qqq = float(sum(slot["qqq"] for slot in slots))
    return {
        "stock_return": stock - 1.0,
        "matched_etf_return": etf - 1.0,
        "qqq_return": qqq - 1.0,
        "stock_minus_matched_etf": stock - etf,
        "stock_minus_qqq": stock - qqq,
        "accepted_trades": len(accepted),
        "stress_trades": sum(bool(r["vol_stress"]) for r in accepted),
    }


def conditional_info(records):
    result = {}
    for stress, label in ((False, "contango_or_flat"), (True, "backwardation")):
        rows = [r for r in records if bool(r["vol_stress"]) == stress and r["fold"] in EVAL_FOLDS]
        result[label] = {
            "candidate_states": len(rows),
            "mean_matched_excess_bps": float(np.mean([r.get("stock_minus_etf_bps", r.get("matched_excess_bps")) for r in rows])) if rows else None,
            "positive_matched_excess_share": float(np.mean([r.get("stock_minus_etf_bps", r.get("matched_excess_bps")) > 0 for r in rows])) if rows else None,
            "mean_prediction_bps": float(np.mean([r["prediction_bps"] for r in rows])) if rows else None,
        }
    return result


def surface(name, records):
    folds = []
    for fold in EVAL_FOLDS:
        folds.append({
            "fold": fold,
            "raw_capacity3": simulate(records, fold, False),
            "vix_backwardation_cap1": simulate(records, fold, True),
        })

    def aggregate(policy):
        rows = [row[policy] for row in folds]
        sw = float(np.prod([1.0 + r["stock_return"] for r in rows]) - 1.0)
        ew = float(np.prod([1.0 + r["matched_etf_return"] for r in rows]) - 1.0)
        qw = float(np.prod([1.0 + r["qqq_return"] for r in rows]) - 1.0)
        return {
            "compound_stock_return": sw,
            "compound_matched_etf_return": ew,
            "compound_qqq_return": qw,
            "compound_stock_minus_matched_etf": sw - ew,
            "compound_stock_minus_qqq": sw - qw,
            "accepted_trades": sum(r["accepted_trades"] for r in rows),
            "stress_trades": sum(r["stress_trades"] for r in rows),
            "fold_stock_returns": [r["stock_return"] for r in rows],
            "fold_matched_excess": [r["stock_minus_matched_etf"] for r in rows],
        }

    control = aggregate("raw_capacity3")
    challenger = aggregate("vix_backwardation_cap1")
    fold_wins = sum(row["vix_backwardation_cap1"]["stock_return"] > row["raw_capacity3"]["stock_return"] for row in folds)
    positive_excess = sum(row["vix_backwardation_cap1"]["stock_minus_matched_etf"] > 0 for row in folds)
    supported = bool(
        challenger["compound_stock_return"] > control["compound_stock_return"]
        and challenger["compound_stock_minus_matched_etf"] > control["compound_stock_minus_matched_etf"]
        and challenger["compound_stock_minus_qqq"] > control["compound_stock_minus_qqq"]
        and fold_wins >= 2
        and positive_excess >= 2
        and challenger["accepted_trades"] >= 0.60 * control["accepted_trades"]
    )
    return {
        "name": name,
        "candidate_states": len(records),
        "conditional_information": conditional_info(records),
        "folds": folds,
        "aggregate": {"raw_capacity3": control, "vix_backwardation_cap1": challenger},
        "gate": {
            "decision": "SUPPORTED" if supported else "NOT_SUPPORTED",
            "fold_wins_vs_raw": fold_wins,
            "positive_matched_etf_excess_folds": positive_excess,
        },
    }


def main():
    vol_rows, source_receipt = fetch_vol_state()
    stagea = hb_bio.load_adapter()
    contract = json.loads(hb_bio.CONTRACT.read_text(encoding="utf-8"))
    cal_a, _, _, rec_a = hb_bio.build_records(stagea, contract)
    cal_b, rec_b = disjoint.build_records(stagea)
    rec_a = annotate(rec_a, cal_a, vol_rows)
    rec_b = annotate(rec_b, cal_b, vol_rows)
    a = surface("homebuilders_biotech", rec_a)
    b = surface("consumer_staples_metals_reits_pharma", rec_b)
    both = a["gate"]["decision"] == "SUPPORTED" and b["gate"]["decision"] == "SUPPORTED"
    receipt = {
        "schema": "public_research.opportunity_option_implied_vol_state_allocator.v1",
        "research_only": True,
        "parent_id": "P05",
        "objective": "Test whether a genuinely independent option-implied stress state improves scarce-capital opportunity timing across two previously frozen cross-family surfaces.",
        "source": source_receipt,
        "representation": {
            "stress": "previous available CBOE VIX close > previous available CBOE 3-month VIX close",
            "control": "raw Stage-A prediction, capacity 3",
            "challenger": "same raw ranking and exits; during backwardation only one of three 1/3-capital risky slots may be occupied by new entries; existing positions are never force-closed",
            "same_day_close_used": False,
            "threshold_search": False,
            "blend_weight_search": False,
        },
        "surfaces": [a, b],
        "parent_gate": "SUPPORTED_BOTH_SURFACES" if both else "NOT_SUPPORTED_BOTH_SURFACES",
        "interpretation_boundary": "A failure parks this fixed VIX-term capital-scaling representation. It does not reject options-derived information generally and does not authorize nearby VIX thresholds or capacity tuning without a new discriminator.",
        "promotion_authority": False,
        "allocation_runtime_authority": False,
        "strategy_spec_mutation": False,
        "broker_action": False,
        "live_trading_change": False,
    }
    OUT.write_text(json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print("OPPORTUNITY_OPTION_IMPLIED_VOL_STATE_ALLOCATOR=" + json.dumps(receipt, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
