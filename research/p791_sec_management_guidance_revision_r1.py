from __future__ import annotations

import bisect
import html
import json
import math
import re
import statistics
import time
import urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path

EXPERIMENT = "SEC_MANAGEMENT_GUIDANCE_REVISION_R1_20260915"
START = "2014-01-01"
RECENT = "2022-01-01"
HOLD = 63
COST = 0.005
MIN_RAISE = 50
MIN_LOWER = 50
BREADTH_GATE = 0.53
CONCENTRATION_GATE = 0.35
SPY = "SPY"
UA = "XoticHaze market-research causal-event-study contact@example.com"

TICKER_TO_SECTOR = {
    "AAPL": "XLK", "MSFT": "XLK", "NVDA": "SMH", "AMD": "SMH", "AMAT": "SMH", "AVGO": "SMH",
    "JPM": "XLF", "BAC": "XLF", "GS": "XLF", "XOM": "XLE", "CVX": "XLE", "COP": "XLE",
    "CAT": "XLI", "HON": "XLI", "GE": "XLI", "JNJ": "XLV", "LLY": "XLV", "UNH": "XLV",
    "PG": "XLP", "KO": "XLP", "PEP": "XLP", "HD": "XLY", "MCD": "XLY", "NKE": "XLY",
    "TSLA": "XLY", "META": "XLC", "GOOGL": "XLC", "NFLX": "XLC", "NEE": "XLU", "DUK": "XLU",
    "LIN": "XLB", "FCX": "XLB", "PLD": "XLRE", "AMT": "XLRE",
}

GUIDANCE_TERMS = r"(?:guidance|outlook|forecast)"
RAISE_ACTIONS = r"(?:raise(?:d|s|ing)?|increase(?:d|s|ing)?|boost(?:ed|s|ing)?)"
LOWER_ACTIONS = r"(?:lower(?:ed|s|ing)?|reduce(?:d|s|ing)?|cut(?:s|ting)?)"
# Deliberately narrow: action and forward-looking noun must be close in the same normalized text window.
RAISE_PATTERNS = [
    re.compile(rf"\b{RAISE_ACTIONS}\b.{{0,100}}\b{GUIDANCE_TERMS}\b", re.I),
    re.compile(rf"\b{GUIDANCE_TERMS}\b.{{0,100}}\b(?:is|was|has been|have been|now)?\s*{RAISE_ACTIONS}\b", re.I),
]
LOWER_PATTERNS = [
    re.compile(rf"\b{LOWER_ACTIONS}\b.{{0,100}}\b{GUIDANCE_TERMS}\b", re.I),
    re.compile(rf"\b{GUIDANCE_TERMS}\b.{{0,100}}\b(?:is|was|has been|have been|now)?\s*{LOWER_ACTIONS}\b", re.I),
]


def get_bytes(url: str, *, sec: bool = False, attempts: int = 6) -> bytes:
    headers = {
        "User-Agent": UA if sec else "Mozilla/5.0 XoticHaze-research/1.0",
        "Accept": "application/json,text/html,text/plain,*/*",
    }
    for n in range(attempts):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
                return response.read()
        except Exception:
            if n == attempts - 1:
                raise
            time.sleep(min(12.0, 0.8 * (2 ** n)))
    raise RuntimeError("unreachable")


def get_json(url: str, *, sec: bool = False):
    return json.loads(get_bytes(url, sec=sec).decode("utf-8"))


def prices(symbol: str):
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{symbol}?period1=1388534400&period2=1798761600&interval=1d&events=div%2Csplits&includeAdjustedClose=true"
    )
    node = get_json(url)["chart"]["result"][0]
    quote = node["indicators"]["quote"][0]
    adj = node["indicators"]["adjclose"][0]["adjclose"]
    rows = []
    for ts, op, cl, ac in zip(node["timestamp"], quote["open"], quote["close"], adj):
        if op is None or cl in (None, 0) or ac is None:
            continue
        ratio = float(ac) / float(cl)
        rows.append((date.fromtimestamp(ts).isoformat(), float(op) * ratio, float(ac)))
    return rows


