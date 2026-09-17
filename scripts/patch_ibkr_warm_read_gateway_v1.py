from __future__ import annotations

from pathlib import Path

WORKFLOW = Path('.github/workflows/ibkr-cloudflare-readonly-b1-r1.yml')
WORKFLOW_TEST = Path('tests/test_ibkr_b1_warm_state_workflow_v2.py')


def replace_once(text: str, old: str, new: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'expected exactly one workflow patch anchor, found {count}: {old[:120]!r}')
    return text.replace(old, new, 1)


def patch_workflow(text: str) -> str:
    text = replace_once(
        text,
        "      dispatch_nonce:\n        description: Optional one-run correlation token\n        required: false\n        default: ''\n        type: string\n",
        "      dispatch_nonce:\n        description: Optional one-run correlation token\n        required: false\n        default: ''\n        type: string\n"
        "      symbols:\n        description: Comma-separated market symbols for the read-only post-auth handoff\n        required: false\n        default: 'AMAT,APH'\n        type: string\n"
        "      read_return_recipient_b64:\n        description: Optional one-run X25519 public recipient for encrypted detailed read return\n        required: false\n        default: ''\n        type: string\n"
        "      read_return_recipient_key_id:\n        description: SHA-256 fingerprint of the encrypted read-return recipient\n        required: false\n        default: ''\n        type: string\n",
    )
    text = replace_once(
        text,
        "      - assistant/ibkr-warm-paper-proof-activation-20260917\n",
        "      - assistant/ibkr-warm-paper-proof-activation-20260917\n"
        "      - assistant/ibkr-warm-read-gateway-20260917\n",
    )
    text = replace_once(
        text,
        "      - 'scripts/ibkr_warm_selected_runtime_activation_v1.py'\n",
        "      - 'scripts/ibkr_warm_selected_runtime_activation_v1.py'\n"
        "      - 'scripts/ibkr_warm_read_return_v1.py'\n",
    )
    text = replace_once(
        text,
        "      - 'tests/test_ibkr_warm_selected_runtime_activation_v1.py'\n",
        "      - 'tests/test_ibkr_warm_selected_runtime_activation_v1.py'\n"
        "      - 'tests/test_ibkr_warm_read_return_v1.py'\n",
    )
    # The validation and broker dependency blocks each compile the activator.
    old_compile = "            scripts/ibkr_warm_selected_runtime_activation_v1.py \\\n            research/forward_bar_contract_v2.py"
    new_compile = "            scripts/ibkr_warm_selected_runtime_activation_v1.py \\\n            scripts/ibkr_warm_read_return_v1.py \\\n            research/forward_bar_contract_v2.py"
    if text.count(old_compile) != 2:
        raise RuntimeError(f'expected two compile anchors, found {text.count(old_compile)}')
    text = text.replace(old_compile, new_compile)

    old_test_compile = "            tests/test_ibkr_warm_selected_runtime_activation_v1.py"
    new_test_compile = "            tests/test_ibkr_warm_selected_runtime_activation_v1.py \\\n            tests/test_ibkr_warm_read_return_v1.py"
    if text.count(old_test_compile) != 2:
        raise RuntimeError(f'expected two test compile anchors, found {text.count(old_test_compile)}')
    text = text.replace(old_test_compile, new_test_compile)

    old_unittest = "            tests.test_ibkr_warm_selected_runtime_activation_v1 -v"
    new_unittest = "            tests.test_ibkr_warm_selected_runtime_activation_v1 \\\n            tests.test_ibkr_warm_read_return_v1 -v"
    if text.count(old_unittest) != 2:
        raise RuntimeError(f'expected two unittest anchors, found {text.count(old_unittest)}')
    text = text.replace(old_unittest, new_unittest)

    text = replace_once(
        text,
        "      POST_AUTH_SYMBOLS: AMAT,APH\n      IBKR_PAPER_PROOF_MODE:",
        "      POST_AUTH_SYMBOLS: ${{ github.event_name == 'workflow_dispatch' && inputs.symbols || 'AMAT,APH' }}\n"
        "      IBKR_WARM_READ_RETURN_REQUESTED: ${{ github.event_name == 'workflow_dispatch' && inputs.mode == 'readonly' && inputs.read_return_recipient_b64 != '' && inputs.read_return_recipient_key_id != '' && '1' || '0' }}\n"
        "      IBKR_PAPER_PROOF_MODE:",
    )

    text = replace_once(
        text,
        "      - name: Obtain one-run sealed gateway environment\n",
        "      - name: Validate optional encrypted warm read-return request\n"
        "        if: ${{ github.event_name == 'workflow_dispatch' && (inputs.read_return_recipient_b64 != '' || inputs.read_return_recipient_key_id != '') }}\n"
        "        env:\n"
        "          READ_RETURN_MODE: ${{ inputs.mode }}\n"
        "          READ_RETURN_RECIPIENT_B64: ${{ inputs.read_return_recipient_b64 }}\n"
        "          READ_RETURN_RECIPIENT_KEY_ID: ${{ inputs.read_return_recipient_key_id }}\n"
        "        run: |\n"
        "          set -euo pipefail\n"
        "          python - <<'PY'\n"
        "          import base64, hashlib, os\n"
        "          if os.environ.get('READ_RETURN_MODE') != 'readonly':\n"
        "              raise SystemExit('encrypted detailed read return is admitted only in readonly mode')\n"
        "          encoded=os.environ.get('READ_RETURN_RECIPIENT_B64','').strip()\n"
        "          key_id=os.environ.get('READ_RETURN_RECIPIENT_KEY_ID','').strip()\n"
        "          if not encoded or not key_id:\n"
        "              raise SystemExit('encrypted read return requires recipient key and fingerprint together')\n"
        "          try:\n"
        "              raw=base64.b64decode(encoded.encode('ascii'),validate=True)\n"
        "          except Exception as exc:\n"
        "              raise SystemExit('encrypted read return recipient is not valid base64') from exc\n"
        "          if len(raw) != 32:\n"
        "              raise SystemExit('encrypted read return recipient must be a 32-byte X25519 public key')\n"
        "          expected='sha256:'+hashlib.sha256(raw).hexdigest()\n"
        "          if key_id != expected:\n"
        "              raise SystemExit('encrypted read return recipient fingerprint mismatch')\n"
        "          print('IBKR_WARM_READ_RETURN_REQUEST_VALID=1')\n"
        "          PY\n\n"
        "      - name: Obtain one-run sealed gateway environment\n",
    )

    post_auth_anchor = "          echo 'IBKR_CONSUMER_READY=1'\n\n      - name: Execute one encrypted MM-authorized selected-runtime paper proof"
    post_auth_insert = "          echo 'IBKR_CONSUMER_READY=1'\n\n"
    post_auth_insert += "      - name: Encrypt optional detailed warm read snapshot for private consumer\n"
    post_auth_insert += "        id: warm_read_return\n"
    post_auth_insert += "        if: env.IBKR_WARM_READ_RETURN_REQUESTED == '1'\n"
    post_auth_insert += "        env:\n"
    post_auth_insert += "          READ_RETURN_RECIPIENT_B64: ${{ inputs.read_return_recipient_b64 }}\n"
    post_auth_insert += "          READ_RETURN_RECIPIENT_KEY_ID: ${{ inputs.read_return_recipient_key_id }}\n"
    post_auth_insert += "        run: |\n"
    post_auth_insert += "          set -euo pipefail\n"
    post_auth_insert += "          python scripts/ibkr_warm_read_return_v1.py \\\n"
    post_auth_insert += "            --host 127.0.0.1 \\\n"
    post_auth_insert += "            --port 4002 \\\n"
    post_auth_insert += "            --client-id 79 \\\n"
    post_auth_insert += "            --run-id \"$GITHUB_RUN_ID\" \\\n"
    post_auth_insert += "            --public-head \"$GITHUB_SHA\" \\\n"
    post_auth_insert += "            --handoff-file \"$RUNNER_TEMP/ibkr-post-auth-handoff.json\" \\\n"
    post_auth_insert += "            --bars-file \"$RUNNER_TEMP/ibkr-forward-bars-v2.jsonl\" \\\n"
    post_auth_insert += "            --recipient-b64 \"$READ_RETURN_RECIPIENT_B64\" \\\n"
    post_auth_insert += "            --recipient-key-id \"$READ_RETURN_RECIPIENT_KEY_ID\" \\\n"
    post_auth_insert += "            --output-dir \"$RUNNER_TEMP/ibkr-warm-read-return\"\n"
    post_auth_insert += "          echo 'ready=1' >> \"$GITHUB_OUTPUT\"\n"
    post_auth_insert += "          echo 'IBKR_WARM_READ_RETURN_ENCRYPTED=1'\n\n"
    post_auth_insert += "      - name: Publish encrypted warm read return\n"
    post_auth_insert += "        if: steps.warm_read_return.outputs.ready == '1'\n"
    post_auth_insert += "        env:\n"
    post_auth_insert += "          GH_TOKEN: ${{ github.token }}\n"
    post_auth_insert += "        run: |\n"
    post_auth_insert += "          set -euo pipefail\n"
    post_auth_insert += "          python - <<'PY'\n"
    post_auth_insert += "          import base64,json,os,subprocess\n"
    post_auth_insert += "          from pathlib import Path\n"
    post_auth_insert += "          root=Path(os.environ['RUNNER_TEMP'])/'ibkr-warm-read-return'\n"
    post_auth_insert += "          envelope=json.loads((root/'ibkr-warm-read-envelope.json').read_text(encoding='utf-8'))\n"
    post_auth_insert += "          run_id=os.environ['GITHUB_RUN_ID']\n"
    post_auth_insert += "          if str(envelope.get('run_id')) != run_id:\n"
    post_auth_insert += "              raise SystemExit('encrypted warm read return run id mismatch')\n"
    post_auth_insert += "          prefix=f'rendezvous/returns/{run_id}/'\n"
    post_auth_insert += "          files=[]\n"
    post_auth_insert += "          for node in envelope.get('chunks') or []:\n"
    post_auth_insert += "              path=str(node.get('path') or '')\n"
    post_auth_insert += "              local_name=str(node.get('local_name') or '')\n"
    post_auth_insert += "              if not path.startswith(prefix) or '..' in path.split('/') or '/' in local_name:\n"
    post_auth_insert += "                  raise SystemExit('encrypted warm read return publish path rejected')\n"
    post_auth_insert += "              files.append((path, root/local_name))\n"
    post_auth_insert += "          files.append((prefix+'ibkr-warm-read-envelope.json', root/'ibkr-warm-read-envelope.json'))\n"
    post_auth_insert += "          repo=os.environ['GITHUB_REPOSITORY']\n"
    post_auth_insert += "          for path,local in files:\n"
    post_auth_insert += "              content=base64.b64encode(local.read_bytes()).decode('ascii')\n"
    post_auth_insert += "              subprocess.run([\n"
    post_auth_insert += "                  'gh','api','--method','PUT',f'/repos/{repo}/contents/{path}',\n"
    post_auth_insert += "                  '-f','message=rendezvous: publish encrypted IBKR warm read return',\n"
    post_auth_insert += "                  '-f',f'content={content}','-f','branch=rendezvous-exchange',\n"
    post_auth_insert += "              ],check=True,stdout=subprocess.DEVNULL)\n"
    post_auth_insert += "          print('IBKR_WARM_READ_RETURN_PUBLISHED=1')\n"
    post_auth_insert += "          print('IBKR_WARM_READ_RETURN_PLAINTEXT_PUBLISHED=0')\n"
    post_auth_insert += "          PY\n\n"
    post_auth_insert += "      - name: Execute one encrypted MM-authorized selected-runtime paper proof"
    text = replace_once(text, post_auth_anchor, post_auth_insert)

    text = replace_once(
        text,
        "            \"$RUNNER_TEMP/ibkr-paper-proof-return\" \\\n            \"$RUNNER_TEMP/mm-ibkr-source\"",
        "            \"$RUNNER_TEMP/ibkr-paper-proof-return\" \\\n"
        "            \"$RUNNER_TEMP/ibkr-warm-read-return\" \\\n"
        "            \"$RUNNER_TEMP/mm-ibkr-source\"",
    )
    return text


