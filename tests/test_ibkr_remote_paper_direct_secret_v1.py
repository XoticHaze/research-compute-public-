import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import ibkr_remote_paper_direct_secret_v1 as direct


def test_direct_secret_materialization_is_paper_read_only_host_independent(monkeypatch, tmp_path):
    monkeypatch.setenv("IBKR_REMOTE_TWS_USERID", "paper-user")
    monkeypatch.setenv("IBKR_REMOTE_TWS_PASSWORD", "paper-password")
    monkeypatch.setenv("IBKR_REMOTE_SOURCE_TOKEN", "source-token-value")
    monkeypatch.setattr(direct, "resolve_private_head", lambda token, ref: "a" * 40)
    monkeypatch.setattr(direct, "fetch_private_archive", lambda token, head, destination: "b" * 64)
    source_root = tmp_path / "mm-ibkr-source" / "repo"
    source_root.mkdir(parents=True)
    monkeypatch.setattr(direct, "_safe_extract_tar", lambda archive, destination: source_root)

    runtime = direct.materialize(runner_temp=tmp_path, source_ref="main")

    assert runtime["mode"] == "session_reconcile"
    assert runtime["paper_only"] is True
    assert runtime["read_only_api"] == "yes"
    assert runtime["live_trading_change"] is False
    assert runtime["host_dependency"] is False
    assert runtime["secrets_in_receipt"] is False
    assert runtime["credential_ingress"] == "github_actions_protected_secrets"
    assert runtime["cleanup"]["allow_global_cancel"] is False
    gateway = (tmp_path / "ibkr-gateway.env").read_text()
    assert "TRADING_MODE=paper" in gateway
    assert "READ_ONLY_API=yes" in gateway
    assert "TWS_USERID=paper-user" in gateway
    assert "TWS_PASSWORD=paper-password" in gateway
    public_runtime = (tmp_path / "ibkr-runtime.json").read_text()
    assert "paper-password" not in public_runtime
    assert "source-token-value" not in public_runtime