def filing_records(cik10: str):
    root = get_json(f"https://data.sec.gov/submissions/CIK{cik10}.json", sec=True)
    parts = [root.get("filings", {}).get("recent", {})]
    for meta in root.get("filings", {}).get("files", []):
        try:
            parts.append(get_json("https://data.sec.gov/submissions/" + meta["name"], sec=True))
            time.sleep(0.11)
        except Exception:
            pass
    found = {}
    for part in parts:
        forms = part.get("form", [])
        for i, form in enumerate(forms):
            if form != "8-K":
                continue
            def value(key):
                values = part.get(key, [])
                return values[i] if i < len(values) else None
            filed = value("filingDate")
            items = value("items") or ""
            accession = value("accessionNumber")
            primary = value("primaryDocument")
            if (
                filed and filed >= START and accession and
                any(item in items for item in ("2.02", "7.01", "8.01"))
            ):
                found.setdefault(
                    accession,
                    {
                        "filing_date": filed,
                        "acceptance_datetime": value("acceptanceDateTime"),
                        "items": items,
                        "accession": accession,
                        "primary_document": primary,
                    },
                )
    return sorted(found.values(), key=lambda x: (x["filing_date"], x["accession"])), len(parts)


def normalize_document(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="ignore")
    text = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def filing_document_names(cik10: str, accession: str, primary: str | None):
    cik = str(int(cik10))
    acc = accession.replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}"
    index = get_json(base + "/index.json", sec=True)
    names = []
    if primary:
        names.append(primary)
    for item in index.get("directory", {}).get("item", []):
        name = str(item.get("name") or "")
        low = name.lower()
        if not low.endswith((".htm", ".html", ".txt")):
            continue
        if low.endswith(("-index.html", "-index.htm")):
            continue
        size = int(item.get("size") or 0)
        if size and size > 2_500_000:
            continue
        if name not in names:
            names.append(name)
    # Primary + likely earnings exhibits first, then bounded fallback docs.
    names.sort(key=lambda n: (0 if n == primary else 1 if re.search(r"(?:ex|exhibit)?99|earn|release", n, re.I) else 2, n))
    return base, names[:6]


def classify_guidance(cik10: str, event: dict):
    base, names = filing_document_names(cik10, event["accession"], event.get("primary_document"))
    raise_hits = []
    lower_hits = []
    scanned = []
    for name in names:
        try:
            text = normalize_document(get_bytes(base + "/" + name, sec=True))
            time.sleep(0.11)
        except Exception:
            continue
        scanned.append(name)
        for label, patterns, sink in (
            ("RAISE", RAISE_PATTERNS, raise_hits),
            ("LOWER", LOWER_PATTERNS, lower_hits),
        ):
            for pattern in patterns:
                for match in pattern.finditer(text):
                    lo = max(0, match.start() - 80)
                    hi = min(len(text), match.end() + 80)
                    sink.append({"document": name, "snippet": text[lo:hi][:360], "pattern": label})
                    if len(sink) >= 3:
                        break
                if len(sink) >= 3:
                    break
    direction = None
    if raise_hits and not lower_hits:
        direction = "RAISE"
    elif lower_hits and not raise_hits:
        direction = "LOWER"
    return {
        "direction": direction,
        "raise_hit_count": len(raise_hits),
        "lower_hit_count": len(lower_hits),
        "raise_hits": raise_hits[:3],
        "lower_hits": lower_hits[:3],
        "documents_scanned": scanned,
    }


def event_return(rows, sector_map, spy_map, event):
    dates = [row[0] for row in rows]
    entry_index = bisect.bisect_right(dates, event["filing_date"])
    exit_index = entry_index + HOLD - 1
    if entry_index >= len(rows) or exit_index >= len(rows):
        return None
    entry = rows[entry_index]
    exit_row = rows[exit_index]
    if entry[0] not in sector_map or exit_row[0] not in sector_map or entry[0] not in spy_map or exit_row[0] not in spy_map:
        return None
    se, sx = sector_map[entry[0]], sector_map[exit_row[0]]
    be, bx = spy_map[entry[0]], spy_map[exit_row[0]]
    candidate = exit_row[2] / entry[1] - 1.0 - COST
    return {
        "entry_date": entry[0],
        "exit_date": exit_row[0],
        "candidate_return_after_cost": candidate,
        "sector_return": sx[2] / se[1] - 1.0,
        "spy_return": bx[2] / be[1] - 1.0,
        "sector_excess": candidate - (sx[2] / se[1] - 1.0),
        "spy_excess": candidate - (bx[2] / be[1] - 1.0),
    }


