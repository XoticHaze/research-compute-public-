from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "fleet-authority-deploy-r2.yml"

def test_fleet_r2_deploy_is_single_owner_and_serialized():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "  deploy:\n    needs: r2_scope_audit\n" in text
    assert text.count("- name: Execute R2 scope audit") == 1
    assert text.count("- name: Persist R2 scope audit") == 1
    audit_job = text.split("\n  r2_scope_audit:\n", 1)[1].split("\n  deploy:\n", 1)[0]
    assert 'test -n "$CLOUDFLARE_DEPLOY_TOKEN_R2"' in audit_job
    assert "CLOUDFLARE_DEPLOY_TOKEN_R2: ${{ secrets.CLOUDFLARE_DEPLOY_TOKEN_R2 }}" in audit_job
    assert text.count("- name: Research Cloudflare R2 scope preflight") == 0
    assert text.count("- name: Publish R2 scope preflight receipt") == 0
    audit = text.split("- name: Persist R2 scope audit", 1)[1].split("- name: Require scope audit success", 1)[0]
    assert "git pull --rebase origin main" in audit
    assert "git push origin HEAD:main" in audit
    deploy = text.split("\n  deploy:\n", 1)[1]
    assert '"scoped_r2"' in deploy
    assert "FLEET_AUTHORITY_CONTROL_PLANE_PASS=1" in deploy
    assert "FLEET_AUTHORITY_HEALTH_PASS=1" in deploy
