#!/usr/bin/env python3
"""Generate FT_OWNER_PASSWORD_HASH without writing credentials to disk."""

import getpass
import sys

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from auth import hash_password  # noqa: E402


def main() -> int:
    first = getpass.getpass("管理员密码: ")
    second = getpass.getpass("再次输入管理员密码: ")
    if not first or first != second:
        print("密码为空或两次输入不一致", file=sys.stderr)
        return 2
    print(hash_password(first))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
