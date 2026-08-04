"""ConversationStore 单元测试。"""

from __future__ import annotations

from pathlib import Path

from conversation.store import ConversationStore, make_title_from_message


def test_make_title_truncates():
    assert make_title_from_message("  hello   world  ") == "hello world"
    long = "这是一段很长很长的标题" * 5
    title = make_title_from_message(long)
    assert title.endswith("…")
    assert len(title) <= 36


def test_conversation_crud_and_auto_title(tmp_path: Path):
    store = ConversationStore(tmp_path / "conversations.db")
    user = "user-1"
    conv = store.create(user)
    assert conv.title == "新对话"
    assert conv.message_count == 0

    updated = store.append_turn(
        conv.conversation_id,
        user,
        "这是个什么证书？请帮我看看图片内容",
        "这是 Datawhale 证书。",
        assistant_meta={"steps": [{"step": 1}]},
    )
    assert updated.title.startswith("这是个什么证书")
    assert updated.message_count == 2

    detail_msgs = store.list_messages(conv.conversation_id)
    assert [m.role for m in detail_msgs] == ["user", "assistant"]
    assert detail_msgs[1].meta["steps"][0]["step"] == 1

    listed = store.list_for_user(user)
    assert listed[0].conversation_id == conv.conversation_id

    store.rename(conv.conversation_id, user, "证书问答")
    assert store.get(conv.conversation_id).title == "证书问答"

    store.delete(conv.conversation_id, user)
    assert store.get(conv.conversation_id) is None
