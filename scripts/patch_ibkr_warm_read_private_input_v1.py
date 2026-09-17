from __future__ import annotations

from pathlib import Path

WORKFLOW = Path('.github/workflows/ibkr-cloudflare-readonly-b1-r1.yml')


def replace_once(text: str, old: str, new: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'expected one patch anchor, found {count}: {old[:120]!r}')
    return text.replace(old, new, 1)


def replace_count(text: str, old: str, new: str, expected: int) -> str:
    count = text.count(old)
    if count != expected:
        raise RuntimeError(f'expected {expected} patch anchors, found {count}: {old[:120]!r}')
    return text.replace(old, new)


def replace_between(text: str, start: str, end: str, replacement: str) -> str:
    a = text.find(start)
    if a < 0:
        raise RuntimeError(f'start marker missing: {start!r}')
    b = text.find(end, a)
    if b < 0:
        raise RuntimeError(f'end marker missing: {end!r}')
    return text[:a] + replacement + text[b:]


def patch(text: str) -> str:
    old_inputs = """      symbols:\n        description: Comma-separated market symbols for the read-only post-auth handoff\n        required: false\n        default: 'AMAT,APH'\n        type: string\n      read_return_recipient_b64:\n        description: Optional one-run X25519 public recipient for encrypted detailed read return\n        required: false\n        default: ''\n        type: string\n      read_return_recipient_key_id:\n        description: SHA-256 fingerprint of the encrypted read-return recipient\n        required: false\n        default: ''\n        type: string\n"""
    new_inputs = """      read_return_requested:\n        description: Request one encrypted private-input broker/account/market snapshot\n        required: false\n        default: false\n        type: boolean\n"""
    text = replace_once(text, old_inputs, new_inputs)
    text = replace_once(
        text,
        "      - assistant/ibkr-warm-read-gateway-20260917\n",
        "      - assistant/ibkr-warm-read-gateway-20260917\n      - assistant/ibkr-warm-read-private-input-20260917\n",
    )
    text = replace_once(
        text,
        "      - 'scripts/ibkr_warm_read_return_v1.py'\n",
        "      - 'scripts/ibkr_warm_read_return_v1.py'\n      - 'scripts/ibkr_warm_read_request_v1.py'\n",
    )
    text = replace_once(
        text,
        "      - 'tests/test_ibkr_warm_read_return_v1.py'\n",
        "      - 'tests/test_ibkr_warm_read_return_v1.py'\n      - 'tests/test_ibkr_warm_read_request_v1.py'\n",
    )
    text = replace_count(
        text,
        "            scripts/ibkr_warm_read_return_v1.py \\\n            research/forward_bar_contract_v2.py",
        "            scripts/ibkr_warm_read_return_v1.py \\\n            scripts/ibkr_warm_read_request_v1.py \\\n            research/forward_bar_contract_v2.py",
        2,
    )
    text = replace_count(
        text,
        "            tests/test_ibkr_warm_read_return_v1.py",
        "            tests/test_ibkr_warm_read_return_v1.py \\\n            tests/test_ibkr_warm_read_request_v1.py",
        2,
    )
    text = replace_count(
        text,
        "            tests.test_ibkr_warm_read_return_v1 -v",
        "            tests.test_ibkr_warm_read_return_v1 \\\n            tests.test_ibkr_warm_read_request_v1 -v",
        2,
    )
    text = replace_once(
        text,
        "      POST_AUTH_SYMBOLS: ${{ github.event_name == 'workflow_dispatch' && inputs.symbols || 'AMAT,APH' }}\n      IBKR_WARM_READ_RETURN_REQUESTED: ${{ github.event_name == 'workflow_dispatch' && inputs.mode == 'readonly' && inputs.read_return_recipient_b64 != '' && inputs.read_return_recipient_key_id != '' && '1' || '0' }}\n",
        "      POST_AUTH_SYMBOLS: AMAT,APH\n      IBKR_WARM_READ_RETURN_REQUESTED: '0'\n",
    )

    start = "      - name: Validate optional encrypted warm read-return request\n"
    end = "      - name: Obtain one-run sealed gateway environment\n"
    replacement = """      - name: Materialize optional encrypted warm read request\n        if: ${{ github.event_name == 'workflow_dispatch' && inputs.read_return_requested }}\n        env:\n          GH_TOKEN: ${{ github.token }}\n          READ_RETURN_MODE: ${{ inputs.mode }}\n          READ_DISPATCH_NONCE: ${{ inputs.dispatch_nonce }}\n        run: |\n          set -euo pipefail\n          test \"$READ_RETURN_MODE\" = \"readonly\" || { echo 'encrypted warm read request is admitted only in readonly mode'; exit 61; }\n          python scripts/ibkr_warm_read_request_v1.py \\\n            --run-id \"$GITHUB_RUN_ID\" \\\n            --public-head \"$GITHUB_SHA\" \\\n            --dispatch-nonce \"$READ_DISPATCH_NONCE\" \\\n            --repository \"$GITHUB_REPOSITORY\" \\\n            --exchange-ref rendezvous-exchange \\\n            --runner-temp \"$RUNNER_TEMP\" \\\n            --wait-seconds 900\n          python - <<'PY'\n          import json, os\n          from pathlib import Path\n          request=json.loads((Path(os.environ['RUNNER_TEMP'])/'ibkr-warm-read-request'/'request.json').read_text(encoding='utf-8'))\n          symbols=','.join(request['symbols'])\n          recipient=request['return_recipient']\n          env=Path(os.environ['GITHUB_ENV'])\n          with env.open('a',encoding='utf-8') as handle:\n              handle.write('POST_AUTH_SYMBOLS='+symbols+'\\n')\n              handle.write('READ_RETURN_RECIPIENT_B64='+recipient['recipient_b64']+'\\n')\n              handle.write('READ_RETURN_RECIPIENT_KEY_ID='+recipient['recipient_key_id']+'\\n')\n              handle.write('IBKR_WARM_READ_RETURN_REQUESTED=1\\n')\n          print('IBKR_WARM_READ_REQUEST_MATERIALIZED=1')\n          print('IBKR_WARM_READ_REQUEST_SYMBOLS_PRIVATE=1')\n          PY\n\n"""
    text = replace_between(text, start, end, replacement)

    old_encrypt = """      - name: Encrypt optional detailed warm read snapshot for private consumer\n        id: warm_read_return\n        if: env.IBKR_WARM_READ_RETURN_REQUESTED == '1'\n        env:\n          READ_RETURN_RECIPIENT_B64: ${{ inputs.read_return_recipient_b64 }}\n          READ_RETURN_RECIPIENT_KEY_ID: ${{ inputs.read_return_recipient_key_id }}\n        run: |\n"""
    new_encrypt = """      - name: Encrypt optional detailed warm read snapshot for private consumer\n        id: warm_read_return\n        if: env.IBKR_WARM_READ_RETURN_REQUESTED == '1'\n        run: |\n"""
    text = replace_once(text, old_encrypt, new_encrypt)
    text = replace_once(
        text,
        "            \"$RUNNER_TEMP/ibkr-warm-read-return\" \\\n            \"$RUNNER_TEMP/mm-ibkr-source\"",
        "            \"$RUNNER_TEMP/ibkr-warm-read-return\" \\\n            \"$RUNNER_TEMP/ibkr-warm-read-request\" \\\n            \"$RUNNER_TEMP/mm-ibkr-source\"",
    )
    return text


def main() -> None:
    text = WORKFLOW.read_text(encoding='utf-8')
    WORKFLOW.write_text(patch(text), encoding='utf-8')
    print('IBKR_WARM_READ_PRIVATE_INPUT_WORKFLOW_PATCHED=1')


if __name__ == '__main__':
    main()
