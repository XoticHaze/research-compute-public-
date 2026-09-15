from __future__ import annotations

"""Sanitize IB Gateway/IBC logs into fixed login-state booleans/counts.

This classifier never emits source log lines, account identifiers, credentials,
or arbitrary matched text. It exists only to distinguish deterministic startup
states while keeping the public Actions log safe.
"""

import json
import sys


def present(text: str, *needles: str) -> bool:
    return any(needle in text for needle in needles)


def count(text: str, needle: str) -> int:
    return text.count(needle)


def main() -> None:
    raw = sys.stdin.read()
    text = raw.lower()

    login_completed = present(text, "ibc: login has completed")
    configuration_completed = present(text, "ibc: configuration tasks completed")
    twofa_initiated = present(text, "ibc: second factor authentication initiated")
    twofa_dialog = present(text, "detected dialog entitled: second factor authentication")
    device_selection = present(
        text,
        "could not find second factor device",
        "second factor device",
    ) and not present(text, "secondfactordevice=")

    result = {
        "schema": "mmibkr-ibkr-gateway-state-v1",
        "login_dialog_opened": present(text, "login dialog window_opened"),
        "paper_login_clicked": present(text, "click button: paper log in"),
        "loading_window_observed": present(text, "detected frame entitled: loading"),
        "starting_application_observed": present(text, "detected frame entitled: starting application"),
        "login_completed": login_completed,
        "configuration_completed": configuration_completed,
        "paper_warning_observed": present(text, "detected dialog entitled: warning"),
        "paper_warning_accepted": present(text, "click button: i understand and accept"),
        "twofa_initiated": twofa_initiated,
        "twofa_dialog_observed": twofa_dialog,
        "second_factor_device_selection_signal": device_selection,
        "credential_rejection_signal": present(
            text,
            "invalid username",
            "invalid password",
            "authentication failed",
            "login failed",
            "failed to authenticate",
        ),
        "existing_session_signal": present(text, "existing session"),
        "api_readonly_setting_observed": present(text, "setting readonlyapi", "read-only api checkbox"),
        "socat_internal_refused": present(text, "socat") and present(text, "connection refused"),
        "api_connection_reset_count": count(text, "connection reset by peer"),
        "login_attempt_count": count(text, "ibc: login attempt:"),
        "container_log_bytes": len(raw.encode("utf-8", errors="replace")),
    }

    if login_completed and configuration_completed:
        stage = "gateway_configured"
    elif login_completed:
        stage = "login_completed_configuration_pending"
    elif twofa_initiated or twofa_dialog:
        stage = "twofa_in_progress"
    elif result["paper_login_clicked"] and result["loading_window_observed"]:
        stage = "paper_login_submitted_loading"
    elif result["paper_login_clicked"]:
        stage = "paper_login_submitted"
    elif result["login_dialog_opened"]:
        stage = "login_dialog_ready"
    else:
        stage = "startup_before_login_dialog"
    result["stage"] = stage

    print("IBKR_GATEWAY_STATE=" + json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
