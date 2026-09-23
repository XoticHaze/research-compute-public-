from pathlib import Path

import pytest

from mmibkr_private_test_probe_v1 import validated_modules, validate_source_identity


def test_allowlist_accepts_research_autotuner_and_registry_dispatch():
    assert validated_modules(
        "tests.test_autotuner_strategy_family_catalog_vnext,"
        "tests.test_autotuner_behavioral_consumption_vnext "
        "tests.test_strategy_backtest_registry_dispatch"
    ) == [
        "tests.test_autotuner_strategy_family_catalog_vnext",
        "tests.test_autotuner_behavioral_consumption_vnext",
        "tests.test_strategy_backtest_registry_dispatch",
    ]


@pytest.mark.parametrize(
    "module",
    [
        "tests.test_selected_runtime_submit_authority",
        "tests.test_ibkr_remote_submit",
        "tests.test_live_bot_runtime_scope",
        "tests.test_not_allowlisted",
        "../escape",
    ],
)
def test_allowlist_rejects_authority_or_unknown_modules(module):
    with pytest.raises(ValueError):
        validated_modules(module)


def test_source_identity_requires_sanitized_cloud_materialization(tmp_path: Path):
    source = tmp_path / "mm-ibkr"
    source.mkdir()
    (source / "Dockerfile.bot").write_text("FROM scratch\n", encoding="utf-8")
    materialization = tmp_path / "source.json"
    materialization.write_text(
        __import__("json").dumps(
            {
                "schema": "mmibkr.cloud_source_materialization.v1",
                "ok": True,
                "source_ref": "0123456789abcdef0123456789abcdef01234567",
                "source_sha": "0123456789abcdef0123456789abcdef01234567",
                "source_root": str(source.resolve()),
                "source_archive_sha256": "a" * 64,
                "source_archive_bytes": 123,
                "producer_identity": {"repository": "XoticHaze/mm-IBKR"},
                "private_repository_token_used": False,
                "broker_credentials_used": False,
                "plaintext_emitted": False,
            }
        ),
        encoding="utf-8",
    )
    node = validate_source_identity(
        source,
        materialization,
        "0123456789abcdef0123456789abcdef01234567",
    )
    assert node["source_sha"] == "0123456789abcdef0123456789abcdef01234567"
