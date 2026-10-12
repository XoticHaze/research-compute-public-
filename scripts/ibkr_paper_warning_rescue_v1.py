#!/usr/bin/env python3
"""Bounded paper-only rescue for the known IB Gateway non-brokerage warning.

Invoked INSIDE the existing pinned ibg-controller container while the
canonical B1 startup probes the API. Uses its existing in-JVM input agent;
never opens a browser, switches account, reads secrets, or places orders.
No raw UI text is ever printed or persisted. If the exact paper-only
warning cannot be proved, it does nothing and the existing gate fails closed.
"""
from __future__ import annotations

import argparse
import os
import re
import socket
import time

SOCKET_PATH = "/tmp/gateway-input.sock"
PAPER_TEXT = re.compile(
    r"(?:not\s+a\s+brokerage\s+account|this\s+is\s+a\s+paper\s+account|"
    r"paper\s+trading\s+account|simulated\s+trading\s+account)",
    re.IGNORECASE,
)
# Current controller already knows "I understand and accept", "I Accept",
# "Acknowledge", etc. These are the IBC-era alternate paper-warning labels.
# Bare OK, Continue, Login, Submit, and all arbitrary controls are denied.
BUTTONS = ("I understand", "I Understand", "I agree", "I Agree", "Agree")


def agent_request(command: str, *, multiline: bool = True) -> str:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(3.0)
        s.connect(SOCKET_PATH)
        s.sendall((command + "\n").encode("utf-8"))
        data = bytearray()
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and len(data) < 65536:
            chunk = s.recv(8192)
            if not chunk:
                break
            data.extend(chunk)
            if multiline and data.rstrip().endswith(b"END"):
                break
            if not multiline and b"\n" in data:
                break
    return data.decode("utf-8", errors="replace")


def parse_windows(raw: str) -> list[tuple[str, bool]]:
    found = []
    for line in raw.splitlines():
        parts = [v.strip() for v in line.split("|")]
        if len(parts) >= 3 and parts[2].lower() == "modal=true":
            found.append((parts[1], True))
    return found


def parse_labels(raw: str) -> list[tuple[str, str]]:
    found = []
    for line in raw.splitlines():
        if line.startswith("[") and "]" in line:
            i = line.index("]")
            found.append((line[1:i], line[i + 1:].strip()))
    return found


def parse_buttons(raw: str) -> set[str]:
    return {line[7:] for line in raw.splitlines() if line.startswith("button ")}


def select_exact_paper_warning(
    windows: list[tuple[str, bool]],
    labels: list[tuple[str, str]],
    buttons: set[str],
) -> tuple[str, str] | None:
    """Requires ONE modal, paper-specific text from that SAME window."""
    hits = []
    for title, modal in windows:
        if not modal or not title or "\n" in title or "|" in title:
            continue
        # Restrict to an actual warning/disclaimer, never a login or
        # account-configuration window even if its labels mention paper.
        if not re.search(r"warning|paper account|disclaimer|notice", title, re.I):
            continue
        if not any(t == title and PAPER_TEXT.search(message) for t, message in labels):
            continue
        btn = next((b for b in BUTTONS if b in buttons), None)
        if btn:
            hits.append((title, btn))
    return hits[0] if len(hits) == 1 else None


def run(*, apply: bool) -> int:
    if os.environ.get("TRADING_MODE") != "paper" or os.environ.get(
        "IBKR_PAPER_DISCLAIMER_RESCUE"
    ) != "1":
        print("IBKR_PAPER_WARNING_RESCUE=DENIED_MODE")
        return 0
    try:
        windows = parse_windows(agent_request("WINDOWS"))
        labels = parse_labels(agent_request("LABELS"))
        buttons = parse_buttons(agent_request("LIST"))
    except (OSError, ValueError, TimeoutError):
        print("IBKR_PAPER_WARNING_RESCUE=AGENT_NOT_READY")
        return 0

    selected = select_exact_paper_warning(windows, labels, buttons)
    if not selected:
        print("IBKR_PAPER_WARNING_RESCUE=NO_EXACT_PAPER_MODAL")
        return 0
    if not apply:
        print("IBKR_PAPER_WARNING_RESCUE=EXACT_MODAL_DRY_RUN")
        return 0
    title, button = selected
    try:
        result = agent_request(f"CLICK_IN_WIN {title}|{button}", multiline=False)
    except (OSError, ValueError, TimeoutError):
        print("IBKR_PAPER_WARNING_RESCUE=CLICK_ERROR")
        return 0
    print(
        "IBKR_PAPER_WARNING_RESCUE="
        + ("EXACT_MODAL_CLICKED" if result.startswith("OK") else "CLICK_REJECTED")
    )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    raise SystemExit(run(apply=args.apply))
