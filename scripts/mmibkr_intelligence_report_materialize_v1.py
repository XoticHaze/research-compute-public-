from __future__ import annotations

"""Materialize human-readable MM-IBKR intelligence reports from canonical public receipts.

This is a sanitized public-receipt consumer. It does not load private MM source,
acquire provider data, execute strategies, mutate runtime/promotion state, or carry
broker/live authority.
"""

import argparse
import hashlib
import html
import json
import re
from pathlib import Path
from typing import Any

PLAN_SCHEMA = "mmibkr.canonical_workload_plan_receipt.v1"
JOB_SCHEMA = "mmibkr.canonical_workload_receipt.v1"
REPORT_SCHEMA = "mmibkr.intelligence_report.v1"
MATERIALIZATION_SCHEMA = "mmibkr.intelligence_report_materialization.v1"
LLM_SCHEMA = "mmibkr.intelligence_report_llm_sidecar.v1"

SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
FORBIDDEN_AUTHORITY_KEYS = (
    "broker_submit",
    "broker_cancel",
    "broker_flatten",
    "strategy_spec_write",
    "runtime_activation",
    "promotion_mutation",
    "live_trading",
)
EXPECTED_AUTHORITY = {"research_only": True, **{key: False for key in FORBIDDEN_AUTHORITY_KEYS}}
SUPPORTED_REPORT_CAPABILITIES = {"NEWS_REPLAY_ANALYZE", "OPTIONS_SNAPSHOT_ANALYZE"}


