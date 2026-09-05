import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[2]
DEPLOY_ROOT = ROOT / "deploy" / "tencent-lighthouse"


def _load_module(path: Path, name: str):
    assert path.is_file(), f"missing deployment component: {path.relative_to(ROOT)}"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runtime_cache_path_uses_persistent_data_root(monkeypatch):
    paths = _load_module(ROOT / "backend" / "data_paths.py", "deployment_data_paths")
    persistent_root = ROOT / ".deployment-test-data"
    monkeypatch.setenv("VR_DATA_DIR", str(persistent_root))

    assert paths.cache_path("rss") == persistent_root / "cache" / "rss"


def test_public_demo_preflight_accepts_session_auth_without_global_api_key():
    preflight = _load_module(ROOT / "scripts" / "production_preflight.py", "production_preflight")
    values = {
        "DOMAIN": "research.example.com",
        "GLM_API_KEY": "live-secret-value",
        "FT_OWNER_PASSWORD_HASH": "scrypt$32768$8$1$c2FsdA$a2V5",
        "FT_PUBLIC_DEMO": "true",
        "FT_AUTH_SECURE_COOKIE": "true",
        "FT_ALLOWED_ORIGINS": "https://research.example.com",
        "VR_ALLOW_ORIGINS": "https://research.example.com",
        "VR_DATA_DIR": "/data",
        "VR_API_KEY": "",
    }

    assert preflight.validate(values) == []


@pytest.mark.parametrize(
    ("name", "value", "expected"),
    [
        ("DOMAIN", "https://research.example.com", "DOMAIN"),
        ("GLM_API_KEY", "replace-me", "GLM_API_KEY"),
        ("FT_OWNER_PASSWORD_HASH", "plain-password", "FT_OWNER_PASSWORD_HASH"),
        ("FT_AUTH_SECURE_COOKIE", "false", "FT_AUTH_SECURE_COOKIE"),
        ("VR_DATA_DIR", "/tmp", "VR_DATA_DIR"),
        ("VR_API_KEY", "shared-browser-secret", "VR_API_KEY"),
        ("FT_GUEST_SESSION_IP_PER_HOUR", "0", "FT_GUEST_SESSION_IP_PER_HOUR"),
        ("FT_GUEST_SESSION_SITE_PER_HOUR", "many", "FT_GUEST_SESSION_SITE_PER_HOUR"),
    ],
)
def test_public_demo_preflight_rejects_unsafe_or_unusable_values(name, value, expected):
    preflight = _load_module(ROOT / "scripts" / "production_preflight.py", "production_preflight_invalid")
    values = {
        "DOMAIN": "research.example.com",
        "GLM_API_KEY": "live-secret-value",
        "FT_OWNER_PASSWORD_HASH": "scrypt$32768$8$1$c2FsdA$a2V5",
        "FT_PUBLIC_DEMO": "true",
        "FT_AUTH_SECURE_COOKIE": "true",
        "FT_ALLOWED_ORIGINS": "https://research.example.com",
        "VR_ALLOW_ORIGINS": "https://research.example.com",
        "VR_DATA_DIR": "/data",
        "VR_API_KEY": "",
        "FT_GUEST_SESSION_IP_PER_HOUR": "20",
        "FT_GUEST_SESSION_SITE_PER_HOUR": "200",
    }
    values[name] = value

    errors = preflight.validate(values)

    assert any(expected in error for error in errors)


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker compose is unavailable")
def test_lighthouse_compose_has_one_private_app_and_https_proxy():
    compose_file = DEPLOY_ROOT / "compose.yaml"
    env_file = DEPLOY_ROOT / ".env.example"
    assert compose_file.is_file(), "missing Tencent Lighthouse compose file"
    assert env_file.is_file(), "missing Tencent Lighthouse environment template"

    result = subprocess.run(
        ["docker", "compose", "--env-file", str(env_file), "-f", str(compose_file), "config", "--format", "json"],
        cwd=DEPLOY_ROOT,
        capture_output=True,
        check=False,
    )

    stderr = result.stderr.decode("utf-8", errors="replace")
    assert result.returncode == 0, stderr
    config = json.loads(result.stdout.decode("utf-8"))
    app = config["services"]["ft-research"]
    proxy = config["services"]["caddy"]
    assert not app.get("ports"), "FastAPI must not be published directly"
    assert app["expose"] == ["8000"]
    assert "--proxy-headers" in app["command"]
    assert "--forwarded-allow-ips=*" in app["command"]
    assert {item["published"] for item in proxy["ports"]} == {"80", "443"}
    assert any(item["target"] == "/data" for item in app["volumes"])
    assert app["logging"]["options"] == {"max-file": "3", "max-size": "10m"}
    assert proxy["logging"]["options"] == {"max-file": "3", "max-size": "10m"}