def mean(values):
    return statistics.fmean(values) if values else None


def median(values):
    return statistics.median(values) if values else None


def chronology_folds(events, k=5):
    rows = sorted(events, key=lambda x: (x["filing_date"], x["ticker"], x["accession"]))
    out = []
    n = len(rows)
    for j in range(k):
        part = rows[math.floor(j * n / k): math.floor((j + 1) * n / k)]
        excess = [x["sector_excess"] for x in part]
        out.append(
            {
                "fold": j + 1,
                "n": len(part),
                "start": part[0]["filing_date"] if part else None,
                "end": part[-1]["filing_date"] if part else None,
                "mean_sector_excess": mean(excess),
                "positive": bool(excess and mean(excess) > 0),
            }
        )
    return out


def concentration(events, key):
    buckets = defaultdict(float)
    total = 0.0
    for event in events:
        value = max(0.0, event["sector_excess"])
        buckets[event[key]] += value
        total += value
    if total <= 0:
        return 1.0, None
    winner = max(buckets, key=buckets.get)
    return buckets[winner] / total, winner


def cohort_summary(events):
    sx = [x["sector_excess"] for x in events]
    bx = [x["spy_excess"] for x in events]
    recent = [x["sector_excess"] for x in events if x["filing_date"] >= RECENT]
    folds = chronology_folds(events)
    ticker_share, ticker = concentration(events, "ticker")
    year_share, year = concentration(events, "year")
    return {
        "n": len(events),
        "mean_after_cost_sector_excess": mean(sx),
        "median_after_cost_sector_excess": median(sx),
        "mean_after_cost_spy_excess": mean(bx),
        "positive_sector_excess_share": mean([x > 0 for x in sx]) if sx else None,
        "recent_2022_plus_sector_excess": mean(recent),
        "chronology_folds": folds,
        "positive_chronology_folds": sum(x["positive"] for x in folds),
        "max_single_ticker_positive_excess_share": ticker_share,
        "max_single_ticker": ticker,
        "max_single_year_positive_excess_share": year_share,
        "max_single_year": year,
    }


