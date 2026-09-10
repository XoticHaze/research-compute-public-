from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DATASET = "gpe5-46if"
BASE = f"https://publicreporting.cftc.gov/resource/{DATASET}.json"
CONTRACTS = {
    "ES": {"code": "13874A", "name_hint": "S&P 500"},
    "NQ": {"code": "209742", "name_hint": "NASDAQ-100"},
}
REQUIRED = {
    "report_date_as_yyyy_mm_dd",
    "cftc_contract_market_code",
    "open_interest_all",
    "asset_mgr_positions_long",
    "asset_mgr_positions_short",
    "lev_money_positions_long",
    "lev_money_positions_short",
}


def fetch_rows(code: str) -> list[dict]:
    query = urlencode({
        "$where": f"cftc_contract_market_code='{code}'",
        "$order": "report_date_as_yyyy_mm_dd DESC",
        "$limit": "12",
    })
    req = Request(BASE + "?" + query, headers={"User-Agent": "XoticHaze-Research/1.0"})
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    tests = {}
    admitted = True
    for symbol, spec in CONTRACTS.items():
        try:
            rows = fetch_rows(spec["code"])
        except Exception as exc:
            tests[symbol] = {"source_ok": False, "error": f"{type(exc).__name__}: {exc}"}
            admitted = False
            continue
        keys = sorted({k for row in rows for k in row})
        required_present = REQUIRED.issubset(set(keys))
        code_match = bool(rows) and all(row.get("cftc_contract_market_code") == spec["code"] for row in rows)
        names = sorted({row.get("contract_market_name") or row.get("market_and_exchange_names") for row in rows if row.get("contract_market_name") or row.get("market_and_exchange_names")})
        dates = [row.get("report_date_as_yyyy_mm_dd") for row in rows if row.get("report_date_as_yyyy_mm_dd")]
        numeric_ok = bool(rows)
        for row in rows:
            for field in REQUIRED - {"report_date_as_yyyy_mm_dd", "cftc_contract_market_code"}:
                try:
                    float(row[field])
                except Exception:
                    numeric_ok = False
        source_ok = bool(rows) and required_present and code_match and numeric_ok
        admitted = admitted and source_ok
        tests[symbol] = {
            "source_ok": source_ok,
            "contract_code": spec["code"],
            "rows": len(rows),
            "latest_report_date": max(dates) if dates else None,
            "oldest_sample_report_date": min(dates) if dates else None,
            "required_fields_present": required_present,
            "numeric_position_fields": numeric_ok,
            "market_names": names,
            "available_fields": keys,
            "sample": rows[:2],
        }
    out = {
        "schema": "research.p281_cftc_tff_source_probe_r1",
        "parent": "P281",
        "claim": "CFTC Traders in Financial Futures positions for ES and NQ are a public, weekly, independently published positioning-state source suitable for a causal macro/regime alpha discriminator if the source contract passes.",
        "contract": {
            "dataset": DATASET,
            "endpoint": BASE,
            "contracts": CONTRACTS,
            "required_fields": sorted(REQUIRED),
            "causality_policy": "Treat each Tuesday report as unavailable until the following Friday publication. Economic tests must lag the COT observation to the first market session after publication; never use report_date as same-day known information.",
            "no_price_or_alpha_inference_in_source_probe": True,
        },
        "tests": tests,
        "decision": "P281_CFTC_TFF_SOURCE_ADMITTED" if admitted else "P281_CFTC_TFF_SOURCE_NOT_ADMITTED",
        "next_if_admitted": "Run one fixed ES/NQ positioning-state economic discriminator with publication lag, matched SPY/QQQ controls, walk-forward chronology, costs, and a permuted-positioning negative control before considering any industry allocation use.",
        "limitations": ["Source admission is not alpha evidence", "COT is weekly and published after the Tuesday observation", "TFF positioning is a macro/regime input, not ticker-level causality"],
        "boundaries": {"portfolio_ranking": False, "allocation_authority": False, "runtime": False, "broker": False, "live_trading": False},
    }
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p281_cftc_tff_source_probe_r1.json").write_text(json.dumps(out, indent=2, sort_keys=True))
    print(json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
