from functools import lru_cache

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    # 图片解析用视觉模型；为空则回退 openai_model。智谱示例: glm-4v-flash
    openai_vision_model: str = ""
    openai_base_url: str | None = None

    app_name: str = "AI Agent Chat API"
    debug: bool = False

    # 逗号分隔；公网 Demo 建议设为前端域名，开发可留 "*"
    cors_origins: str = "*"

    # 为 true 时由 FastAPI 托管 frontend/dist（单端口 Demo 部署）
    serve_frontend: bool = False

    # Agent 循环最多跑几轮（ReAct: Thought → Action → Observation 每轮算一步）
    max_agent_steps: int = 10

    # RAG 文本切分（字符数，非 token；中文约 1 字 ≈ 1~2 token）
    rag_chunk_size: int = 500
    rag_chunk_overlap: int = 50

    # Embedding 模型（OpenAI: text-embedding-3-small；智谱: embedding-3）
    embedding_model: str = "embedding-3"

    # RAG Chroma 向量库目录（每用户子目录）
    rag_store_path: str = "rag/store"

    # 检索返回 Top-K 条
    retrieval_top_k: int = 3

    # 知识库路由：入库摘要最大字符数
    rag_catalog_summary_max_chars: int = 400
    # 是否启用文档级路由
    rag_route_enabled: bool = True
    # 单次最多检索几个文档
    rag_max_route_docs: int = 2
    # 摘要向量相似度低于此值时 fallback 全库
    rag_route_min_score: float = 0.35
    # post-filter 时向量检索候选放大倍数
    rag_route_expand_factor: int = 5
    # Top-2 分数接近时同时选中的差距阈值
    rag_route_score_delta: float = 0.05

    # Session 短期记忆：注入 Prompt 时保留的「最近完整轮数」（压缩窗口）
    max_session_turns: int = 10
    # SQLite 中最多保留多少轮（>= max_session_turns，用于保留历史）
    session_store_max_turns: int = 100
    # 超出窗口的旧对话是否用 LLM 摘要压缩
    session_summary_enabled: bool = True
    # trim_messages 近似 token 上限（摘要失败时的硬裁剪）
    session_compress_max_tokens: int = 4000

    # Long-term Memory Chroma 目录（与 rag/store 分离）
    memory_store_path: str = "memory/store"

    # 长期记忆检索 Top-K
    memory_top_k: int = 3

    # extractor 启发式打分入库阈值（0~1）
    memory_min_score: float = 0.75

    # 语义去重：同用户相似度超过此值则跳过写入
    memory_dedup_threshold: float = 0.92

    # 检索结果最低加权分数，低于此值的记忆不注入 Prompt
    memory_min_retrieval_score: float = 0.20

    # 多用户鉴权
    auth_secret: str = "change-me-in-production"
    auth_disabled: bool = True
    auth_token_expire_hours: int = 24

    # 持久化路径
    users_db_path: str = "data/users.db"
    sessions_db_path: str = "data/sessions.db"
    conversations_db_path: str = "data/conversations.db"
    eval_db_path: str = "data/evaluations.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()
