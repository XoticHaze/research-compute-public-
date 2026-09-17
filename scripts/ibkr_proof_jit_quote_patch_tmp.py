from pathlib import Path

path = Path('scripts/ibkr_remote_selected_runtime_paper_proof_v1.py')
text = path.read_text(encoding='utf-8')
anchor = '''def _flatten_snapshot(send: JsonSender, symbol: str) -> tuple[int, dict[str, Any]]:
    return send(
        "POST",
        "/strategy/ibkr-paper-flatten-preview-suite",
        payload={"preview_symbols": [symbol], "batch_symbols": [symbol], "candidate_limit": 50, "preview_limit": 1, "batch_limit": 1},
        timeout=60.0,
    )


'''
helper = '''def _flatten_snapshot(send: JsonSender, symbol: str) -> tuple[int, dict[str, Any]]:
    return send(
        "POST",
        "/strategy/ibkr-paper-flatten-preview-suite",
        payload={"preview_symbols": [symbol], "batch_symbols": [symbol], "candidate_limit": 50, "preview_limit": 1, "batch_limit": 1},
        timeout=60.0,
    )


def _positive_price(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _canonical_quote_final_limit(body: Mapping[str, Any]) -> float | None:
    if not isinstance(body, Mapping):
        return None
    limit_policy = body.get("limit_price_policy") if isinstance(body.get("limit_price_policy"), Mapping) else {}
    lmt_chase = body.get("lmt_chase_policy") if isinstance(body.get("lmt_chase_policy"), Mapping) else {}
    for value in (
        body.get("final_limit_price"),
        body.get("limit_price"),
        body.get("lmtPrice"),
        limit_policy.get("final_limit_price"),
        lmt_chase.get("base_limit_price"),
        lmt_chase.get("limit_price"),
    ):
        price = _positive_price(value)
        if price is not None:
            return price
    return None


def _jit_refresh_authorized_lmt_payload(
    *,
    send: JsonSender,
    payload: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    submit_payload = dict(payload)
    requested = submit_payload.get("remote_proof_refresh_limit_price") is True
    if not requested:
        return submit_payload, {"requested": False, "performed": False, "ok": None}

    order_type = str(submit_payload.get("order_type") or submit_payload.get("orderType") or "").strip().upper()
    if order_type != "LMT":
        return None, {
            "requested": True,
            "performed": False,
            "ok": False,
            "blockers": ["jit_quote_refresh_requires_lmt_order"],
        }

    quote_payload = dict(submit_payload)
    quote_payload["require_executable_quote"] = True
    # The command owns whether refresh is authorized; the canonical MM route owns
    # market-data/contract/session/limit policy. Cloud code only consumes its
    # returned final limit and never changes action, quantity, runtime, or contract.
    status, quote = send(
        "POST",
        "/strategy/ibkr-paper-quote-snapshot",
        payload=quote_payload,
        timeout=90.0,
    )
    final_limit = _canonical_quote_final_limit(quote)
    blockers = list(quote.get("blockers") or []) if isinstance(quote, Mapping) else []
    ok = bool(status == 200 and isinstance(quote, Mapping) and quote.get("ok") is True and final_limit is not None)
    evidence = {
        "requested": True,
        "performed": True,
        "ok": ok,
        "http_status": status,
        "status": quote.get("status") if isinstance(quote, Mapping) else None,
        "final_limit_price": final_limit,
        "executable_quote_available": quote.get("executable_quote_available") if isinstance(quote, Mapping) else None,
        "blockers": blockers,
        "canonical_route": "/strategy/ibkr-paper-quote-snapshot",
        "price_fields_only": True,
    }
    if not ok:
        if final_limit is None:
            evidence["blockers"] = sorted(set(blockers + ["canonical_quote_final_limit_required"]))
        return None, evidence

    for key in (
        "remote_proof_refresh_limit_price",
        "remote_proof_candidate_quote_received_at_utc",
        "remote_proof_candidate_quote_max_age_sec",
    ):
        submit_payload.pop(key, None)
    submit_payload.update({
        "limit_price": final_limit,
        "lmtPrice": final_limit,
        "reference_price": final_limit,
        "marketPrice": final_limit,
        "limit_price_source": "remote_proof_jit_canonical_quote_snapshot",
        "requested_price_source": "remote_proof_jit_canonical_quote_snapshot",
        "quote_materialized_limit_price_14th27b": final_limit,
    })
    return submit_payload, evidence


'''
if text.count(anchor) != 1:
    raise SystemExit('flatten snapshot helper anchor mismatch')
text = text.replace(anchor, helper, 1)

old_receipt = '''        "submit": {"called": False, "http_status": None, "ok": False, "broker_order_placed": False, "order_identity": {}},
        "cleanup": {"exact_cancel_called": False, "exact_cancel_ok": None, "flatten_called": False, "flatten_ok": None, "global_cancel_called": False},
'''
new_receipt = '''        "quote_refresh": {"requested": False, "performed": False, "ok": None},
        "submit": {"called": False, "http_status": None, "ok": False, "broker_order_placed": False, "order_identity": {}},
        "cleanup": {"exact_cancel_called": False, "exact_cancel_ok": None, "flatten_called": False, "flatten_ok": None, "global_cancel_called": False},
'''
if text.count(old_receipt) != 1:
    raise SystemExit('receipt anchor mismatch')