class IntelligenceReportError(RuntimeError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def json_file_bytes(value: Any) -> bytes:
    return canonical_bytes(value) + b"\n"


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise IntelligenceReportError(f"{label} is not valid JSON") from exc


def exact_fields(node: dict, expected: set[str], label: str) -> None:
    if set(node) != expected:
        raise IntelligenceReportError(
            f"{label} field set mismatch expected={sorted(expected)} actual={sorted(node)}"
        )


def require_inside(root: Path, path: Path, label: str) -> Path:
    root = root.resolve()
    path = path.resolve()
    try:
        path.relative_to(root)
    except Exception as exc:
        raise IntelligenceReportError(f"{label} is outside governed root") from exc
    return path


def validate_authority(node: Any, label: str) -> None:
    if node != EXPECTED_AUTHORITY:
        raise IntelligenceReportError(f"{label} authority drift")


def validate_descriptor(node: Any, label: str) -> dict:
    if not isinstance(node, dict):
        raise IntelligenceReportError(f"{label} descriptor must be object")
    exact_fields(node, {"relative_path", "sha256", "bytes"}, label)
    rel = Path(str(node.get("relative_path") or ""))
    if rel.is_absolute() or not rel.parts or ".." in rel.parts:
        raise IntelligenceReportError(f"{label} relative_path rejected")
    digest = str(node.get("sha256") or "").lower()
    if not SHA256_RE.fullmatch(digest):
        raise IntelligenceReportError(f"{label} sha256 rejected")
    try:
        size = int(node.get("bytes"))
    except Exception as exc:
        raise IntelligenceReportError(f"{label} bytes rejected") from exc
    if size < 0:
        raise IntelligenceReportError(f"{label} bytes rejected")
    return {"relative_path": rel.as_posix(), "sha256": digest, "bytes": size}


def verify_artifact(
    receipt_dir: Path,
    job_fingerprint: str,
    descriptor: Any,
    label: str,
) -> tuple[dict, Path]:
    desc = validate_descriptor(descriptor, label)
    root = (receipt_dir / "artifacts" / job_fingerprint).resolve()
    path = require_inside(root, root / desc["relative_path"], label)
    if not path.is_file():
        raise IntelligenceReportError(f"{label} artifact missing")
    if path.stat().st_size != desc["bytes"]:
        raise IntelligenceReportError(f"{label} artifact byte count mismatch")
    if file_sha256(path) != desc["sha256"]:
        raise IntelligenceReportError(f"{label} artifact sha256 mismatch")
    return desc, path


def validate_mmibkr(node: Any, label: str) -> dict:
    if not isinstance(node, dict):
        raise IntelligenceReportError(f"{label} mmibkr must be object")
    exact_fields(node, {"repository", "commit", "source_archive_sha256"}, f"{label} mmibkr")
    repository = str(node.get("repository") or "")
    commit = str(node.get("commit") or "").lower()
    archive = str(node.get("source_archive_sha256") or "").lower()
    if repository != "XoticHaze/mm-IBKR":
        raise IntelligenceReportError(f"{label} private source repository drift")
    if not SHA1_RE.fullmatch(commit):
        raise IntelligenceReportError(f"{label} private source commit rejected")
    if not SHA256_RE.fullmatch(archive):
        raise IntelligenceReportError(f"{label} private source archive rejected")
    return {"repository": repository, "commit": commit, "source_archive_sha256": archive}


def validate_dependencies(node: Any, label: str) -> dict:
    if node is None:
        return {}
    if not isinstance(node, dict) or len(node) > 256:
        raise IntelligenceReportError(f"{label} canonical_dependencies rejected")
    out = {}
    for raw_path, raw_sha in sorted(node.items()):
        path = str(raw_path or "").strip()
        digest = str(raw_sha or "").lower()
        if not path or Path(path).is_absolute() or ".." in Path(path).parts:
            raise IntelligenceReportError(f"{label} dependency path rejected")
        if not SHA1_RE.fullmatch(digest):
            raise IntelligenceReportError(f"{label} dependency blob rejected")
        out[path] = digest
    return out


def validate_dataset(node: Any, label: str) -> dict | None:
    if node is None:
        return None
    return validate_descriptor(node, f"{label} dataset")


def validate_result_authority(result: dict, label: str) -> None:
    safety = result.get("safety")
    if not isinstance(safety, dict) or safety.get("research_only") is not True:
        raise IntelligenceReportError(f"{label} research-only safety drift")
    for key in FORBIDDEN_AUTHORITY_KEYS:
        if safety.get(key) is not False:
            raise IntelligenceReportError(f"{label} safety drift: {key}")


def validate_plan_receipt(plan: Any) -> dict:
    if not isinstance(plan, dict):
        raise IntelligenceReportError("plan receipt must be object")
    exact_fields(
        plan,
        {"schema", "plan_id", "status", "max_parallel", "waves", "jobs", "authority"},
        "plan receipt",
    )
    if plan.get("schema") != PLAN_SCHEMA:
        raise IntelligenceReportError("unsupported plan receipt schema")
    plan_id = str(plan.get("plan_id") or "")
    if not ID_RE.fullmatch(plan_id):
        raise IntelligenceReportError("plan_id rejected")
    if plan.get("status") != "completed":
        raise IntelligenceReportError("plan receipt must be completed")
    validate_authority(plan.get("authority"), "plan receipt")
    jobs = plan.get("jobs")
    if not isinstance(jobs, dict) or not jobs or len(jobs) > 256:
        raise IntelligenceReportError("plan receipt jobs rejected")
    normalized_jobs = {}
    for job_id, state in sorted(jobs.items()):
        if not ID_RE.fullmatch(str(job_id)):
            raise IntelligenceReportError("plan job_id rejected")
        if not isinstance(state, dict):
            raise IntelligenceReportError(f"plan state rejected: {job_id}")
        exact_fields(
            state,
            {"state", "cache_hit", "job_fingerprint", "receipt_sha256"},
            f"plan job state {job_id}",
        )
        if state.get("state") not in {"completed", "cached"}:
            raise IntelligenceReportError(f"plan job not completed: {job_id}")
        fp = str(state.get("job_fingerprint") or "").lower()
        receipt_sha = str(state.get("receipt_sha256") or "").lower()
        if not SHA256_RE.fullmatch(fp) or not SHA256_RE.fullmatch(receipt_sha):
            raise IntelligenceReportError(f"plan job digest rejected: {job_id}")
        normalized_jobs[str(job_id)] = {
            "state": state["state"],
            "cache_hit": bool(state.get("cache_hit")),
            "job_fingerprint": fp,
            "receipt_sha256": receipt_sha,
        }
    return {
        "schema": PLAN_SCHEMA,
        "plan_id": plan_id,
        "status": "completed",
        "max_parallel": int(plan.get("max_parallel") or 0),
        "waves": plan.get("waves"),
        "jobs": normalized_jobs,
        "authority": dict(EXPECTED_AUTHORITY),
    }


def load_job_receipt(
    receipt_dir: Path,
    job_id: str,
    state: dict,
) -> tuple[dict, dict]:
    fp = state["job_fingerprint"]
    path = require_inside(
        receipt_dir / "receipts",
        receipt_dir / "receipts" / f"{fp}.json",
        f"job receipt {job_id}",
    )
    if not path.is_file():
        raise IntelligenceReportError(f"job receipt missing: {job_id}")
    receipt = load_json(path, f"job receipt {job_id}")
    if not isinstance(receipt, dict):
        raise IntelligenceReportError(f"job receipt must be object: {job_id}")
    exact_fields(
        receipt,
        {
            "schema",
            "job_id",
            "job_fingerprint",
            "capability_id",
            "status",
            "authority",
            "mmibkr",
            "entrypoint",
            "resources",
            "result_sha256",
            "result",
        },
        f"job receipt {job_id}",
    )
    if receipt.get("schema") != JOB_SCHEMA or receipt.get("status") != "completed":
        raise IntelligenceReportError(f"job receipt schema/status rejected: {job_id}")
    if receipt.get("job_id") != job_id or receipt.get("job_fingerprint") != fp:
        raise IntelligenceReportError(f"job receipt identity mismatch: {job_id}")
    if canonical_sha256(receipt) != state["receipt_sha256"]:
        raise IntelligenceReportError(f"job receipt canonical hash mismatch: {job_id}")
    validate_authority(receipt.get("authority"), f"job receipt {job_id}")
    mmibkr = validate_mmibkr(receipt.get("mmibkr"), f"job receipt {job_id}")
    result = receipt.get("result")
    if not isinstance(result, dict):
        raise IntelligenceReportError(f"job result rejected: {job_id}")
    result_sha = str(receipt.get("result_sha256") or "").lower()
    if not SHA256_RE.fullmatch(result_sha) or canonical_sha256(result) != result_sha:
        raise IntelligenceReportError(f"job result hash mismatch: {job_id}")
    capability = str(receipt.get("capability_id") or "")
    return receipt, {
        "job_id": job_id,
        "job_fingerprint": fp,
        "receipt_sha256": state["receipt_sha256"],
        "receipt_file_sha256": file_sha256(path),
        "capability_id": capability,
        "mmibkr": mmibkr,
        "result_sha256": result_sha,
        "dataset": validate_dataset(result.get("dataset"), f"job {job_id}"),
        "canonical_dependencies": validate_dependencies(
            result.get("canonical_dependencies"), f"job {job_id}"
        ),
    }


def verify_job_artifacts(receipt_dir: Path, receipt: dict) -> dict[str, tuple[dict, Path]]:
    result = receipt["result"]
    artifacts = result.get("artifacts") or []
    if not isinstance(artifacts, list) or len(artifacts) > 4096:
        raise IntelligenceReportError("job artifacts rejected")
    out: dict[str, tuple[dict, Path]] = {}
    for index, node in enumerate(artifacts):
        desc, path = verify_artifact(
            receipt_dir,
            receipt["job_fingerprint"],
            node,
            f"{receipt['job_id']} artifact[{index}]",
        )
        if desc["relative_path"] in out:
            raise IntelligenceReportError("duplicate artifact relative_path")
        out[desc["relative_path"]] = (desc, path)
    return out


def news_section(receipt_dir: Path, receipt: dict) -> dict:
    result = receipt["result"]
    if result.get("schema") != "mmibkr.news_replay_analysis.v1":
        raise IntelligenceReportError("News result schema rejected")
    validate_result_authority(result, "News result")
    policy = result.get("policy")
    if (
        not isinstance(policy, dict)
        or policy.get("deterministic_only") is not True
        or policy.get("provider_or_rss_acquisition") is not False
        or policy.get("llm_enrichment") is not False
    ):
        raise IntelligenceReportError("News deterministic/acquisition policy drift")
    artifacts = verify_job_artifacts(receipt_dir, receipt)
    artifact_map = result.get("artifact_map")
    expected_news_artifacts = {"articles.json", "scorecards.json", "unmatched.json", "match_summary.json"}
    if not isinstance(artifact_map, dict) or set(artifact_map) != expected_news_artifacts:
        raise IntelligenceReportError("News artifact_map rejected")
    article_desc = validate_descriptor(artifact_map.get("articles.json"), "News articles")
    pair = artifacts.get(article_desc["relative_path"])
    if pair is None or pair[0] != article_desc:
        raise IntelligenceReportError("News articles artifact binding mismatch")
    articles = load_json(pair[1], "News articles artifact")
    if not isinstance(articles, list):
        raise IntelligenceReportError("News articles artifact must be list")
    public_articles = []
    fields = (
        "symbol",
        "title",
        "source",
        "published_at",
        "match_method",
        "match_confidence",
        "relevance_class",
        "relevance_label",
        "relevance_action",
        "relevance_weight",
        "symbol_relevance_reason",
        "sentiment_score",
        "sentiment_label",
        "impact_score",
        "confidence",
        "score",
        "themes",
        "summary",
        "summary_source",
    )
    for row in articles[:100]:
        if isinstance(row, dict):
            public_articles.append({key: row.get(key) for key in fields if key in row})
    return {
        "job_id": receipt["job_id"],
        "job_fingerprint": receipt["job_fingerprint"],
        "dataset": validate_dataset(result.get("dataset"), "News"),
        "symbols": list(result.get("symbols") or []),
        "input_item_count": int(result.get("input_item_count") or 0),
        "matched_item_count": int(result.get("matched_item_count") or 0),
        "unmatched_item_count": int(result.get("unmatched_item_count") or 0),
        "scorecards": result.get("scorecards") if isinstance(result.get("scorecards"), list) else [],
        "scorecards_sha256": result.get("scorecards_sha256"),
        "articles_sha256": result.get("articles_sha256"),
        "article_evidence_displayed": len(public_articles),
        "article_evidence": public_articles,
        "articles_artifact": article_desc,
        "top_unmatched_entities": result.get("top_unmatched_entities")
        if isinstance(result.get("top_unmatched_entities"), list)
        else [],
        "policy": result.get("policy") if isinstance(result.get("policy"), dict) else {},
    }


def options_section(receipt_dir: Path, receipt: dict) -> dict:
    result = receipt["result"]
    if result.get("schema") != "mmibkr.options_snapshot_analysis.v1":
        raise IntelligenceReportError("Options result schema rejected")
    validate_result_authority(result, "Options result")
    policy = result.get("policy")
    if (
        not isinstance(policy, dict)
        or policy.get("snapshot_input_only") is not True
        or policy.get("ibkr_acquisition") is not False
        or policy.get("alpaca_acquisition") is not False
        or policy.get("network_acquisition") is not False
    ):
        raise IntelligenceReportError("Options snapshot/acquisition policy drift")
    artifacts = verify_job_artifacts(receipt_dir, receipt)
    if len(artifacts) != 2:
        raise IntelligenceReportError("Options canonical artifact set rejected")
    analytics_pair = None
    for rel, pair in artifacts.items():
        if rel.endswith("options_snapshot/analytics.json"):
            analytics_pair = pair
            break
    if analytics_pair is None:
        raise IntelligenceReportError("Options analytics artifact missing")
    rows = load_json(analytics_pair[1], "Options analytics artifact")
    if not isinstance(rows, list):
        raise IntelligenceReportError("Options analytics artifact must be list")
    public_rows = []
    fields = (
        "symbol",
        "expiry",
        "expiry_utc",
        "expiry_time_basis",
        "strike",
        "right",
        "bid",
        "ask",
        "last",
        "price_basis",
        "analysis_price",
        "volume",
        "notional_usd",
        "underlying_price",
        "as_of_utc",
        "time_to_expiry_years",
        "moneyness_pct",
        "ib_iv",
        "ib_delta",
        "ib_gamma",
        "ib_vega",
        "ib_theta",
        "calc_iv",
        "calc_delta",
        "calc_gamma",
        "calc_vega",
        "calc_theta",
        "comparison",
        "status",
        "reason",
        "reasons",
    )
    for row in rows[:100]:
        if isinstance(row, dict):
            public_rows.append({key: row.get(key) for key in fields if key in row})
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    return {
        "job_id": receipt["job_id"],
        "job_fingerprint": receipt["job_fingerprint"],
        "dataset": validate_dataset(result.get("dataset"), "Options"),
        "as_of_utc": result.get("as_of_utc"),
        "snapshot_state": result.get("snapshot_state"),
        "empty_reason": result.get("empty_reason"),
        "summary": summary,
        "analytics_sha256": result.get("analytics_sha256"),
        "analytics_rows_displayed": len(public_rows),
        "analytics_rows": public_rows,
        "analytics_artifact": analytics_pair[0],
        "policy": result.get("policy") if isinstance(result.get("policy"), dict) else {},
    }


def validate_llm_sidecar(path: Path, expected_sha256: str, report_sha256: str) -> tuple[dict, dict]:
    if not SHA256_RE.fullmatch(str(expected_sha256 or "").lower()):
        raise IntelligenceReportError("LLM sidecar expected SHA256 rejected")
    actual = file_sha256(path)
    if actual != expected_sha256.lower():
        raise IntelligenceReportError("LLM sidecar SHA256 mismatch")
    node = load_json(path, "LLM sidecar")
    if not isinstance(node, dict):
        raise IntelligenceReportError("LLM sidecar must be object")
    exact_fields(
        node,
        {"schema", "deterministic_report_sha256", "provider", "model", "generated_at", "sections"},
        "LLM sidecar",
    )
    if node.get("schema") != LLM_SCHEMA:
        raise IntelligenceReportError("LLM sidecar schema rejected")
    if node.get("deterministic_report_sha256") != report_sha256:
        raise IntelligenceReportError("LLM sidecar deterministic report binding mismatch")
    provider = str(node.get("provider") or "").strip()
    model = str(node.get("model") or "").strip()
    generated_at = str(node.get("generated_at") or "").strip()
    if not provider or len(provider) > 128 or not model or len(model) > 128 or len(generated_at) > 128:
        raise IntelligenceReportError("LLM sidecar metadata rejected")
    sections = node.get("sections")
    if not isinstance(sections, dict) or len(sections) > 16:
        raise IntelligenceReportError("LLM sidecar sections rejected")
    clean_sections = {}
    total = 0
    for raw_key, raw_text in sorted(sections.items()):
        key = str(raw_key or "").strip()
        text = str(raw_text or "")
        if not ID_RE.fullmatch(key) or len(text) > 20000:
            raise IntelligenceReportError("LLM sidecar section rejected")
        total += len(text.encode("utf-8"))
        clean_sections[key] = text
    if total > 100000:
        raise IntelligenceReportError("LLM sidecar narrative exceeds bound")
    clean = {
        "schema": LLM_SCHEMA,
        "deterministic_report_sha256": report_sha256,
        "provider": provider,
        "model": model,
        "generated_at": generated_at,
        "sections": clean_sections,
    }
    descriptor = {"sha256": actual, "bytes": path.stat().st_size, "name": path.name}
    return clean, descriptor


def _h(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, sort_keys=True, ensure_ascii=False)
    return html.escape(str(value), quote=True)


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    head = "".join(f"<th>{_h(item)}</th>" for item in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{_h(cell)}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def render_html(report: dict, report_sha256: str, llm: dict | None) -> str:
    parts = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        "<title>MM-IBKR Intelligence Report</title>",
        """<style>
body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;margin:24px;color:#171717;background:#fff}
main{max-width:1500px;margin:auto}.meta{font-size:13px;color:#555}.pill{display:inline-block;padding:3px 8px;border:1px solid #bbb;border-radius:999px;margin:2px 4px 2px 0}
section{margin:28px 0}h1,h2,h3{margin-bottom:8px}table{border-collapse:collapse;width:100%;font-size:12px;margin:10px 0 18px}
th,td{border:1px solid #ddd;padding:6px 8px;vertical-align:top;text-align:left}th{background:#f5f5f5;position:sticky;top:0}
code,pre{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}pre{white-space:pre-wrap;border:1px solid #ddd;background:#fafafa;padding:10px}
.notice{border-left:4px solid #777;padding:10px 12px;background:#f7f7f7}.truth{font-weight:600}.muted{color:#666}
</style></head><body><main>""",
        "<h1>MM-IBKR Intelligence Report</h1>",
        f'<div class="meta">Plan: <code>{_h(report["plan"]["plan_id"])}</code> &nbsp; Deterministic report SHA-256: <code>{_h(report_sha256)}</code></div>',
        '<p class="notice"><strong>Research only.</strong> Provider acquisition, StrategySpec mutation, runtime activation, promotion mutation, broker submit/cancel/flatten, and live trading authority are all absent.</p>',
        "<h2>Provenance</h2>",
    ]
    job_rows = []
    for job in report["jobs"]:
        mm = job["mmibkr"]
        dataset = job.get("dataset") or {}
        job_rows.append(
            [
                job["job_id"],
                job["capability_id"],
                job["job_fingerprint"],
                job["receipt_sha256"],
                mm["commit"],
                mm["source_archive_sha256"],
                dataset.get("relative_path", ""),
                dataset.get("sha256", ""),
            ]
        )
    parts.append(
        _table(
            [
                "Job",
                "Capability",
                "Job fingerprint",
                "Receipt canonical SHA",
                "MM commit",
                "Source archive SHA",
                "Dataset",
                "Dataset SHA",
            ],
            job_rows,
        )
    )

    parts.append("<h2>Deterministic News intelligence</h2>")
    if not report["news"]:
        parts.append('<p class="muted">No NEWS_REPLAY_ANALYZE receipt is present in this plan.</p>')
    for section in report["news"]:
        parts.append(f'<section><h3>{_h(section["job_id"])}</h3>')
        parts.append(
            f'<p>Matched <strong>{section["matched_item_count"]}</strong> items; '
            f'unmatched <strong>{section["unmatched_item_count"]}</strong>. '
            'Scoring shown here is deterministic. Designated LLM narrative, if supplied, is rendered separately below.</p>'
        )
        score_rows = []
        for row in section["scorecards"]:
            if not isinstance(row, dict):
                continue
            score_rows.append(
                [
                    row.get("symbol"),
                    row.get("rank"),
                    row.get("articles"),
                    row.get("score"),
                    row.get("avg_relevance"),
                    row.get("avg_match_confidence"),
                    row.get("summary_source"),
                ]
            )
        parts.append(
            _table(
                ["Symbol", "Rank", "Articles", "Score", "Avg relevance", "Avg match confidence", "Summary source"],
                score_rows,
            )
        )
        article_rows = []
        for row in section["article_evidence"]:
            article_rows.append(
                [
                    row.get("symbol"),
                    row.get("published_at"),
                    row.get("source"),
                    row.get("title"),
                    row.get("match_method"),
                    row.get("relevance_class"),
                    row.get("match_confidence"),
                    row.get("sentiment_label"),
                    row.get("sentiment_score"),
                    row.get("impact_score"),
                    row.get("confidence"),
                    row.get("symbol_relevance_reason"),
                    row.get("themes"),
                ]
            )
        parts.append(
            _table(
                [
                    "Symbol",
                    "Published",
                    "Source",
                    "Title",
                    "Match",
                    "Relevance",
                    "Match confidence",
                    "Sentiment",
                    "Sentiment score",
                    "Impact",
                    "Confidence",
                    "Why associated",
                    "Themes",
                ],
                article_rows,
            )
        )
        parts.append("</section>")

    parts.append("<h2>Deterministic Options intelligence</h2>")
    if not report["options"]:
        parts.append('<p class="muted">No OPTIONS_SNAPSHOT_ANALYZE receipt is present in this plan.</p>')
    for section in report["options"]:
        parts.append(f'<section><h3>{_h(section["job_id"])}</h3>')
        state = section.get("snapshot_state")
        empty_reason = section.get("empty_reason")
        parts.append(
            f'<p class="truth">Snapshot truth: {_h(state)}</p>'
            + (f'<p>Availability explanation: {_h(empty_reason)}</p>' if empty_reason else "")
        )
        summary = section.get("summary") or {}
        parts.append(
            "<p>"
            f'As of {_h(section.get("as_of_utc"))}; '
            f'captured at {_h(summary.get("captured_at"))}; '
            f'source {_h(summary.get("capture_source"))}; '
            f'analyzed {int(summary.get("analyzed_row_count") or 0)} / {int(summary.get("input_row_count") or 0)} rows; '
            f'unavailable {int(summary.get("unavailable_row_count") or 0)}; '
            f'total notional USD {_h(summary.get("total_notional_usd"))}.'
            "</p>"
        )
        option_rows = []
        for row in section["analytics_rows"]:
            option_rows.append(
                [
                    row.get("symbol"),
                    row.get("expiry_utc") or row.get("expiry"),
                    row.get("strike"),
                    row.get("right"),
                    row.get("analysis_price"),
                    row.get("price_basis"),
                    row.get("volume"),
                    row.get("notional_usd"),
                    row.get("underlying_price"),
                    row.get("moneyness_pct"),
                    row.get("calc_iv"),
                    row.get("calc_delta"),
                    row.get("calc_gamma"),
                    row.get("calc_vega"),
                    row.get("calc_theta"),
                    row.get("status"),
                    row.get("reason"),
                ]
            )
        parts.append(
            _table(
                [
                    "Symbol",
                    "Expiry",
                    "Strike",
                    "Right",
                    "Price",
                    "Price basis",
                    "Volume",
                    "Notional USD",
                    "Underlying",
                    "Moneyness %",
                    "Calc IV",
                    "Delta",
                    "Gamma",
                    "Vega",
                    "Theta",
                    "Status",
                    "Reason",
                ],
                option_rows,
            )
        )
        parts.append("</section>")

    parts.append("<h2>Designated LLM enrichment</h2>")
    if llm is None:
        parts.append(
            '<p class="notice">Not provided. No generative narrative is mixed into the deterministic News or Options fields above.</p>'
        )
    else:
        parts.append(
            f'<p class="notice">External sidecar bound to deterministic report SHA-256. '
            f'Provider: {_h(llm["provider"])}; model: {_h(llm["model"])}; generated: {_h(llm["generated_at"])}. '
            'This section cannot overwrite deterministic fields.</p>'
        )
        for key, text in llm["sections"].items():
            parts.append(f"<h3>{_h(key)}</h3><pre>{_h(text)}</pre>")
    parts.append("</main></body></html>\n")
    return "".join(parts)


def materialize_report(
    *,
    plan_receipt_path: Path,
    receipt_dir: Path,
    output_dir: Path,
    llm_sidecar_path: Path | None = None,
    llm_sidecar_sha256: str | None = None,
) -> dict:
    receipt_dir = receipt_dir.resolve()
    output_dir = output_dir.resolve()
    plan_receipt_path = require_inside(receipt_dir, plan_receipt_path, "plan receipt")
    if not plan_receipt_path.is_file():
        raise IntelligenceReportError("plan receipt missing")
    raw_plan = load_json(plan_receipt_path, "plan receipt")
    plan = validate_plan_receipt(raw_plan)
    expected_name = f"plan-{plan['plan_id']}.json"
    if plan_receipt_path.name != expected_name:
        raise IntelligenceReportError("plan receipt filename does not match plan_id")

    job_provenance = []
    news = []
    options = []
    for job_id, state in plan["jobs"].items():
        receipt, provenance = load_job_receipt(receipt_dir, job_id, state)
        job_provenance.append(provenance)
        capability = provenance["capability_id"]
        if capability == "NEWS_REPLAY_ANALYZE":
            news.append(news_section(receipt_dir, receipt))
        elif capability == "OPTIONS_SNAPSHOT_ANALYZE":
            options.append(options_section(receipt_dir, receipt))

    if not news and not options:
        raise IntelligenceReportError("plan contains no supported News/Options intelligence receipts")

    report = {
        "schema": REPORT_SCHEMA,
        "plan": {
            "plan_id": plan["plan_id"],
            "plan_receipt_canonical_sha256": canonical_sha256(raw_plan),
            "plan_receipt_file_sha256": file_sha256(plan_receipt_path),
            "job_count": len(plan["jobs"]),
        },
        "jobs": job_provenance,
        "news": news,
        "options": options,
        "designated_llm_policy": {
            "status": "external_sidecar_optional",
            "deterministic_fields_overwritable": False,
            "binding_field": "deterministic_report_sha256",
        },
        "authority": dict(EXPECTED_AUTHORITY),
    }
    report_bytes = json_file_bytes(report)
    report_sha = hashlib.sha256(report_bytes).hexdigest()

    llm = None
    llm_descriptor = None
    if llm_sidecar_path is not None:
        if llm_sidecar_sha256 is None:
            raise IntelligenceReportError("LLM sidecar SHA256 is required")
        llm, llm_descriptor = validate_llm_sidecar(
            llm_sidecar_path.resolve(),
            llm_sidecar_sha256,
            report_sha,
        )
    elif llm_sidecar_sha256 is not None:
        raise IntelligenceReportError("LLM sidecar path is required when SHA256 is provided")

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "intelligence_report.json"
    html_path = output_dir / "intelligence_report.html"
    receipt_path = output_dir / "intelligence_report_materialization.json"

    report_path.write_bytes(report_bytes)
    html_bytes = render_html(report, report_sha, llm).encode("utf-8")
    html_path.write_bytes(html_bytes)

    materialization = {
        "schema": MATERIALIZATION_SCHEMA,
        "plan_id": plan["plan_id"],
        "deterministic_report": {
            "relative_path": report_path.name,
            "sha256": report_sha,
            "bytes": len(report_bytes),
        },
        "rendered_html": {
            "relative_path": html_path.name,
            "sha256": hashlib.sha256(html_bytes).hexdigest(),
            "bytes": len(html_bytes),
        },
        "llm_sidecar": (
            {"status": "provided", **llm_descriptor}
            if llm_descriptor is not None
            else {"status": "not_provided"}
        ),
        "authority": dict(EXPECTED_AUTHORITY),
    }
    receipt_path.write_bytes(json_file_bytes(materialization))
    return materialization


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan-receipt", required=True)
    parser.add_argument("--receipt-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--llm-sidecar")
    parser.add_argument("--llm-sidecar-sha256")
    args = parser.parse_args()
    try:
        result = materialize_report(
            plan_receipt_path=Path(args.plan_receipt),
            receipt_dir=Path(args.receipt_dir),
            output_dir=Path(args.output_dir),
            llm_sidecar_path=Path(args.llm_sidecar) if args.llm_sidecar else None,
            llm_sidecar_sha256=args.llm_sidecar_sha256,
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    except IntelligenceReportError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
