"""
Session Memory 演示 — 验证 10 轮 FIFO 与 messages 拼接。

用法（backend 目录）:
    .venv\\Scripts\\python.exe -m memory.demo_session
"""

import logging

from infra.session_store import SessionStore

logging.basicConfig(level=logging.INFO, format="%(message)s")


def main() -> None:
    print("\n" + "=" * 60)
    print("  Session Memory Demo")
    print("=" * 60)

    store = SessionStore()
    demo_user_id = "demo-user"
    session_id, _ = store.get_or_create(None, demo_user_id)
    print(f"\n  新建 session: {session_id}\n")

    # 模拟 3 轮对话
    dialogs = [
        ("帮我算 123*456", "123 × 456 = 56088"),
        ("再乘以 2", "112176"),
        ("我叫小明", "你好小明！"),
    ]

    for user, assistant in dialogs:
        store.add_turn(session_id, user, assistant)

    print("\n--- get_history_messages (给 LLM 的格式) ---\n")
    for msg in store.get_history_messages(session_id):
        print(f"  [{msg['role']:9}] {msg['content'][:50]}")

    print("\n--- 测试 FIFO: 追加 11 轮，应只保留最近 10 轮 ---\n")
    for i in range(11):
        store.add_turn(session_id, f"问题{i}", f"回答{i}")

    print(f"  当前轮数: {store.get_turn_count(session_id)} (应为 10)")
    first = store.get_history_messages(session_id)[0]["content"]
    print(f"  最早一条 user: {first} (应为 问题1，问题0 已被删除)")

    print("\n" + "=" * 60)
    print("  完成 — 接入点: api/chat.py load history -> run_react_agent")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
