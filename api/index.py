"""Vercel 部署入口：把 FastAPI 应用暴露为 Vercel Serverless Function。"""

from app.main import app

# Vercel Python Runtime 会自动识别 `app`（ASGI 应用）
