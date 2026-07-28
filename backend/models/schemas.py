from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=4)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class AuthResponse(BaseModel):
    user_id: str
    username: str
    access_token: str
    token_type: str = "bearer"
    api_key: str = Field(..., description="API Key，可用于 X-API-Key 头鉴权")


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User message to send to the LLM")
    session_id: str | None = Field(None, description="Session ID for multi-turn memory; omit to start new")


class ReActStepSchema(BaseModel):
    """单步 ReAct 记录 — 供 API 返回和前端展示 Agent 思考过程。"""

    step: int = Field(..., description="步骤序号，从 1 开始")
    thought: str = Field(..., description="LLM 的思考内容")
    action: str | None = Field(None, description="调用的工具，如 calculator(123 * 456)")
    observation: str | None = Field(None, description="工具返回结果")
    final_answer: str | None = Field(None, description="最终回答（仅最后一步可能有）")


class RetrievedMemorySchema(BaseModel):
    rank: int
    score: float
    content: str
    memory_type: str
    source: str = Field("", description="记忆来源")


class ChatResponse(BaseModel):
    response: str = Field(..., description="Assistant reply from the Agent")
    session_id: str = Field(..., description="Session ID — save on client for next request")
    user_id: str = Field(..., description="Current user ID")
    steps: list[ReActStepSchema] = Field(
        default_factory=list,
        description="ReAct 步骤链：Thought → Action → Observation → Final Answer",
    )
    memories_used: list[str] = Field(
        default_factory=list,
        description="本轮注入 Prompt 的长期记忆片段（兼容旧字段）",
    )
    retrieved_memories: list[RetrievedMemorySchema] = Field(
        default_factory=list,
        description="本轮 FAISS 检索命中的长期记忆详情",
    )
    memory_retrieval_skipped: bool = Field(
        False,
        description="True 表示本轮未执行长期记忆检索",
    )
    memory_skip_reason: str = Field(
        "",
        description="跳过长期记忆检索的原因",
    )


class RAGAskRequest(BaseModel):
    question: str = Field(..., min_length=1, description="User question for document QA")
    session_id: str | None = Field(None, description="Session ID for multi-turn memory")
    top_k: int | None = Field(None, ge=1, le=20, description="Number of chunks to retrieve")
    evaluate: bool = Field(True, description="Run RAG quality evaluation after answer")


class RAGSourceSchema(BaseModel):
    rank: int
    score: float
    source: str
    page: int
    text: str
    relevance_score: float | None = Field(None, description="Evaluated relevance score")
    relevance_label: str | None = Field(None, description="high | medium | low | irrelevant")


class RetrievalItemEvalSchema(BaseModel):
    rank: int
    faiss_id: int
    vector_score: float
    relevance_score: float
    relevance_label: str
    source: str = ""
    page: int = 0
    text_preview: str = ""
    reason: str = ""


class RetrievalEvalSchema(BaseModel):
    top_k: int
    items: list[RetrievalItemEvalSchema] = Field(default_factory=list)
    avg_vector_score: float = 0.0
    avg_relevance_score: float = 0.0
    context_precision: float = 0.0
    hit_quality: str = "poor"


class AnswerEvalSchema(BaseModel):
    faithfulness: float = 0.0
    answer_relevance: float = 0.0
    completeness: float = 0.0
    overall_score: float = 0.0
    verdict: str = "acceptable"
    issues: list[str] = Field(default_factory=list)
    judge_model: str = ""


class CitationItemSchema(BaseModel):
    rank: int
    cited: bool
    source: str = ""
    page: int = 0
    excerpt: str = ""


class CitationEvalSchema(BaseModel):
    cited_source_ranks: list[int] = Field(default_factory=list)
    items: list[CitationItemSchema] = Field(default_factory=list)
    citation_coverage: float = 0.0


class RAGEvaluationSummarySchema(BaseModel):
    evaluation_id: str
    retrieval: RetrievalEvalSchema
    answer: AnswerEvalSchema
    citation: CitationEvalSchema
    latency_ms: dict[str, int] = Field(default_factory=dict)


