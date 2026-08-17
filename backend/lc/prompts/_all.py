"""
统一 Prompt 管理 — 全部经 LangChain ChatPromptTemplate。

职责:
  - 集中存放各链路 Prompt 原文（保持与迁移前一致）
  - 用 ChatPromptTemplate / MessagesPlaceholder 组装 messages
  - 对外仍输出 OpenAI 风格 list[dict]，兼容 core.llm.chat_completion

模块入口:
  - build_react_messages / build_rag_messages / build_memory_messages
  - build_memory_system_section / build_judge_messages
  - IMAGE_EXTRACT_PROMPT
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import BaseMessage, convert_to_openai_messages
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from lc.llm.chat import dict_messages_to_lc

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt 原文（保持原有效果，勿随意改写措辞）
# ---------------------------------------------------------------------------

REACT_SYSTEM_PROMPT = """你是一个 ReAct Agent 学习助手，帮助用户学习知识和解决问题。

## 工作方式（ReAct 循环）

对于每个用户问题，你必须按以下格式思考和行动：

1. **Thought（思考）**：分析用户问题，说明当前情况和下一步计划。
2. **Action（行动）**：调用工具获取信息或执行计算；如果不需要工具，直接给出 Final Answer。
3. 看到 **Observation（工具返回结果）** 后，继续 Thought → Action，直到信息足够。
4. **Final Answer（最终回答）**：信息足够时，用自然语言回答用户。

## 输出格式要求

### 需要调用工具时

在回复的文本部分写 Thought，然后通过工具调用（tool_call）执行 Action：

Thought: [你的分析和计划]
（然后通过 tool_call 调用对应工具）

### 不需要工具，或已收集足够信息时

Thought: [简要说明为什么可以回答了]
Final Answer: [给用户的完整回答]

## 知识库检索（search_docs）

- 当用户询问已上传文档、手册、PDF 中的内容时，使用 search_docs 工具检索。
- 回答必须基于检索到的 Observation，不要编造文档中没有的信息。
- 如果 search_docs 返回「未找到」或「知识库为空」，如实告知用户，并建议上传 PDF。
- 引用文档时尽量说明来源（文件名、页码）。

## 重要规则

- 数学计算必须使用 calculator 工具，不要心算。
- 复杂计算分步进行：先算子表达式，再合并结果。
- 文档类问题优先使用 search_docs，不要凭记忆猜测。
- 每次只调用一个工具，看到 Observation 后再决定下一步。
- Final Answer 必须清晰、完整，面向用户。
- 非计算、非文档类问题，如果不需要工具，可以直接 Thought + Final Answer。

## 示例

用户：123 * 456 等于多少

Thought: 用户需要精确计算 123 * 456，我应使用 calculator 工具。
Action: calculator({"expression": "123 * 456"})
Observation: 56088
Thought: 工具返回 56088，可以回答用户了。
Final Answer: 123 × 456 = 56088

用户：员工手册里报销流程是什么？

Thought: 用户询问文档内容，我需要用 search_docs 检索知识库。
Action: search_docs({"query": "报销流程"})
Observation: [1] 员工手册.pdf p.1 (score=0.892): 员工需填写电子报销申请单...
Thought: 检索结果足够，可以基于文档回答。
Final Answer: 根据员工手册，报销流程是：1. 填写电子报销申请单；2. 附上发票...
"""

RAG_SYSTEM_PROMPT = """你是一个专业的文档问答助手。

请严格根据【检索到的资料】回答用户问题，遵循以下规则：
1. 只使用资料中的信息，不要编造或推测
2. 如果资料中没有相关内容，请明确说「根据现有文档，未找到相关信息」
3. 回答时可自然引用来源（如「根据员工手册第12页…」）
4. 回答要清晰、准确、面向用户
"""

MEMORY_QA_SYSTEM_PROMPT = """你是一个具备长期记忆能力的 AI 助手。

