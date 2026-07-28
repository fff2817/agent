#!/usr/bin/env python3
"""创建 Demo 面试账号（幂等）。"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from auth.user_store import get_user_store  # noqa: E402

DEMO_USERNAME = "demo"
DEMO_PASSWORD = "Demo2026!"


def main() -> None:
    store = get_user_store()
    existing = store.get_by_username(DEMO_USERNAME)
    if existing:
        print(f"[seed] Demo 用户已存在: {DEMO_USERNAME}")
        return

    user = store.create_user(DEMO_USERNAME, DEMO_PASSWORD)
    print(f"[seed] 已创建 Demo 用户: {user.username} / {DEMO_PASSWORD}")


if __name__ == "__main__":
    main()