def main():
    company_map = get_json("https://www.sec.gov/files/company_tickers.json", sec=True)
    cik = {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in company_map.values()}
    symbols = sorted(set(TICKER_TO_SECTOR) | set(TICKER_TO_SECTOR.values()) | {SPY})
    px = {}
    for symbol in symbols:
        px[symbol] = prices(symbol)
        time.sleep(0.05)
    price_maps = {s: {d: (d, o, c) for d, o, c in rows} for s, rows in px.items()}

    events = []
    coverage = []
    for ticker, sector in TICKER_TO_SECTOR.items():
        try:
            filings, parts = filing_records(cik[ticker])
        except Exception as exc:
            coverage.append({"ticker": ticker, "status": "SEC_SUBMISSIONS_ERROR", "error": type(exc).__name__})
            continue
        classified = 0
        raises = 0
        lowers = 0
        ambiguous = 0
        for filing in filings:
            try:
                cls = classify_guidance(cik[ticker], filing)
                time.sleep(0.11)
            except Exception:
                continue
            if cls["raise_hit_count"] and cls["lower_hit_count"]:
                ambiguous += 1
            if cls["direction"] is None:
                continue
            ret = event_return(px[ticker], price_maps[sector], price_maps[SPY], filing)
            if ret is None:
                continue
            row = dict(filing)
            row.update(ret)
            row.update(cls)
            row.update({"ticker": ticker, "sector": sector, "year": filing["filing_date"][:4]})
            events.append(row)
            classified += 1
            raises += int(cls["direction"] == "RAISE")
            lowers += int(cls["direction"] == "LOWER")
        coverage.append(
            {
                "ticker": ticker,
                "status": "OK",
                "filing_parts": parts,
                "candidate_8k_filings": len(filings),
                "classified_events": classified,
                "raise_events": raises,
                "lower_events": lowers,
                "ambiguous_mixed_filings": ambiguous,
            }
        )

    raised = [x for x in events if x["direction"] == "RAISE"]
    lowered = [x for x in events if x["direction"] == "LOWER"]
    raise_summary = cohort_summary(raised)
    lower_summary = cohort_summary(lowered)
    spread = (
        raise_summary["mean_after_cost_sector_excess"] - lower_summary["mean_after_cost_sector_excess"]
        if raised and lowered else None
    )
    gates = {
        "raise_events_at_least_50": len(raised) >= MIN_RAISE,
        "lower_events_at_least_50": len(lowered) >= MIN_LOWER,
        "raise_mean_sector_excess_positive": bool(raised and raise_summary["mean_after_cost_sector_excess"] > 0),
        "raise_median_sector_excess_positive": bool(raised and raise_summary["median_after_cost_sector_excess"] > 0),
        "raise_minus_lower_sector_excess_positive": bool(spread is not None and spread > 0),
        "raise_positive_sector_excess_share_at_least_53pct": bool(raised and raise_summary["positive_sector_excess_share"] >= BREADTH_GATE),
        "raise_chronology_folds_at_least_3_of_5_positive": raise_summary["positive_chronology_folds"] >= 3,
        "raise_recent_2022_plus_sector_excess_positive": bool(raise_summary["recent_2022_plus_sector_excess"] is not None and raise_summary["recent_2022_plus_sector_excess"] > 0),
        "raise_single_ticker_positive_contribution_share_le_35pct": raise_summary["max_single_ticker_positive_excess_share"] <= CONCENTRATION_GATE,
        "raise_single_year_positive_contribution_share_le_35pct": raise_summary["max_single_year_positive_excess_share"] <= CONCENTRATION_GATE,
    }
    adequate = gates["raise_events_at_least_50"] and gates["lower_events_at_least_50"]
    if not adequate:
        decision = "INCONCLUSIVE_SAMPLE"
    elif all(gates.values()):
        decision = "GUIDANCE_REVISION_MECHANISM_SUPPORTED_R1"
    else:
        decision = "REJECT_EXACT_R1_NO_PARAMETER_RESCUE"

    result = {
        "decision": decision,
        "eligible_classified_events": len(events),
        "raise": raise_summary,
        "lower": lower_summary,
        "raise_minus_lower_mean_sector_excess": spread,
        "gates": gates,
    }
    output = {
        "schema": "public_research.sec_management_guidance_revision_r1",
        "experiment_id": EXPERIMENT,
        "inherited_learning_ids": ["SLP-20260913-SEC-8K-EARNINGS-REACTION-DRIFT-R1"],
        "frozen_specification": {
            "start_date": START,
            "recent_start": RECENT,
            "event_source": "SEC submissions 8-K items 2.02/7.01/8.01 plus filing/exhibit text",
            "classifier": "explicit raise/increase/boost vs lower/reduce/cut within 100 normalized characters of guidance/outlook/forecast; mixed filings excluded",
            "information_time": "SEC filing acceptance/public filing; no market reaction feature",
            "earliest_trade_at": "next full trading-session open strictly after filingDate",
            "holding_sessions": HOLD,
            "round_trip_cost": COST,
            "matched_controls": ["sector ETF", "SPY", "LOWER guidance cohort"],
            "panel": "same fixed current liquid multi-sector mechanism-screen panel as prior SEC event study",
            "chronology_folds": 5,
            "minimum_raise_events": MIN_RAISE,
            "minimum_lower_events": MIN_LOWER,
            "breadth_gate": BREADTH_GATE,
            "max_ticker_year_concentration": CONCENTRATION_GATE,
            "parameter_search": False,
            "post_result_lexicon_search": False,
            "post_result_horizon_search": False,
        },
        "result": result,
        "source_coverage": coverage,
        "events": events,
        "limitations": [
            "fixed current liquid panel is a mechanism screen, not a point-in-time investable-universe claim",
            "deterministic phrase classifier intentionally sacrifices recall for auditability",
            "filingDate rather than intraday acceptance timestamp is used for the conservative next-full-session entry rule",
            "failure forbids lexicon/horizon/date/ticker/sector/cost/control rescue",
        ],
        "boundaries": {
            "portfolio_allocation": False,
            "strategy_spec_mutation": False,
            "runtime": False,
            "broker": False,
            "live_trading": False,
        },
    }
    path = Path("research/results/p791_sec_management_guidance_revision_r1.json")
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(output, indent=2, sort_keys=True, allow_nan=False))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
