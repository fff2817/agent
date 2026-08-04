"""
图片解析器 — 通过视觉 LLM 提取文字与画面描述，供 RAG 入库。

支持扩展名: .png / .jpg / .jpeg / .webp / .gif
不引入 OCR 本地依赖，复用现有 OpenAI 兼容 API（智谱需配置支持视觉的模型）。
"""

from __future__ import annotations

import base64
import logging
import mimetypes
from pathlib import Path

from core.config import get_settings
from core.llm import get_openai_client
from file_parser.parser import BaseFileParser, ParseResult, normalize_whitespace

logger = logging.getLogger(__name__)

_IMAGE_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

_MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB

_EXTRACT_PROMPT = (
    "请仔细阅读这张图片，完成以下任务并用中文输出：\n"
    "1. 提取图中所有可见文字（OCR），尽量保留原有顺序与结构；\n"
    "2. 若文字很少或没有，请用一段话描述图片的主要内容、物体、场景与关键信息；\n"
    "3. 不要输出与图片无关的寒暄。\n"
    "直接输出可检索的纯文本内容即可。"
)


class ImageParser(BaseFileParser):
    """用视觉模型将图片转为可入库文本。"""

    supported_extensions = frozenset(_IMAGE_MIME.keys())
    file_type = "image"

    def parse(self, path: str | Path) -> ParseResult:
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"图片不存在: {file_path}")

        suffix = file_path.suffix.lower()
        if suffix not in _IMAGE_MIME:
            raise ValueError(f"不支持的图片类型: {suffix}")

        size = file_path.stat().st_size
        if size > _MAX_IMAGE_BYTES:
            raise ValueError(
                f"图片过大（{size // (1024 * 1024)}MB），请压缩到 10MB 以内再上传"
            )
        if size == 0:
            raise ValueError(f"图片为空: {file_path.name}")

        settings = get_settings()
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is not configured")

        vision_model = (settings.openai_vision_model or settings.openai_model).strip()
        mime = _IMAGE_MIME[suffix] or mimetypes.guess_type(file_path.name)[0] or "image/png"
        b64 = base64.b64encode(file_path.read_bytes()).decode("ascii")
        data_url = f"data:{mime};base64,{b64}"

        logger.info(
            "[ImageParser] 视觉解析: file=%s model=%s size=%d",
            file_path.name,
            vision_model,
            size,
        )

        client = get_openai_client()
        try:
            response = client.chat.completions.create(
                model=vision_model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": _EXTRACT_PROMPT},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    }
                ],
                temperature=0.2,
            )
        except Exception as exc:
            logger.exception("[ImageParser] 视觉模型调用失败")
            raise ValueError(
                f"图片解析失败（请确认模型支持视觉，当前: {vision_model}）: {exc}"
            ) from exc

        content = (response.choices[0].message.content or "").strip()
        if not content:
            raise ValueError(f"未能从图片中提取内容: {file_path.name}")

        text = normalize_whitespace(content)
        logger.info("[ImageParser] 完成: %s, text_len=%d", file_path.name, len(text))
        return self.build_result(file_path, text)
