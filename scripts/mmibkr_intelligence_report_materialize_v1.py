from __future__ import annotations

"""Render deterministic MM-IBKR intelligence receipts into JSON + HTML."""

import argparse
import hashlib
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPORT_SCHEMA = "mmibkr.intelligence_report.v1"
LLM_SCHEMA = "mmibkr.designated_llm_report_enrichment.v1"
PLAN_SCHEMA = "mmibkr.canonical_workload_plan_receipt.v1"
RECEIPT_SCHEMA = "mmibkr.canonical_workload_receipt.v1"
INTELLIGENCE_CAPABILITIES = {"NEWS_REPLAY_ANALYZE", "OPTIONS_SNAPSHOT_ANALYZE"}
FORBIDDEN = (
    "broker_submit","broker_cancel","broker_flatten","strategy_spec_write",
    "runtime_activation","promotion_mutation","live_trading",
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class IntelligenceReportError(RuntimeError):
    pass


def cbytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False, default=str,
    ).encode("utf-8")


def sha(value: Any) -> str:
    return hashlib.sha256(cbytes(value)).hexdigest()


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise IntelligenceReportError(f"invalid JSON: {path.name}") from exc
    if not isinstance(value, dict):
        raise IntelligenceReportError(f"JSON root must be object: {path.name}")
    return value


def utc_iso(value: Any, label: str) -> str:
    try:
        parsed = datetime.fromisoformat(str(value or "").strip().replace("Z", "+00:00"))
    except Exception as exc:
        raise IntelligenceReportError(f"{label} is invalid") from exc
    if parsed.tzinfo is None:
        raise IntelligenceReportError(f"{label} must include timezone")
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def authority(node: Any, label: str) -> dict:
    if not isinstance(node, dict) or node.get("research_only") is not True:
        raise IntelligenceReportError(f"{label} research-only authority rejected")
    for key in FORBIDDEN:
        if node.get(key) is not False:
            raise IntelligenceReportError(f"{label} forbidden authority rejected: {key}")
    return {"research_only": True, **{key: False for key in FORBIDDEN}}


