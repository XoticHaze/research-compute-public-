from __future__ import annotations

from pathlib import Path

PATH = Path('.github/workflows/ibkr-cloudflare-readonly-b1-r1.yml')


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise SystemExit(f'expected exactly one anchor, found {text.count(old)}: {old[:100]!r}')
    return text.replace(old, new, 1)


def main() -> None:
    text = PATH.read_text(encoding='utf-8')

    text = replace_once(
        text,
        '  workflow_dispatch:\n',
        "  workflow_dispatch:\n    inputs:\n      operation:\n        description: 'Explicit broker operation for this admitted warm run'\n        required: true\n        default: read_only\n        type: choice\n        options:\n          - read_only\n          - paper_submit_proof\n",
    )
    text = replace_once(
        text,
        '      - assistant/ibkr-warm-seed-owner-20260917\n',
        '      - assistant/ibkr-warm-seed-owner-20260917\n      - assistant/ibkr-warm-paper-proof-activation-20260917\n',
    )
    text = replace_once(
        text,
        "      - 'scripts/ibkr_post_auth_pipeline_v1.py'\n",
        "      - 'scripts/ibkr_post_auth_pipeline_v1.py'\n      - 'scripts/ibkr_remote_selected_runtime_command_capsule_v2.py'\n      - 'scripts/ibkr_remote_selected_runtime_paper_proof_v1.py'\n      - 'scripts/ibkr_remote_selected_runtime_paper_proof_v2.py'\n      - 'scripts/ibkr_remote_paper_proof_return_v1.py'\n      - 'tests/test_ibkr_remote_selected_runtime_paper_proof_v1.py'\n      - 'tests/test_ibkr_remote_selected_runtime_paper_proof_v2.py'\n      - 'tests/test_ibkr_remote_selected_runtime_command_capsule_v2.py'\n      - 'tests/test_ibkr_remote_paper_proof_return_v1.py'\n",
    )
    text = replace_once(
        text,
        "          echo 'IBKR_BROKER_LOGIN_ATTEMPTED=0'\n\n  broker-data-proof:\n",
        "          python -m py_compile \\\n            scripts/ibkr_remote_selected_runtime_command_capsule_v2.py \\\n            scripts/ibkr_remote_selected_runtime_paper_proof_v1.py \\\n            scripts/ibkr_remote_selected_runtime_paper_proof_v2.py \\\n            scripts/ibkr_remote_paper_proof_return_v1.py \\\n            tests/test_ibkr_remote_selected_runtime_paper_proof_v1.py \\\n            tests/test_ibkr_remote_selected_runtime_paper_proof_v2.py \\\n            tests/test_ibkr_remote_selected_runtime_command_capsule_v2.py \\\n            tests/test_ibkr_remote_paper_proof_return_v1.py\n          python -m unittest \\\n            tests.test_ibkr_remote_selected_runtime_paper_proof_v1 \\\n            tests.test_ibkr_remote_selected_runtime_paper_proof_v2 \\\n            tests.test_ibkr_remote_selected_runtime_command_capsule_v2 \\\n            tests.test_ibkr_remote_paper_proof_return_v1 -v\n          echo 'IBKR_SELECTED_RUNTIME_PAPER_PROOF_STATIC_VALID=1'\n          echo 'IBKR_BROKER_LOGIN_ATTEMPTED=0'\n\n  broker-data-proof:\n",
    )
    text = replace_once(
        text,
        "  broker-data-proof:\n    needs: validate\n    if: ${{ github.event_name == 'workflow_dispatch' || contains(github.event.head_commit.message, '[ibkr-login]') }}\n    runs-on: ubuntu-24.04\n    timeout-minutes: 40\n    env:\n      FLEET_AUTHORITY_URL: https://fleet-authority.slenderiq.workers.dev/v1/authorities/ibkr-paper/seal\n      IBKR_CONTROLLER_IMAGE: ghcr.io/code-hustler-ft3d/ibg-controller@sha256:5db4074ec952d130937afc3bb926ee97f115d09f7f46676eb16d98c2805572b5\n      POST_AUTH_SYMBOLS: AMAT,APH\n",
        "  broker-data-proof:\n    needs: validate\n    if: ${{ github.event_name == 'workflow_dispatch' || contains(github.event.head_commit.message, '[ibkr-login]') }}\n    runs-on: ubuntu-24.04\n    timeout-minutes: 55\n    permissions:\n      contents: write\n      actions: read\n      id-token: write\n    env:\n      FLEET_AUTHORITY_URL: https://fleet-authority.slenderiq.workers.dev/v1/authorities/ibkr-paper/seal\n      IBKR_CONTROLLER_IMAGE: ghcr.io/code-hustler-ft3d/ibg-controller@sha256:5db4074ec952d130937afc3bb926ee97f115d09f7f46676eb16d98c2805572b5\n      POST_AUTH_SYMBOLS: AMAT,APH\n      EXCHANGE_REF: rendezvous-exchange\n      RECIPIENT_ROOT: rendezvous/recipients\n      RESPONSE_ROOT: rendezvous/responses\n      RETURN_ROOT: rendezvous/returns\n      PAPER_PROOF_REQUESTED: ${{ (github.event_name == 'workflow_dispatch' && inputs.operation == 'paper_submit_proof') && '1' || '0' }}\n",
    )

    command_steps = r'''
      - name: Publish one-run selected-runtime command recipient
        if: env.PAPER_PROOF_REQUESTED == '1'
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          set -euo pipefail
          umask 077
          python - <<'PY'
          import base64, hashlib, json, os
          from pathlib import Path
          from cryptography.hazmat.primitives import serialization
          from cryptography.hazmat.primitives.asymmetric import x25519
          private=x25519.X25519PrivateKey.generate()
          private_raw=private.private_bytes(serialization.Encoding.Raw,serialization.PrivateFormat.Raw,serialization.NoEncryption())
          public_raw=private.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
          temp=Path(os.environ['RUNNER_TEMP'])
          (temp/'ibkr-remote-private.b64').write_text(base64.b64encode(private_raw).decode('ascii'))
          recipient={
              'schema':'ibkr-remote-paper-recipient-v1',
              'run_id':os.environ['GITHUB_RUN_ID'],
              'recipient_b64':base64.b64encode(public_raw).decode('ascii'),
              'recipient_key_id':'sha256:'+hashlib.sha256(public_raw).hexdigest(),
              'authority':'mm_ibkr_paper_runtime',
              'harness':'mm_ibkr_remote_paper_runtime_v1',
          }
          (temp/'ibkr-remote-recipient.json').write_text(json.dumps(recipient,sort_keys=True)+'\n')
          print('IBKR_REMOTE_RECIPIENT_KEY_ID='+recipient['recipient_key_id'])
          PY
          recipient_path="${RECIPIENT_ROOT}/${GITHUB_RUN_ID}-ibkr-remote-paper.json"
          gh api --method PUT "/repos/${GITHUB_REPOSITORY}/contents/${recipient_path}" \
            -f message='rendezvous: publish one-run IBKR paper proof recipient' \
            -f content="$(base64 -w0 "$RUNNER_TEMP/ibkr-remote-recipient.json")" \
            -f branch="$EXCHANGE_REF" >/dev/null
          echo "IBKR_REMOTE_RECIPIENT_PATH=${recipient_path}"

      - name: Wait for encrypted MM-IBKR selected-runtime command
        if: env.PAPER_PROOF_REQUESTED == '1'
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          set -euo pipefail
          response_root="${RESPONSE_ROOT}/${GITHUB_RUN_ID}"
          envelope_path="${response_root}/ibkr-remote-paper-envelope.json"
          found=0
          for _ in $(seq 1 360); do
            if gh api -H 'Accept: application/vnd.github.raw+json' "/repos/${GITHUB_REPOSITORY}/contents/${envelope_path}?ref=${EXCHANGE_REF}" > "$RUNNER_TEMP/ibkr-remote-envelope.json" 2>/dev/null; then
              found=1
              break
            fi
            sleep 5
          done
          test "$found" = 1 || { echo 'run-bound encrypted MM-IBKR paper proof command did not arrive'; exit 42; }
          echo "IBKR_REMOTE_RESPONSE_ROOT=${response_root}" >> "$GITHUB_ENV"

      - name: Reassemble and materialize credential-free command v2
        if: env.PAPER_PROOF_REQUESTED == '1'
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          set -euo pipefail
          python - <<'PY'
          import base64, hashlib, json, os, subprocess
          from pathlib import Path
          env=json.loads((Path(os.environ['RUNNER_TEMP'])/'ibkr-remote-envelope.json').read_text())
          chunks=env.get('chunks')
          if not isinstance(chunks,list) or not chunks or len(chunks)>64:
              raise SystemExit('invalid selected-runtime command chunk list')
          prefix=f"rendezvous/responses/{os.environ['GITHUB_RUN_ID']}/"
          pieces=[]; seen=set(); temp=Path(os.environ['RUNNER_TEMP'])
          for index,node in enumerate(chunks):
              if not isinstance(node,dict) or set(node)!={'path','sha256','chars'}:
                  raise SystemExit('invalid selected-runtime command chunk descriptor')
              path=str(node['path'])
              if not path.startswith(prefix) or path in seen or '..' in path.split('/'):
                  raise SystemExit('selected-runtime command chunk path rejected')
              seen.add(path)
              out=temp/f'ibkr-command-chunk-{index:03d}.txt'
              with out.open('wb') as fh:
                  subprocess.run(['gh','api','-H','Accept: application/vnd.github.raw+json',f"/repos/{os.environ['GITHUB_REPOSITORY']}/contents/{path}?ref={os.environ['EXCHANGE_REF']}"],check=True,stdout=fh)
              raw=out.read_bytes()
              if len(raw)!=int(node['chars']) or hashlib.sha256(raw).hexdigest()!=node['sha256']:
                  raise SystemExit('selected-runtime command chunk identity mismatch')
              pieces.append(raw.decode('ascii'))
          ciphertext=base64.b64decode(''.join(pieces).encode('ascii'),validate=True)
          if hashlib.sha256(ciphertext).hexdigest()!=env.get('ciphertext_sha256'):
              raise SystemExit('selected-runtime command ciphertext digest mismatch')
          (temp/'ibkr-remote-ciphertext.bin').write_bytes(ciphertext)
          PY
          python scripts/ibkr_remote_selected_runtime_command_capsule_v2.py \
            --envelope "$RUNNER_TEMP/ibkr-remote-envelope.json" \
            --ciphertext "$RUNNER_TEMP/ibkr-remote-ciphertext.bin" \
            --private-key "$RUNNER_TEMP/ibkr-remote-private.b64" \
            --run-id "$GITHUB_RUN_ID" \
            --response-root "$IBKR_REMOTE_RESPONSE_ROOT" \
            --runner-temp "$RUNNER_TEMP"
          echo 'IBKR_SELECTED_RUNTIME_COMMAND_READY=1'

'''
    text = replace_once(
        text,
        '      - name: Obtain one-run sealed gateway environment\n',
        command_steps + '      - name: Obtain one-run sealed gateway environment\n',
    )

    text = replace_once(
        text,
        "      - name: Refuse cold login inside IBKR reset window\n",
        "      - name: Require restored warm state for paper proof\n        if: env.PAPER_PROOF_REQUESTED == '1'\n        run: |\n          set -euo pipefail\n          test \"${{ steps.restore.outputs.restored }}\" = '1' || { echo 'paper proof requires accepted restored warm state'; exit 43; }\n          echo 'IBKR_PAPER_PROOF_WARM_STATE_REQUIRED=1'\n\n      - name: Refuse cold login inside IBKR reset window\n",
    )

    text = replace_once(
        text,
        '          warm_state_args=()\n',
        "          warm_state_args=()\n          gateway_read_only=yes\n          paper_proof_port_args=()\n          if [ \"$PAPER_PROOF_REQUESTED\" = 1 ]; then\n            gateway_read_only=no\n            paper_proof_port_args=(-p 127.0.0.1:8001:8001)\n          fi\n",
    )
    text = replace_once(text, '            -e READ_ONLY_API=yes \\\n', '            -e READ_ONLY_API="$gateway_read_only" \\\n')
    text = replace_once(
        text,
        '            -p 127.0.0.1:18080:8080 \\\n            "$IBKR_CONTROLLER_IMAGE" >/dev/null\n',
        '            -p 127.0.0.1:18080:8080 \\\n            "${paper_proof_port_args[@]}" \\\n            "$IBKR_CONTROLLER_IMAGE" >/dev/null\n',
    )
    text = replace_once(
        text,
        "          docker exec ibkr-cloudflare-b1 /bin/sh -lc 'test \"$TRADING_MODE\" = paper && test \"$READ_ONLY_API\" = yes && test \"$TWOFA_TIMEOUT_ACTION\" = none && test \"$TWOFA_EXIT_INTERVAL\" = 120 && test \"$RELOGIN_AFTER_TWOFA_TIMEOUT\" = yes' >/dev/null\n",
        "          docker exec ibkr-cloudflare-b1 /bin/sh -lc 'test \"$TRADING_MODE\" = paper && test \"$READ_ONLY_API\" = \"'$gateway_read_only'\" && test \"$TWOFA_TIMEOUT_ACTION\" = none && test \"$TWOFA_EXIT_INTERVAL\" = 120 && test \"$RELOGIN_AFTER_TWOFA_TIMEOUT\" = yes' >/dev/null\n          echo \"IBKR_GATEWAY_READ_ONLY_API=${gateway_read_only}\"\n",
    )

    proof_steps = r'''
      - name: Build exact private MM-IBKR source for selected-runtime paper proof
        if: env.PAPER_PROOF_REQUESTED == '1'
        run: |
          set -euo pipefail
          source_root="$(python - <<'PY'
          import json, os
          from pathlib import Path
          print(json.loads((Path(os.environ['RUNNER_TEMP'])/'ibkr-runtime.json').read_text())['source_root'])
          PY
          )"
          docker build --target bot -t "mmibkr-paper-proof:${GITHUB_RUN_ID}" "$source_root" >/dev/null
          echo 'IBKR_PRIVATE_SOURCE_BUILT=1'

      - name: Start canonical MM-IBKR control runtime for paper proof
        if: env.PAPER_PROOF_REQUESTED == '1'
        run: |
          set -euo pipefail
          mkdir -p "$RUNNER_TEMP/mmibkr-data"
          docker run -d --name mmibkr-paper-proof-bot \
            --network container:ibkr-cloudflare-b1 \
            -e IB_HOST=127.0.0.1 \
            -e IB_PORT=4004 \
            -e CLIENT_ID=34 \
            -e ENABLE_LIVE_TRADING=0 \
            -e CONTROL_API_ENABLED=true \
            -e CONTROL_API_HOST=0.0.0.0 \
            -e CONTROL_API_PORT=8001 \
            -e CONTROL_RUNTIME_PORT=8001 \
            -e BOT_SELECTED_RUNTIME_NATURAL_CANDIDATE_14TH31BV_ENABLED=0 \
            -e FUTURES_AUTO_ENABLED=0 \
            -e STRATEGY_IBKR_PAPER_ORDER_SUBMIT_ENABLED_13Z53=1 \
            -e STRATEGY_IBKR_PAPER_CANCEL_ENABLED_13Z37=1 \
            -e STRATEGY_IBKR_PAPER_GLOBAL_CANCEL_ENABLED_13Z37D=0 \
            -e STRATEGY_IBKR_PAPER_FLATTEN_ENABLED_13Z39=1 \
            -v "$RUNNER_TEMP/mmibkr-data:/app/data" \
            "mmibkr-paper-proof:${GITHUB_RUN_ID}" >/dev/null
          ready=0
          for _ in $(seq 1 90); do
            if curl -fsS --max-time 4 http://127.0.0.1:8001/healthz >/dev/null 2>&1; then ready=1; break; fi
            sleep 2
          done
          test "$ready" = 1 || { docker logs mmibkr-paper-proof-bot || true; echo 'canonical MM-IBKR control runtime did not become healthy'; exit 50; }
          echo 'IBKR_CANONICAL_CONTROL_RUNTIME_READY=1'

      - name: Execute MM-authorized selected-runtime paper proof through canonical routes
        if: env.PAPER_PROOF_REQUESTED == '1'
        run: |
          set -euo pipefail
          python scripts/ibkr_remote_selected_runtime_paper_proof_v2.py \
            --base-url http://127.0.0.1:8001 \
            --runtime "$RUNNER_TEMP/ibkr-runtime.json" \
            --receipt "$RUNNER_TEMP/ibkr-paper-proof-receipt.json" \
            --run-id "$GITHUB_RUN_ID" \
            --public-head "$GITHUB_SHA"
          echo 'IBKR_SELECTED_RUNTIME_PAPER_PROOF_EXECUTED=1'

      - name: Encrypt paper proof to private one-run recipient
        if: env.PAPER_PROOF_REQUESTED == '1'
        run: |
          set -euo pipefail
          python scripts/ibkr_remote_paper_proof_return_v1.py \
            --receipt "$RUNNER_TEMP/ibkr-paper-proof-receipt.json" \
            --runtime "$RUNNER_TEMP/ibkr-runtime.json" \
            --run-id "$GITHUB_RUN_ID" \
            --output-dir "$RUNNER_TEMP/ibkr-proof-return"
          echo 'IBKR_SELECTED_RUNTIME_PAPER_PROOF_ENCRYPTED=1'

      - name: Publish encrypted paper proof return only
        if: env.PAPER_PROOF_REQUESTED == '1'
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          set -euo pipefail
          python - <<'PY' > "$RUNNER_TEMP/ibkr-proof-return-files.tsv"
          import json, os
          from pathlib import Path
          root=Path(os.environ['RUNNER_TEMP'])/'ibkr-proof-return'
          env=json.loads((root/'ibkr-paper-proof-envelope.json').read_text())
          for node in env['chunks']:
              print(str(root/node['local_name'])+'\t'+node['path'])
          print(str(root/'ibkr-paper-proof-envelope.json')+'\t'+f"rendezvous/returns/{os.environ['GITHUB_RUN_ID']}/ibkr-paper-proof-envelope.json")
          PY
          while IFS=$'\t' read -r local_path remote_path; do
            gh api --method PUT "/repos/${GITHUB_REPOSITORY}/contents/${remote_path}" \
              -f message='rendezvous: publish encrypted selected-runtime paper proof return' \
              -f content="$(base64 -w0 "$local_path")" \
              -f branch="$EXCHANGE_REF" >/dev/null
          done < "$RUNNER_TEMP/ibkr-proof-return-files.tsv"
          echo 'IBKR_SELECTED_RUNTIME_PAPER_PROOF_RETURN_PUBLISHED=1'
          echo 'IBKR_PLAINTEXT_PAPER_PROOF_PUBLISHED=0'

      - name: Stop canonical MM-IBKR control runtime before Gateway snapshot
        if: env.PAPER_PROOF_REQUESTED == '1'
        run: |
          set -euo pipefail
          docker stop --time 30 mmibkr-paper-proof-bot >/dev/null
          docker rm -f mmibkr-paper-proof-bot >/dev/null
          echo 'IBKR_CANONICAL_CONTROL_RUNTIME_STOPPED=1'

'''
    text = replace_once(
        text,
        '      - name: Gracefully stop authenticated Gateway before warm-state snapshot\n',
        proof_steps + '      - name: Gracefully stop authenticated Gateway before warm-state snapshot\n',
    )

    text = replace_once(
        text,
        '          docker stop --time 90 ibkr-cloudflare-b1 >/dev/null 2>&1\n',
        '          docker rm -f mmibkr-paper-proof-bot >/dev/null 2>&1\n          docker image rm "mmibkr-paper-proof:${GITHUB_RUN_ID}" >/dev/null 2>&1\n          docker stop --time 90 ibkr-cloudflare-b1 >/dev/null 2>&1\n',
    )
    text = replace_once(
        text,
        '            "$RUNNER_TEMP/mm-ibkr-source.tar.gz" \\\n',
        '            "$RUNNER_TEMP/mm-ibkr-source.tar.gz" \\\n            "$RUNNER_TEMP/mm-ibkr-source" \\\n            "$RUNNER_TEMP/mmibkr-data" \\\n            "$RUNNER_TEMP/ibkr-submit-request.json" \\\n            "$RUNNER_TEMP/ibkr-runtime.json" \\\n            "$RUNNER_TEMP/ibkr-proof-return-recipient.json" \\\n            "$RUNNER_TEMP/ibkr-remote-private.b64" \\\n            "$RUNNER_TEMP/ibkr-remote-recipient.json" \\\n            "$RUNNER_TEMP/ibkr-remote-envelope.json" \\\n            "$RUNNER_TEMP/ibkr-remote-ciphertext.bin" \\\n            "$RUNNER_TEMP/ibkr-paper-proof-receipt.json" \\\n            "$RUNNER_TEMP/ibkr-proof-return" \\\n            "$RUNNER_TEMP/ibkr-proof-return-files.tsv" \\\n',
    ) if '            "$RUNNER_TEMP/mm-ibkr-source.tar.gz" \\\n' in text else text

    PATH.write_text(text, encoding='utf-8')
    print('IBKR_WARM_PAPER_PROOF_ACTIVATION_PATCHED=1')


if __name__ == '__main__':
    main()
