#!/usr/bin/env python3
"""Small, auditable deploy/update/backup runner for Tencent Lighthouse."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from production_preflight import load_env, validate  # noqa: E402


PROTECTED_ENV_NAMES = {
    "DOMAIN",
    "GLM_BASE_URL",
    "GLM_MODEL",
    "GLM_API_KEY",
    "FT_OWNER_PASSWORD_HASH",
    "FT_PUBLIC_DEMO",
    "FT_AUTH_SECURE_COOKIE",
    "FT_ALLOWED_ORIGINS",
    "VR_ALLOW_ORIGINS",
    "VR_API_KEY",
    "VR_DATA_DIR",
    "FT_GUEST_DAILY_CALLS",
    "FT_IP_DAILY_CALLS",
    "FT_SITE_DAILY_CALLS",
    "FT_GUEST_SESSION_IP_PER_HOUR",
    "FT_GUEST_SESSION_SITE_PER_HOUR",
}


def command_plan(action: str, deploy_root: Path, *, timestamp: str | None = None) -> list[list[str]]:
    deploy_root = deploy_root.resolve()
    repo_root = deploy_root.parents[1]
    compose = [
        "docker", "compose", "--env-file", str(deploy_root / ".env"),
        "-f", str(deploy_root / "compose.yaml"),
    ]
    deploy = [
        [*compose, "config", "--quiet"],
        [*compose, "up", "-d", "--build", "--wait", "--wait-timeout", "180"],
    ]
    if action == "deploy":
        return deploy
    if action == "update":
        return [["git", "-C", str(repo_root), "pull", "--ff-only", "origin", "main"], *deploy]
    if action == "backup":
        stamp = timestamp or datetime.now().strftime("%Y%m%d-%H%M%S")
        name = f"owner-{stamp}.sqlite3"
        return [
            [
                *compose, "exec", "-T", "ft-research", "python", "scripts/owner_backup.py", "export",
                "--db", "/data/sessions.sqlite3", "--out", f"/data/backups/{name}",
            ],
            [*compose, "cp", f"ft-research:/data/backups/{name}", str(deploy_root / "backups" / name)],
        ]
    raise ValueError(f"unknown action: {action}")


def run_commands(commands, *, protected_names, base_env=None, runner=subprocess.run) -> None:
    environment = dict(os.environ if base_env is None else base_env)
    for name in PROTECTED_ENV_NAMES | set(protected_names):
        environment.pop(name, None)
    for command in commands:
        runner(command, check=True, env=environment)


def assert_clean_main(repo_root: Path, *, runner=subprocess.run) -> None:
    branch = runner(
        ["git", "-C", str(repo_root), "branch", "--show-current"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if branch != "main":
        raise RuntimeError(f"server checkout must be on main, found {branch or 'detached HEAD'}")
    status = runner(
        ["git", "-C", str(repo_root), "status", "--porcelain", "--untracked-files=all"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if status:
        raise RuntimeError("server checkout has uncommitted or untracked files; review them before updating")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("deploy", "update", "backup"))
    parser.add_argument(
        "--deploy-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "deploy" / "tencent-lighthouse",
    )
    args = parser.parse_args(argv)
    env_file = args.deploy_root / ".env"
    if not env_file.is_file():
        print(f"environment file not found: {env_file}", file=sys.stderr)
        return 2
    values = load_env(env_file)
    errors = validate(values)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if args.action == "update":
        try:
            assert_clean_main(args.deploy_root.resolve().parents[1])
        except (OSError, subprocess.CalledProcessError, RuntimeError) as exc:
            print(f"operation failed: {exc}", file=sys.stderr)
            return 1
    if args.action == "backup":
        (args.deploy_root / "backups").mkdir(parents=True, exist_ok=True)
    try:
        run_commands(command_plan(args.action, args.deploy_root), protected_names=values.keys())
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"operation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