text = text.replace(old_receipt, new_receipt, 1)

old_submit = '''    submit_status, submit = send("POST", "/strategy/ibkr-paper-order-submit", payload=auth["payload"], timeout=120.0)
'''
new_submit = '''    submit_payload, quote_refresh = _jit_refresh_authorized_lmt_payload(send=send, payload=auth["payload"])
    receipt["quote_refresh"] = quote_refresh
    if submit_payload is None:
        receipt["status"] = "JIT_QUOTE_REFRESH_BLOCKED"
        return receipt

    submit_status, submit = send("POST", "/strategy/ibkr-paper-order-submit", payload=submit_payload, timeout=120.0)
'''
if text.count(old_submit) != 1:
    raise SystemExit('submit call anchor mismatch')
text = text.replace(old_submit, new_submit, 1)
path.write_text(text, encoding='utf-8')

# Extend focused proof tests without changing legacy cases.
test_path = Path('tests/test_ibkr_remote_selected_runtime_paper_proof_v1.py')
tests = test_path.read_text(encoding='utf-8')
insert = '''    def test_jit_quote_refresh_uses_canonical_quote_and_changes_only_price_fields(self):
        request = self._request()
        payload = request["canonical_submit_payload"]
        payload["remote_proof_refresh_limit_price"] = True
        payload["remote_proof_candidate_quote_received_at_utc"] = "2026-09-17T18:00:00Z"
        payload["remote_proof_candidate_quote_max_age_sec"] = 15
        payload["operator_approved"] = True
        payload["ibkr_paper_order_submit_ack_13z53"] = "IBKR_PAPER_ORDER_SUBMIT_ACK_13Z53"
        original_action = payload["action"]
        original_quantity = payload["quantity"]

        responses = self._base()
        responses[("POST", "/strategy/ibkr-paper-quote-snapshot")] = [
            (200, {
                "ok": True,
                "status": "ready",
                "executable_quote_available": True,
                "limit_price_policy": {"final_limit_price": 22010.25},
                "blockers": [],
            })
        ]
        responses[("POST", "/strategy/ibkr-paper-order-submit")] = [
            (409, {
                "ok": False,
                "status": "blocked",
                "place_order_called": False,
                "broker_order_placed": False,
                "guards": {"selected_runtime_id": "mnq-runtime"},
                "blockers": ["route_currently_active_required_or_explicit_override_13z53"],
            })
        ]
        sender = FakeSender(responses)
        receipt = execute_paper_proof(runtime=self._runtime(), request=request, send=sender, run_id="6", public_head="p")
        self.assertEqual(receipt["status"], "CANONICAL_SUBMIT_BLOCKED")
        self.assertTrue(receipt["quote_refresh"]["ok"])
        self.assertEqual(receipt["quote_refresh"]["final_limit_price"], 22010.25)
        submit_call = next(c for c in sender.calls if c["route"] == "/strategy/ibkr-paper-order-submit")
        self.assertEqual(submit_call["payload"]["action"], original_action)
        self.assertEqual(submit_call["payload"]["quantity"], original_quantity)
        self.assertEqual(submit_call["payload"]["limit_price"], 22010.25)
        self.assertEqual(submit_call["payload"]["lmtPrice"], 22010.25)
        self.assertEqual(submit_call["payload"]["limit_price_source"], "remote_proof_jit_canonical_quote_snapshot")
        self.assertNotIn("remote_proof_refresh_limit_price", submit_call["payload"])
        self.assertTrue(submit_call["payload"]["operator_approved"])
        self.assertEqual(submit_call["payload"]["ibkr_paper_order_submit_ack_13z53"], "IBKR_PAPER_ORDER_SUBMIT_ACK_13Z53")

    def test_jit_quote_refresh_failure_blocks_before_submit(self):
        request = self._request()
        request["canonical_submit_payload"]["remote_proof_refresh_limit_price"] = True
        responses = self._base()
        responses[("POST", "/strategy/ibkr-paper-quote-snapshot")] = [
            (409, {"ok": False, "status": "blocked", "blockers": ["executable_quote_source_missing_13z65"]})
        ]
        sender = FakeSender(responses)
        receipt = execute_paper_proof(runtime=self._runtime(), request=request, send=sender, run_id="7", public_head="p")
        self.assertEqual(receipt["status"], "JIT_QUOTE_REFRESH_BLOCKED")
        self.assertFalse(receipt["ok"])
        self.assertFalse(receipt["submit"]["called"])
        self.assertFalse(receipt["quote_refresh"]["ok"])
        self.assertFalse(any(c["route"] == "/strategy/ibkr-paper-order-submit" for c in sender.calls))

'''
anchor_test = '''    def test_live_authority_in_request_is_rejected(self):
'''
if tests.count(anchor_test) != 1:
    raise SystemExit('test insertion anchor mismatch')
tests = tests.replace(anchor_test, insert + anchor_test, 1)
test_path.write_text(tests, encoding='utf-8')