class RAGEvaluationListItemSchema(BaseModel):
    id: str
    question: str
    answer: str
    overall_score: float
    hit_quality: str
    pipeline: str
    session_id: str | None = None
    created_at: str


class RAGEvaluationStatsSchema(BaseModel):
    total: int
    avg_overall_score: float
    low_score_rate: float
    poor_retrieval_rate: float


class RAGEvaluationDetailSchema(BaseModel):
    id: str
    created_at: str
    user_id: str
    session_id: str | None = None
    pipeline: str
    question: str
    answer: str
    top_k: int
    model: str
    embedding_model: str
    sources: list[RAGSourceSchema] = Field(default_factory=list)
    context_preview: str = ""
    retrieval: RetrievalEvalSchema
    answer_eval: AnswerEvalSchema
    citation: CitationEvalSchema
    latency_ms: dict[str, int] = Field(default_factory=dict)
    eval_version: str = "1.0"


class RAGAskResponse(BaseModel):
    question: str
    answer: str
    session_id: str = Field(..., description="Session ID for multi-turn memory")
    user_id: str = Field(..., description="Current user ID")
    sources: list[RAGSourceSchema] = Field(default_factory=list)
    context_preview: str = Field("", description="Preview of context sent to LLM")
    evaluation: RAGEvaluationSummarySchema | None = Field(
        None,
        description="RAG quality evaluation summary when evaluate=true",
    )


class RAGIngestRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Text content to ingest")
    source: str = Field("upload", description="Document source name for citation")


class RAGIngestResponse(BaseModel):
    source: str
    chunks_added: int


class DocumentUploadResponse(BaseModel):
    status: str = Field(..., description="Upload status, e.g. ok")
    doc_id: str = Field(..., description="Logical document ID for routing")
    filename: str = Field(..., description="Saved document filename")
    file_type: str = Field(..., description="Document type: pdf, docx, txt, markdown")
    chunks_added: int = Field(..., description="Number of chunks added in this upload")
    total_chunks: int = Field(..., description="Total chunks in the vector store")


class DocumentItemSchema(BaseModel):
    filename: str = Field(..., description="Document filename")
    file_type: str = Field(..., description="Document type: pdf, docx, txt, markdown")
    size: int = Field(..., description="File size in bytes")
    uploaded_at: float = Field(..., description="Last modified timestamp (Unix seconds)")


class DocumentListResponse(BaseModel):
    documents: list[DocumentItemSchema] = Field(default_factory=list)


class LongTermMemoryItemSchema(BaseModel):
    content: str
    memory_type: str
    importance: float = 0.7
    source: str = Field("", description="记忆来源，如 conversation_history")
    created_at: str = ""


class MemoryOverviewResponse(BaseModel):
    user_id: str
    session_id: str
    short_term_memory: list[str] = Field(
        default_factory=list,
        description="当前 session 短期记忆摘要",
    )
    long_term_memory: list[LongTermMemoryItemSchema] = Field(
        default_factory=list,
        description="该用户全部长期记忆",
    )


class MemoryAskRequest(BaseModel):
    question: str = Field(..., min_length=1, description="User question for memory-augmented QA")
    session_id: str | None = Field(None, description="Session ID for multi-turn memory")
    top_k: int | None = Field(None, ge=1, le=20, description="Number of memories to retrieve")


class MemorySourceSchema(BaseModel):
    rank: int
    score: float
    memory_type: str
    content: str


class MemoryAskResponse(BaseModel):
    question: str
    answer: str
    session_id: str
    user_id: str
    should_retrieve: bool = Field(..., description="Whether memory retrieval was attempted")
    skip_reason: str = Field("", description="Reason retrieval was skipped")
    memories: list[MemorySourceSchema] = Field(default_factory=list)
    context_preview: str = Field("", description="Preview of memory context sent to LLM")
