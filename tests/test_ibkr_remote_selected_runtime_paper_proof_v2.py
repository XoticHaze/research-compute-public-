import unittest

from scripts import ibkr_remote_selected_runtime_paper_proof_v2 as mod


class RemoteSelectedRuntimePaperProofV2Tests(unittest.TestCase):
    def _runtime(self):
        return {
            "schema": "mmibkr.remote_selected_runtime_materialization.v3",
            "mode": "paper_submit_proof",
            "gateway_auth_source": "fleet_authority_warm_state",
            "gateway_credentials_in_capsule": False,
            "paper_only": True,
            "live_trading_change": False,
            "read_only_api": "no",
            "cleanup": {
                "cancel_open_order": True,
                "flatten_filled_position": True,
                "require_zero_baseline": True,
                "allow_global_cancel": False,
            },
        }

    def test_valid_v3_runtime_is_admitted(self):
        runtime = mod.validate_fleet_authority_runtime(self._runtime())
        self.assertEqual(runtime["gateway_auth_source"], "fleet_authority_warm_state")
        self.assertFalse(runtime["gateway_credentials_in_capsule"])

    def test_legacy_materialization_is_rejected(self):
        runtime = self._runtime()
        runtime["schema"] = "mm-ibkr-remote-paper-materialization-v2"
        with self.assertRaisesRegex(RuntimeError, "materialization_v3_required"):
            mod.validate_fleet_authority_runtime(runtime)

    def test_wrong_auth_source_is_rejected(self):
        runtime = self._runtime()
        runtime["gateway_auth_source"] = "capsule_credentials"
        with self.assertRaisesRegex(RuntimeError, "fleet_authority_warm_state_required"):
            mod.validate_fleet_authority_runtime(runtime)

    def test_credential_flag_or_legacy_material_is_rejected(self):
        runtime = self._runtime()
        runtime["gateway_credentials_in_capsule"] = True
        with self.assertRaisesRegex(RuntimeError, "gateway_credentials_in_capsule_must_be_false"):
            mod.validate_fleet_authority_runtime(runtime)

        runtime = self._runtime()
        runtime["gateway_env_path"] = "/tmp/legacy.env"
        with self.assertRaisesRegex(RuntimeError, "legacy_gateway_credential_material_rejected"):
            mod.validate_fleet_authority_runtime(runtime)

    def test_v2_delegates_only_after_boundary_validation(self):
        calls = []

        def executor(**kwargs):
            calls.append(kwargs)
            return {"ok": True, "status": "CANONICAL_SUBMIT_BLOCKED", "authority": {}}

        receipt = mod.execute_paper_proof_v2(
            runtime=self._runtime(),
            request={"x": 1},
            send=lambda *args, **kwargs: (200, {}),
            run_id="123",
            public_head="abc",
            executor=executor,
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(receipt["authority"]["gateway_auth_source"], "fleet_authority_warm_state")
        self.assertFalse(receipt["authority"]["gateway_credentials_in_capsule"])
        self.assertFalse(receipt["authority"]["legacy_credential_capsule_allowed"])


if __name__ == "__main__":
    unittest.main()