def patch_workflow_test(text: str) -> str:
    anchor = "\n\nif __name__ == '__main__':\n    unittest.main()\n"
    addition = r'''

    def test_optional_warm_read_return_is_readonly_run_bound_and_encrypted(self):
        self.assertIn('read_return_recipient_b64:', self.text)
        self.assertIn('read_return_recipient_key_id:', self.text)
        self.assertIn('symbols:', self.text)
        self.assertIn("inputs.mode == 'readonly'", self.text)
        self.assertIn('IBKR_WARM_READ_RETURN_REQUEST_VALID=1', self.text)
        self.assertIn('python scripts/ibkr_warm_read_return_v1.py', self.text)
        self.assertIn('--run-id "$GITHUB_RUN_ID"', self.text)
        self.assertIn('--public-head "$GITHUB_SHA"', self.text)
        self.assertIn('rendezvous/returns/{run_id}/', self.text)
        self.assertIn('IBKR_WARM_READ_RETURN_PLAINTEXT_PUBLISHED=0', self.text)
        self.assertIn('"$RUNNER_TEMP/ibkr-warm-read-return"', self.text)

        post_auth = self.text.index('name: Materialize canonical post-auth broker and forward-data handoff')
        encrypt = self.text.index('name: Encrypt optional detailed warm read snapshot for private consumer')
        publish = self.text.index('name: Publish encrypted warm read return')
        proof = self.text.index('name: Execute one encrypted MM-authorized selected-runtime paper proof')
        stop = self.text.index('name: Gracefully stop authenticated Gateway before warm-state snapshot')
        self.assertLess(post_auth, encrypt)
        self.assertLess(encrypt, publish)
        self.assertLess(publish, proof)
        self.assertLess(proof, stop)

    def test_warm_read_return_does_not_enable_writable_gateway(self):
        self.assertIn("IBKR_WARM_READ_RETURN_REQUESTED: ${{ github.event_name == 'workflow_dispatch' && inputs.mode == 'readonly'", self.text)
        writable = self.text.index('if [ "$IBKR_PAPER_PROOF_MODE" = "1" ]; then')
        writable_tail = self.text[writable:writable + 160]
        self.assertIn('api_read_only=no', writable_tail)
        self.assertNotIn('IBKR_WARM_READ_RETURN_REQUESTED', writable_tail)
'''
    if anchor not in text:
        raise RuntimeError('workflow test final anchor not found')
    return text.replace(anchor, addition + anchor, 1)


def main() -> None:
    workflow = WORKFLOW.read_text(encoding='utf-8')
    workflow_test = WORKFLOW_TEST.read_text(encoding='utf-8')
    WORKFLOW.write_text(patch_workflow(workflow), encoding='utf-8')
    WORKFLOW_TEST.write_text(patch_workflow_test(workflow_test), encoding='utf-8')
    print('IBKR_WARM_READ_GATEWAY_WORKFLOW_PATCHED=1')


if __name__ == '__main__':
    main()