请根据【检索到的用户长期记忆】回答用户问题，遵循以下规则：
1. 优先使用记忆中与用户问题相关的信息
2. 记忆中没有的内容不要编造；可结合通用知识补充，但要区分「已知记忆」与「推测」
3. 自然融入记忆，不要逐条复述「根据记忆1…记忆2…」
4. 若记忆与当前问题无关，可忽略记忆直接回答
"""

MEMORY_AGENT_SECTION_HEADER = (
    "\n\n## 用户长期记忆\n"
    "以下是与该用户相关的已知信息，请在回答中自然运用，不要逐条复述：\n"
)

IMAGE_EXTRACT_PROMPT = (
    "请仔细阅读这张图片，完成以下任务并用中文输出：\n"
    "1. 提取图中所有可见文字（OCR），尽量保留原有顺序与结构；\n"
    "2. 若文字很少或没有，请用一段话描述图片的主要内容、物体、场景与关键信息；\n"
    "3. 不要输出与图片无关的寒暄。\n"
    "直接输出可检索的纯文本内容即可。"
)

JUDGE_SYSTEM_PROMPT = """你是 RAG 质量评估专家。根据用户问题、检索资料和 AI 回答，输出 JSON 评估结果。
只输出 JSON，不要 markdown 代码块。"""

JUDGE_USER_PROMPT = """请评估以下 RAG 问答质量。

【用户问题】
{question}

【检索资料】
{context}

【AI 回答】
{answer}

请输出 JSON，字段如下：
{{
  "retrieval_items": [
    {{"rank": 1, "relevant": true, "score": 0.0-1.0, "reason": "简短说明"}}
  ],
  "faithfulness": 0.0-1.0,
  "answer_relevance": 0.0-1.0,
  "completeness": 0.0-1.0,
  "overall_score": 0.0-1.0,
  "verdict": "good|acceptable|poor",
  "issues": ["问题1", "问题2"]
}}

评分标准：
- faithfulness: 回答是否被资料支撑，有无幻觉
- answer_relevance: 回答是否切题
- completeness: 是否覆盖问题要点
- retrieval_items: 对每条检索片段（按 rank）判断是否真正相关
"""

RAG_USER_PROMPT = """【检索到的资料】
{context}

【用户问题】
{question}"""

MEMORY_QA_USER_PROMPT = """【检索到的用户长期记忆】
{context}

