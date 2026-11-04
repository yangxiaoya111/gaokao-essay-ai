"""大模型调用封装。

使用 OpenAI SDK 以 OpenAI 兼容协议调用国内外大模型（GLM / Qwen / DeepSeek 等），
也兼容 CC-SWITCH 提供的统一接口。通过环境变量配置：

    LLM_API_KEY    大模型 API 密钥
    LLM_BASE_URL   OpenAI 兼容接口地址
    LLM_MODEL      模型名称
"""

from __future__ import annotations

import os

from openai import OpenAI

from app.prompt import SYSTEM_PROMPT, build_user_prompt


class LLMClient:
    """OpenAI 兼容协议的轻量封装。"""

    def __init__(self) -> None:
        api_key = os.getenv("LLM_API_KEY", "").strip()
        base_url = os.getenv("LLM_BASE_URL", "").strip()
        self.model = os.getenv("LLM_MODEL", "").strip()

        if not api_key:
            raise RuntimeError(
                "未配置 LLM_API_KEY，请在 .env 文件中填写大模型 API 密钥。"
            )
        if not self.model:
            raise RuntimeError("未配置 LLM_MODEL，请在 .env 文件中填写模型名称。")

        # base_url 可为空（使用 OpenAI 官方端点），也可指向任意兼容端点
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = OpenAI(**kwargs)

    def generate_essay(
        self,
        topic: str,
        style: str = "自动",
        word_count: int = 800,
        temperature: float = 0.8,
    ) -> str:
        """生成高考满分作文，返回纯文本（首行为标题，其后为正文）。"""
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(topic, style, word_count)},
        ]
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            timeout=120,
        )
        content = resp.choices[0].message.content or ""
        return content.strip()
