from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta, timezone
from urllib.request import Request, urlopen

SYMBOLS = ("DHI", "LEN", "PHM", "NVR", "TOL", "MTH", "KBH", "LGIH", "DFH")
UA = "XoticHaze market-research PIT-panel contact@example.com"
START = date(2019, 1, 1)
END = date(2026, 9, 12)
MAX_STALE_DAYS = 200


def get(url: str) -> dict:
    req = Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urlopen(req, timeout=30) as response:  # noqa: S310 fixed SEC HTTPS host
        return json.loads(response.read().decode("utf-8"))


def month_ends(start: date, end: date) -> list[date]:
    out = []
    cur = date(start.year, start.month, 1)
    while cur <= end:
        nxt = date(cur.year + (cur.month == 12), 1 if cur.month == 12 else cur.month + 1, 1)
        me = min(nxt - timedelta(days=1), end)
        out.append(me)
        cur = nxt
    return out


def fact_rows(us: dict, concept: str) -> list[dict]:
    rows = []
    for unit, vals in us.get(concept, {}).get("units", {}).items():
        if unit != "USD":
            continue
        for row in vals:
            if row.get("form") not in ("10-K", "10-Q"):
                continue
            if not row.get("filed") or not row.get("end") or row.get("val") is None:
                continue
            rows.append(row)
    return rows


def latest_instant(rows: list[dict], asof: date) -> dict | None:
    eligible = []
    for row in rows:
        filed = date.fromisoformat(row["filed"])
        end = date.fromisoformat(row["end"])
        if filed <= asof and end <= asof and (asof - end).days <= MAX_STALE_DAYS:
            eligible.append(row)
    if not eligible:
        return None
    return max(eligible, key=lambda row: (row["end"], row["filed"], row.get("accn") or ""))


def latest_income(rows: list[dict], asof: date) -> dict | None:
    eligible = []
    for row in rows:
        if not row.get("start"):
            continue
        filed = date.fromisoformat(row["filed"])
        start = date.fromisoformat(row["start"])
        end = date.fromisoformat(row["end"])
        span = (end - start).days + 1
        if filed <= asof and end <= asof and 60 <= span <= 400 and (asof - end).days <= MAX_STALE_DAYS:
            eligible.append((row, span))
    if not eligible:
        return None
    # Latest reported period first; for the same end prefer a true quarter, then the
    # shortest available duration. This is deterministic and uses filed-at facts only.
    row, span = max(
        eligible,
        key=lambda item: (
            item[0]["end"],
            1 if 70 <= item[1] <= 110 else 0,
            -item[1],
            item[0]["filed"],
            item[0].get("accn") or "",
        ),
    )
    return {**row, "span_days": span}


def equity_at(us: dict, asof: date, assets: dict | None, liabilities: dict | None) -> tuple[float | None, str | None, str | None]:
    for concept in ("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"):
        row = latest_instant(fact_rows(us, concept), asof)
        if row is not None:
            return float(row["val"]), concept, row["filed"]
    if assets is not None and liabilities is not None:
        return float(assets["val"]) - float(liabilities["val"]), "AssetsMinusLiabilities", max(assets["filed"], liabilities["filed"])
    return None, None, None


def main() -> None:
    ticker_map = get("https://www.sec.gov/files/company_tickers.json")
    cik = {row["ticker"].upper(): str(row["cik_str"]).zfill(10) for row in ticker_map.values()}
    calendar = month_ends(START, END)
    results = {}

    for symbol in SYMBOLS:
        payload = get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik[symbol]}.json")
        us = payload.get("facts", {}).get("us-gaap", {})
        assets_rows = fact_rows(us, "Assets")
        liabilities_rows = fact_rows(us, "Liabilities")
        income_rows = fact_rows(us, "NetIncomeLoss")
        eligible = []
        fallback_counts: dict[str, int] = {}
        for asof in calendar:
            assets = latest_instant(assets_rows, asof)
            liabilities = latest_instant(liabilities_rows, asof)
            equity, equity_source, equity_filed = equity_at(us, asof, assets, liabilities)
            income = latest_income(income_rows, asof)
            if assets is None or income is None or equity is None or equity <= 0 or float(assets["val"]) <= 0:
                continue
            liabilities_value = float(liabilities["val"]) if liabilities is not None else float(assets["val"]) - equity
            if liabilities_value < 0:
                continue
            fallback_counts[equity_source] = fallback_counts.get(equity_source, 0) + 1
            eligible.append(
                {
                    "asof": asof.isoformat(),
                    "assets_end": assets["end"],
                    "assets_filed": assets["filed"],
                    "income_end": income["end"],
                    "income_filed": income["filed"],
                    "income_span_days": income["span_days"],
                    "equity_source": equity_source,
                    "equity_filed": equity_filed,
                }
            )
        results[symbol] = {
            "eligible_months": len(eligible),
            "first_eligible": eligible[0]["asof"] if eligible else None,
            "last_eligible": eligible[-1]["asof"] if eligible else None,
            "equity_source_counts": fallback_counts,
            "sample_first": eligible[:2],
            "sample_last": eligible[-2:],
        }
        time.sleep(0.12)

    dev = SYMBOLS[:-1]
    dev_min = min(results[s]["eligible_months"] for s in dev)
    dfh_months = results["DFH"]["eligible_months"]
    decision = (
        "HOMEBUILDER_SEC_PIT_PANEL_ADMITTED_FOR_ECONOMIC_TEST"
        if dev_min >= 72 and dfh_months >= 48
        else "HOMEBUILDER_SEC_PIT_PANEL_NOT_ADMITTED"
    )
    out = {
        "schema": "public_research.homebuilder_sec_pit_panel_probe_r1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "claim": "Prove filed-at balance-sheet/profitability coverage before any fundamental-return test.",
        "symbols": list(SYMBOLS),
        "max_staleness_days": MAX_STALE_DAYS,
        "deterministic_equity_fallback": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "Assets-Liabilities"],
        "income_rule": "latest filed NetIncomeLoss period; prefer 70-110 day quarter for same end; otherwise shortest 60-400 day duration; no filed-after-asof facts",
        "results": results,
        "gate": {"development_min_eligible_months": 72, "DFH_min_eligible_months": 48},
        "decision": decision,
        "boundaries": {"source_probe_only": True, "economic_results": False, "live_trading_change": False},
    }
    print("HOMEBUILDER_SEC_PIT_PANEL=" + json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