【用户问题】
{question}"""

# ---------------------------------------------------------------------------
# ChatPromptTemplate 定义
# ---------------------------------------------------------------------------

# human 侧统一用 {user_content}，正文在外部用 f-string 拼好，
# 避免检索资料 / 记忆 / 回答中的 { } 被当成模板变量。
REACT_CHAT_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", "{system_content}"),
        MessagesPlaceholder("history", optional=True),
        ("human", "{input}"),
    ]
)

RAG_CHAT_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", "{system_content}"),
        MessagesPlaceholder("history", optional=True),
        ("human", "{user_content}"),
    ]
)

MEMORY_QA_CHAT_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", "{system_content}"),
        MessagesPlaceholder("history", optional=True),
        ("human", "{user_content}"),
    ]
)

JUDGE_CHAT_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", "{system_content}"),
        ("human", "{user_content}"),
    ]
)

IMAGE_EXTRACT_CHAT_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("human", "{prompt}"),
    ]
)


# ---------------------------------------------------------------------------
# 渲染工具
# ---------------------------------------------------------------------------


def _history_to_lc(history: list[dict] | None) -> list[BaseMessage]:
    if not history:
        return []
    return dict_messages_to_lc(history)


def _prompt_needs_history(prompt: ChatPromptTemplate) -> bool:
    """判断模板是否包含 MessagesPlaceholder('history')。"""
    if "history" in getattr(prompt, "input_variables", []):
        return True
    for msg in prompt.messages:
        if getattr(msg, "variable_name", None) == "history":
            return True
    return False


def render_chat_prompt(
    prompt: ChatPromptTemplate,
    *,
    history: list[dict] | None = None,
    **variables: Any,
) -> list[dict]:
    """
    渲染 ChatPromptTemplate → OpenAI messages(list[dict])。
    """
    invoke_vars: dict[str, Any] = dict(variables)
    if _prompt_needs_history(prompt):
        invoke_vars["history"] = _history_to_lc(history)

    result = prompt.invoke(invoke_vars)
    messages = convert_to_openai_messages(result.to_messages())
    return list(messages)


def build_memory_system_section(hints: list[str]) -> str:
    """将长期记忆格式化为可追加到 ReAct system prompt 的段落。"""
    if not hints:
        return ""
    lines = "\n".join(f"- {hint}" for hint in hints)
    return f"{MEMORY_AGENT_SECTION_HEADER}{lines}\n"


def build_react_messages(
    user_message: str,
    *,
    history: list[dict] | None = None,
    memory_hints: list[str] | None = None,
) -> list[dict]:
    """ReAct Agent 初始 messages：system(含可选记忆) + history + user。"""
    system_content = REACT_SYSTEM_PROMPT + build_memory_system_section(
        memory_hints or []
    )
    messages = render_chat_prompt(
        REACT_CHAT_PROMPT,
        history=history,
        system_content=system_content,
        input=user_message,
    )
    logger.info(
        "[Prompts] ReAct messages: history=%d, memory_hints=%d",
        len(history or []),
        len(memory_hints or []),
    )
    return messages


def build_rag_messages(
    question: str,
    context: str,
    *,
    history: list[dict] | None = None,
) -> list[dict]:
    """RAG 问答 messages（context 已由调用方 format_context 拼好）。"""
    # 用 f-string 拼 user，避免资料正文中的 { } 触发 str.format
    user_content = (
        f"【检索到的资料】\n{context}\n\n【用户问题】\n{question}"
    )
    messages = render_chat_prompt(
        RAG_CHAT_PROMPT,
        history=history,
        system_content=RAG_SYSTEM_PROMPT,
        user_content=user_content,
    )
    logger.info(
        "[Prompts] RAG messages: history=%d, context_len=%d",
        len(history or []),
        len(context),
    )
    return messages


def build_memory_messages(
    question: str,
    context: str,
    *,
    history: list[dict] | None = None,
) -> list[dict]:
    """长期记忆独立问答 /memory/ask 的 messages。"""
    user_content = (
        f"【检索到的用户长期记忆】\n{context}\n\n【用户问题】\n{question}"
    )
    messages = render_chat_prompt(
        MEMORY_QA_CHAT_PROMPT,
        history=history,
        system_content=MEMORY_QA_SYSTEM_PROMPT,
        user_content=user_content,
    )
    logger.info(
        "[Prompts] Memory QA messages: history=%d, context_len=%d",
        len(history or []),
        len(context),
    )
    return messages


def build_judge_messages(
    *,
    question: str,
    context: str,
    answer: str,
) -> list[dict]:
    """RAG Eval Judge messages。"""
    # JUDGE_USER_PROMPT 含 JSON 示例的 {{ }}；正文侧尽量避免未转义花括号
    user_content = JUDGE_USER_PROMPT.format(
        question=question,
        context=context,
        answer=answer,
    )
    return render_chat_prompt(
        JUDGE_CHAT_PROMPT,
        system_content=JUDGE_SYSTEM_PROMPT,
        user_content=user_content,
    )


def get_image_extract_prompt() -> str:
    """视觉解析 Prompt 原文（经 ChatPromptTemplate 渲染，效果不变）。"""
    rendered = IMAGE_EXTRACT_CHAT_PROMPT.invoke({"prompt": IMAGE_EXTRACT_PROMPT})
    messages = rendered.to_messages()
    content = messages[0].content if messages else IMAGE_EXTRACT_PROMPT
    return content if isinstance(content, str) else IMAGE_EXTRACT_PROMPT