def inside(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def validate_job(receipt: dict, job_id: str, fingerprint: str, expected_sha: str) -> dict:
    if receipt.get("schema") != RECEIPT_SCHEMA or receipt.get("status") != "completed":
        raise IntelligenceReportError(f"job receipt schema/status rejected: {job_id}")
    if receipt.get("job_id") != job_id or receipt.get("job_fingerprint") != fingerprint:
        raise IntelligenceReportError(f"job receipt identity mismatch: {job_id}")
    if sha(receipt) != expected_sha:
        raise IntelligenceReportError(f"job receipt hash mismatch: {job_id}")
    result = receipt.get("result")
    if not isinstance(result, dict):
        raise IntelligenceReportError(f"job result missing: {job_id}")
    expected_result = str(receipt.get("result_sha256") or "")
    if not SHA256_RE.fullmatch(expected_result) or hashlib.sha256(cbytes(result)).hexdigest() != expected_result:
        raise IntelligenceReportError(f"job result hash mismatch: {job_id}")
    authority(receipt.get("authority"), f"job {job_id}")
    return receipt


def load_plan_jobs(receipt_dir: Path, plan_path: Path) -> tuple[dict, list[dict]]:
    plan = load_json(plan_path)
    if plan.get("schema") != PLAN_SCHEMA or plan.get("status") != "completed":
        raise IntelligenceReportError("plan receipt schema/status rejected")
    authority(plan.get("authority"), "plan")
    jobs = plan.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        raise IntelligenceReportError("plan receipt has no jobs")
    root = (receipt_dir.resolve() / "receipts").resolve()
    receipts = []
    for job_id in sorted(jobs):
        state = jobs[job_id]
        if not isinstance(state, dict) or state.get("state") not in {"completed", "cached"}:
            raise IntelligenceReportError(f"plan job not completed/cached: {job_id}")
        fingerprint = str(state.get("job_fingerprint") or "").lower()
        receipt_sha = str(state.get("receipt_sha256") or "").lower()
        if not SHA256_RE.fullmatch(fingerprint) or not SHA256_RE.fullmatch(receipt_sha):
            raise IntelligenceReportError(f"plan job identity invalid: {job_id}")
        path = (root / f"{fingerprint}.json").resolve()
        if not inside(root, path) or not path.is_file():
            raise IntelligenceReportError(f"plan job receipt missing: {job_id}")
        receipts.append(validate_job(load_json(path), job_id, fingerprint, receipt_sha))
    return plan, receipts


def dataset_identity(result: dict) -> dict | None:
    node = result.get("dataset")
    if not isinstance(node, dict):
        return None
    digest = str(node.get("sha256") or "").lower()
    try:
        size = int(node.get("bytes"))
    except Exception:
        return None
    relative = str(node.get("relative_path") or "")
    if not relative or not SHA256_RE.fullmatch(digest) or size < 0:
        return None
    return {"relative_path": relative, "sha256": digest, "bytes": size}


def input_identity(receipt: dict) -> dict:
    result = receipt["result"]
    mm = receipt.get("mmibkr") if isinstance(receipt.get("mmibkr"), dict) else {}
    entry = receipt.get("entrypoint") if isinstance(receipt.get("entrypoint"), dict) else {}
    deps = result.get("canonical_dependencies")
    if not isinstance(deps, dict):
        deps = {}
    clean_deps = {
        str(k): str(v)
        for k, v in deps.items()
        if re.fullmatch(r"^[0-9a-f]{40}$", str(v or ""))
    }
    return {
        "job_id": receipt["job_id"],
        "capability_id": receipt["capability_id"],
        "job_fingerprint": receipt["job_fingerprint"],
        "receipt_sha256": sha(receipt),
        "result_sha256": receipt["result_sha256"],
        "mmibkr": {
            "repository": mm.get("repository"),
            "commit": mm.get("commit"),
            "source_archive_sha256": mm.get("source_archive_sha256"),
        },
        "entrypoint": {
            "path": entry.get("path"),
            "module": entry.get("module"),
            "callable": entry.get("callable"),
            "git_blob_sha1": entry.get("git_blob_sha1"),
        },
        "dataset": dataset_identity(result),
        "canonical_dependencies": clean_deps,
    }


def news_projection(receipt: dict) -> dict:
    result = receipt["result"]
    keys = (
        "symbol","rank","percentile","articles","effective_articles","score",
        "avg_sentiment","avg_impact","avg_confidence","avg_relevance",
        "avg_match_confidence","direct_articles","alias_articles","theme_articles",
        "macro_articles","top_theme","top_sector","summary_source",
    )
    cards = result.get("scorecards")
    if not isinstance(cards, list):
        cards = []
    return {
        "source_type": "deterministic",
        "job_id": receipt["job_id"],
        "matched_item_count": result.get("matched_item_count"),
        "unmatched_item_count": result.get("unmatched_item_count"),
        "scorecard_count": result.get("scorecard_count"),
        "scorecards_sha256": result.get("scorecards_sha256"),
        "articles_sha256": result.get("articles_sha256"),
        "top_unmatched_entities": result.get("top_unmatched_entities") or [],
        "policy": result.get("policy") or {},
        "scorecards": [
            {key: row.get(key) for key in keys if key in row}
            for row in cards[:50] if isinstance(row, dict)
        ],
    }


def options_projection(receipt: dict) -> dict:
    result = receipt["result"]
    keys = (
        "symbol","expiry","expiry_utc","expiry_time_basis","strike","right",
        "analysis_price","price_basis","volume","notional_usd","underlying_price",
        "time_to_expiry_years","moneyness_pct","ib_model_price","ib_iv","ib_delta",
        "ib_gamma","ib_vega","ib_theta","calc_iv","calc_delta","calc_gamma",
        "calc_vega","calc_theta","comparison","status","reason","reasons",
    )
    rows = result.get("row_sample")
    if not isinstance(rows, list):
        rows = []
    summary = result.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    return {
        "source_type": "deterministic",
        "job_id": receipt["job_id"],
        "as_of_utc": result.get("as_of_utc"),
        "risk_free_rate": result.get("risk_free_rate"),
        "snapshot_state": result.get("snapshot_state"),
        "empty_reason": result.get("empty_reason"),
        "analytics_sha256": result.get("analytics_sha256"),
        "policy": result.get("policy") or {},
        "summary": summary,
        "rows": [
            {key: row.get(key) for key in keys if key in row}
            for row in rows[:50] if isinstance(row, dict)
        ],
    }


def deterministic_payload(plan: dict, receipts: list[dict], as_of_utc: str) -> dict:
    intelligence = [r for r in receipts if r.get("capability_id") in INTELLIGENCE_CAPABILITIES]
    if not intelligence:
        raise IntelligenceReportError("plan has no supported intelligence receipts")
    return {
        "as_of_utc": as_of_utc,
        "plan": {
            "plan_id": plan.get("plan_id"),
            "status": plan.get("status"),
            "waves": plan.get("waves") or [],
        },
        "input_identities": [input_identity(r) for r in receipts],
        "news": [news_projection(r) for r in intelligence if r.get("capability_id") == "NEWS_REPLAY_ANALYZE"],
        "options": [options_projection(r) for r in intelligence if r.get("capability_id") == "OPTIONS_SNAPSHOT_ANALYZE"],
        "authority": {"research_only": True, **{key: False for key in FORBIDDEN}},
    }


def llm_enrichment(path: Path | None, deterministic_hash: str) -> dict:
    if path is None:
        return {
            "status": "not_provided",
            "source_type": "designated_llm",
            "deterministic_fields_overridden": False,
        }
    node = load_json(path)
    required = {
        "schema","model_id","prompt_sha256","input_report_sha256",
        "output_sha256","created_at_utc","text",
    }
    if set(node) != required or node.get("schema") != LLM_SCHEMA:
        raise IntelligenceReportError("designated LLM sidecar schema rejected")
    for key in ("prompt_sha256","input_report_sha256","output_sha256"):
        if not SHA256_RE.fullmatch(str(node.get(key) or "").lower()):
            raise IntelligenceReportError(f"designated LLM sidecar {key} invalid")
    if node["input_report_sha256"] != deterministic_hash:
        raise IntelligenceReportError("designated LLM sidecar deterministic input hash mismatch")
    text = str(node.get("text") or "")
    if hashlib.sha256(text.encode("utf-8")).hexdigest() != node["output_sha256"]:
        raise IntelligenceReportError("designated LLM sidecar output hash mismatch")
    model = str(node.get("model_id") or "").strip()
    if not model or len(model) > 160:
        raise IntelligenceReportError("designated LLM model_id invalid")
    return {
        "status": "provided",
        "source_type": "designated_llm",
        "model_id": model,
        "prompt_sha256": node["prompt_sha256"],
        "input_report_sha256": node["input_report_sha256"],
        "output_sha256": node["output_sha256"],
        "created_at_utc": utc_iso(node["created_at_utc"], "designated LLM created_at_utc"),
        "text": text,
        "deterministic_fields_overridden": False,
    }


def build_report(
    receipt_dir: Path,
    plan_receipt_path: Path,
    as_of_utc: str,
    llm_sidecar_path: Path | None = None,
) -> dict:
    as_of = utc_iso(as_of_utc, "report as_of_utc")
    plan, receipts = load_plan_jobs(receipt_dir.resolve(), plan_receipt_path.resolve())
    deterministic = deterministic_payload(plan, receipts, as_of)
    identity = sha(deterministic)
    return {
        "schema": REPORT_SCHEMA,
        "deterministic_identity_sha256": identity,
        "deterministic": deterministic,
        "llm_enrichment": llm_enrichment(
            llm_sidecar_path.resolve() if llm_sidecar_path else None, identity
        ),
        "authority": {"research_only": True, **{key: False for key in FORBIDDEN}},
    }


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def num(value: Any, digits: int = 3) -> str:
    if value in (None, ""):
        return "--"
    try:
        return f"{float(value):,.{digits}f}"
    except Exception:
        return esc(value)


def render_html(report: dict) -> str:
    det = report["deterministic"]
    news_html = []
    for block in det.get("news") or []:
        rows = "".join(
            "<tr>"
            f"<td>{esc(r.get('symbol'))}</td><td>{esc(r.get('rank'))}</td>"
            f"<td>{num(r.get('score'),2)}</td><td>{esc(r.get('articles'))}</td>"
            f"<td>{num(r.get('avg_relevance'))}</td><td>{num(r.get('avg_match_confidence'))}</td>"
            f"<td>{num(r.get('avg_sentiment'),2)}</td><td>{num(r.get('avg_impact'),2)}</td>"
            f"<td>{num(r.get('avg_confidence'))}</td><td>{esc(r.get('summary_source') or 'deterministic')}</td>"
            "</tr>"
            for r in block.get("scorecards") or []
        )
        news_html.append(
            "<section class='card'><div class='eyebrow'>Deterministic News</div>"
            f"<h2>News scorecard · {esc(block.get('job_id'))}</h2>"
            f"<p class='muted'>matched {esc(block.get('matched_item_count'))} · "
            f"unmatched {esc(block.get('unmatched_item_count'))} · scorecards {esc(block.get('scorecard_count'))}</p>"
            "<div class='scroll'><table><thead><tr><th>Symbol</th><th>Rank</th><th>Score</th><th>Articles</th>"
            "<th>Relevance</th><th>Match conf.</th><th>Sentiment</th><th>Impact</th><th>Confidence</th><th>Summary source</th>"
            f"</tr></thead><tbody>{rows}</tbody></table></div></section>"
        )

    options_html = []
    for block in det.get("options") or []:
        rows = "".join(
            "<tr>"
            f"<td>{esc(r.get('symbol'))}</td><td>{esc(r.get('expiry'))}</td><td>{num(r.get('strike'),2)}</td>"
            f"<td>{esc(r.get('right'))}</td><td>{num(r.get('analysis_price'),2)}</td><td>{esc(r.get('volume'))}</td>"
            f"<td>{num(r.get('notional_usd'),2)}</td><td>{num(r.get('calc_iv'),4)}</td>"
            f"<td>{num(r.get('calc_delta'),4)}</td><td>{num(r.get('calc_gamma'),5)}</td>"
            f"<td>{num(r.get('calc_vega'),3)}</td><td>{num(r.get('calc_theta'),3)}</td>"
            f"<td>{esc(r.get('status'))}{(' · ' + esc(r.get('reason'))) if r.get('reason') else ''}</td></tr>"
            for r in block.get("rows") or []
        )
        summary = block.get("summary") or {}
        options_html.append(
            "<section class='card'><div class='eyebrow'>Deterministic Options</div>"
            f"<h2>Options snapshot · {esc(block.get('job_id'))}</h2>"
            f"<p><span class='pill'>{esc(block.get('snapshot_state'))}</span> "
            f"<span class='muted'>as of {esc(block.get('as_of_utc'))} · analyzed {esc(summary.get('analyzed_row_count'))} · "
            f"unavailable {esc(summary.get('unavailable_row_count'))} · notional USD {num(summary.get('total_notional_usd'),2)}</span></p>"
            + (f"<p class='warn'>Empty reason: {esc(block.get('empty_reason'))}</p>" if block.get("empty_reason") else "")
            + "<div class='scroll'><table><thead><tr><th>Symbol</th><th>Expiry</th><th>Strike</th><th>Right</th>"
            "<th>Price</th><th>Volume</th><th>Notional</th><th>Calc IV</th><th>Delta</th><th>Gamma</th><th>Vega</th><th>Theta</th><th>Status</th>"
            f"</tr></thead><tbody>{rows}</tbody></table></div></section>"
        )

    identities = "".join(
        "<tr>"
        f"<td>{esc(n.get('job_id'))}</td><td>{esc(n.get('capability_id'))}</td>"
        f"<td class='mono'>{esc(str(n.get('job_fingerprint') or '')[:16])}…</td>"
        f"<td class='mono'>{esc(str((n.get('mmibkr') or {}).get('commit') or '')[:12])}</td>"
        f"<td>{esc((n.get('dataset') or {}).get('relative_path') or '--')}</td>"
        f"<td class='mono'>{esc(str((n.get('dataset') or {}).get('sha256') or '')[:16])}{'…' if (n.get('dataset') or {}).get('sha256') else ''}</td>"
        "</tr>"
        for n in det.get("input_identities") or []
    )

    llm = report["llm_enrichment"]
    if llm.get("status") == "provided":
        llm_html = (
            f"<p><span class='pill'>designated LLM</span> model {esc(llm.get('model_id'))}</p>"
            f"<p class='muted mono'>prompt {esc(llm.get('prompt_sha256'))}<br>"
            f"bound deterministic input {esc(llm.get('input_report_sha256'))}<br>"
            f"output {esc(llm.get('output_sha256'))}</p><div class='llmtext'>{esc(llm.get('text'))}</div>"
        )
    else:
        llm_html = "<p><span class='pill'>designated LLM</span> Not provided. Deterministic evidence is unmodified.</p>"

    exact = esc(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>MM-IBKR Intelligence Report</title>
<style>:root{{color-scheme:dark}}*{{box-sizing:border-box}}body{{margin:0;background:#0d1117;color:#e6edf3;font:14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif}}
main{{max-width:1240px;margin:auto;padding:28px}}h1{{font-size:28px;margin:4px 0 6px}}h2{{font-size:18px;margin:4px 0 10px}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:16px;margin:14px 0}}.eyebrow{{text-transform:uppercase;letter-spacing:.08em;color:#8b949e;font-size:11px}}
.muted{{color:#8b949e}}.warn{{color:#d29922}}.pill{{display:inline-block;border:1px solid #484f58;border-radius:999px;padding:2px 8px}}
.scroll{{overflow:auto}}table{{border-collapse:collapse;width:100%;min-width:820px}}th,td{{border-bottom:1px solid #30363d;text-align:left;padding:7px 8px;white-space:nowrap}}
th{{color:#8b949e;font-weight:600}}.mono{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}}pre{{white-space:pre-wrap;word-break:break-word;max-height:520px;overflow:auto}}
.llmtext{{white-space:pre-wrap}}</style></head><body><main>
<div class="eyebrow">MM-IBKR · research-only intelligence</div><h1>Canonical Intelligence Report</h1>
<p class="muted">Plan {esc((det.get('plan') or {}).get('plan_id'))} · as of {esc(det.get('as_of_utc'))}</p>
<section class="card"><strong>Authority boundary</strong><p>Research evidence only. Broker actions, StrategySpec writes, runtime activation, promotion mutation, and live trading are disabled.</p></section>
{''.join(news_html) if news_html else "<section class='card'><h2>News</h2><p class='muted'>No News intelligence receipt in this plan.</p></section>"}
{''.join(options_html) if options_html else "<section class='card'><h2>Options</h2><p class='muted'>No Options intelligence receipt in this plan.</p></section>"}
<section class="card"><div class="eyebrow">Exact provenance</div><h2>Input identities</h2><div class="scroll"><table><thead>
<tr><th>Job</th><th>Capability</th><th>Fingerprint</th><th>MM source</th><th>Dataset</th><th>Dataset SHA-256</th></tr>
</thead><tbody>{identities}</tbody></table></div><p class="muted mono">deterministic report identity: {esc(report.get('deterministic_identity_sha256'))}</p></section>
<section class="card"><div class="eyebrow">Separate enrichment plane</div><h2>Designated LLM enrichment</h2>{llm_html}</section>
<section class="card"><details><summary>Exact report payload</summary><pre class="mono">{exact}</pre></details></section>
</main></body></html>"""


def materialize(
    receipt_dir: Path,
    plan_receipt_path: Path,
    out_dir: Path,
    as_of_utc: str,
    llm_sidecar_path: Path | None = None,
) -> dict:
    report = build_report(receipt_dir, plan_receipt_path, as_of_utc, llm_sidecar_path)
    out = out_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "intelligence_report.json"
    html_path = out / "intelligence_report.html"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    html_path.write_text(render_html(report), encoding="utf-8")
    return {
        "schema": "mmibkr.intelligence_report_materialization.v1",
        "status": "PASS",
        "deterministic_identity_sha256": report["deterministic_identity_sha256"],
        "llm_status": report["llm_enrichment"]["status"],
        "artifacts": [
            {"name": json_path.name, "sha256": sha_file(json_path), "bytes": json_path.stat().st_size},
            {"name": html_path.name, "sha256": sha_file(html_path), "bytes": html_path.stat().st_size},
        ],
        "authority": {"research_only": True, **{key: False for key in FORBIDDEN}},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt-dir", required=True)
    parser.add_argument("--plan-receipt", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--as-of-utc", required=True)
    parser.add_argument("--llm-sidecar")
    args = parser.parse_args()
    try:
        receipt = materialize(
            Path(args.receipt_dir), Path(args.plan_receipt), Path(args.out_dir),
            args.as_of_utc, Path(args.llm_sidecar) if args.llm_sidecar else None,
        )
    except IntelligenceReportError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