def test_lighthouse_update_plan_fast_forwards_before_redeploying():
    ops = _load_module(ROOT / "scripts" / "lighthouse_ops.py", "lighthouse_ops_update")

    commands = ops.command_plan("update", DEPLOY_ROOT, timestamp="20260905-120000")

    assert commands == [
        ["git", "-C", str(ROOT), "pull", "--ff-only", "origin", "main"],
        ["docker", "compose", "--env-file", str(DEPLOY_ROOT / ".env"), "-f", str(DEPLOY_ROOT / "compose.yaml"), "config", "--quiet"],
        ["docker", "compose", "--env-file", str(DEPLOY_ROOT / ".env"), "-f", str(DEPLOY_ROOT / "compose.yaml"), "up", "-d", "--build", "--wait", "--wait-timeout", "180"],
    ]


def test_lighthouse_runner_removes_values_that_could_override_checked_env_file():
    ops = _load_module(ROOT / "scripts" / "lighthouse_ops.py", "lighthouse_ops_environment")
    seen = []

    def runner(command, *, check, env):
        seen.append((command, check, env))

    ops.run_commands(
        [["docker", "compose", "config"]],
        protected_names={"DOMAIN", "FT_PUBLIC_DEMO"},
        base_env={
            "PATH": "safe",
            "DOMAIN": "attacker.example",
            "FT_PUBLIC_DEMO": "false",
            "FT_GUEST_SESSION_IP_PER_HOUR": "999",
        },
        runner=runner,
    )

    assert seen == [(["docker", "compose", "config"], True, {"PATH": "safe"})]


def test_lighthouse_update_refuses_non_main_or_dirty_checkout():
    ops = _load_module(ROOT / "scripts" / "lighthouse_ops.py", "lighthouse_ops_checkout")

    class Result:
        def __init__(self, stdout):
            self.stdout = stdout

    outputs = iter((Result("feature\n"), Result("")))
    with pytest.raises(RuntimeError, match="main"):
        ops.assert_clean_main(ROOT, runner=lambda *_args, **_kwargs: next(outputs))

    outputs = iter((Result("main\n"), Result("?? unexpected.txt\n")))
    with pytest.raises(RuntimeError, match="uncommitted"):
        ops.assert_clean_main(ROOT, runner=lambda *_args, **_kwargs: next(outputs))


def test_caddy_starts_with_scoped_short_hsts_policy():
    caddyfile = (DEPLOY_ROOT / "Caddyfile").read_text(encoding="utf-8")

    assert 'Strict-Transport-Security "max-age=86400"' in caddyfile
    assert "includeSubDomains" not in caddyfile
    assert "preload" not in caddyfile


def test_lighthouse_main_protects_every_checked_env_name(monkeypatch, tmp_path):
    ops = _load_module(ROOT / "scripts" / "lighthouse_ops.py", "lighthouse_ops_main")
    deploy_root = tmp_path / "deploy"
    deploy_root.mkdir()
    (deploy_root / ".env").write_text(
        "\n".join([
            "DOMAIN=research.example.com",
            "GLM_API_KEY=live-secret-value",
            "FT_OWNER_PASSWORD_HASH='scrypt$32768$8$1$c2FsdA$a2V5'",
            "FT_PUBLIC_DEMO=true",
            "FT_AUTH_SECURE_COOKIE=true",
            "FT_ALLOWED_ORIGINS=https://research.example.com",
            "VR_ALLOW_ORIGINS=https://research.example.com",
            "VR_DATA_DIR=/data",
            "VR_API_KEY=",
        ]),
        encoding="utf-8",
    )
    captured = {}
    monkeypatch.setattr(ops, "command_plan", lambda *_args, **_kwargs: [["safe-command"]])
    monkeypatch.setattr(ops, "run_commands", lambda commands, *, protected_names: captured.update(commands=commands, names=set(protected_names)))

    assert ops.main(["deploy", "--deploy-root", str(deploy_root)]) == 0
    assert captured["commands"] == [["safe-command"]]
    assert {"DOMAIN", "GLM_API_KEY", "FT_PUBLIC_DEMO", "VR_API_KEY"} <= captured["names"]


def test_lighthouse_backup_plan_creates_unique_owner_backup_inside_data_volume():
    ops = _load_module(ROOT / "scripts" / "lighthouse_ops.py", "lighthouse_ops_backup")

    commands = ops.command_plan("backup", DEPLOY_ROOT, timestamp="20260905-120000")

    compose = ["docker", "compose", "--env-file", str(DEPLOY_ROOT / ".env"), "-f", str(DEPLOY_ROOT / "compose.yaml")]
    assert commands == [
        [
            *compose, "exec", "-T", "ft-research", "python", "scripts/owner_backup.py", "export",
            "--db", "/data/sessions.sqlite3", "--out", "/data/backups/owner-20260905-120000.sqlite3",
        ],
        [
            *compose, "cp", "ft-research:/data/backups/owner-20260905-120000.sqlite3",
            str(DEPLOY_ROOT / "backups" / "owner-20260905-120000.sqlite3"),
        ],
    ]
