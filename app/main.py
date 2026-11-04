"""高考满分作文智能应用 —— FastAPI 后端。

功能：
  1. 根据高考作文题目调用大模型生成满分作文（无需登录）；
  2. 多用户信息管理系统：注册/登录/退出，每位用户可保存、查看、删除自己的作文历史。

运行：
    uvicorn app.main:app --reload
"""

from __future__ import annotations

import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.llm import LLMClient
from app.prompt import DEMO_ESSAY
from app.security import hash_password, new_token, verify_password
from app.storage import get_storage

# 加载 .env 环境变量
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="高考满分作文智能应用",
    description="根据高考作文题目调用大模型生成满分作文，支持多用户与作文历史管理。",
    version="2.0.0",
)


class GenerateRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=200, description="作文题目")
    style: str = Field("自动", description="文体：自动/议论文/记叙文/散文")
    word_count: int = Field(800, ge=600, le=1200, description="目标字数")


class AuthRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=100)


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def _public_user(u: dict) -> dict:
    """去除敏感字段（密码哈希），并把 id 统一为字符串。"""
    return {"id": str(u["id"]), "username": u["username"], "created_at": u.get("created_at")}


def _extract_token(authorization: str) -> str:
    if authorization and authorization.startswith("Bearer "):
        return authorization[7:].strip()
    return ""


def _require_user(authorization: str) -> dict:
    """从 Authorization 头解析当前登录用户，未登录/过期则抛 401。"""
    token = _extract_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="未登录")
    user = get_storage().get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    return user


def _parse_content(content: str) -> dict:
    lines = content.splitlines()
    title = lines[0].strip() if lines else ""
    body = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
    if title.startswith("《") and title.endswith("》"):
        title = title[1:-1]
    char_count = len(content.replace("\n", "").replace(" ", ""))
    return {"title": title, "body": body, "char_count": char_count}


def _generate(req: GenerateRequest) -> dict:
    """调用大模型生成作文（未配置 Key 时进入演示模式）。"""
    demo = False
    start = time.time()
    try:
        client = LLMClient()
        content = client.generate_essay(req.topic, req.style, req.word_count)
    except RuntimeError:
        demo = True
        content = DEMO_ESSAY
    except Exception as exc:  # noqa: BLE001 - 统一转为可读的接口错误
        raise HTTPException(status_code=502, detail=f"大模型调用失败：{exc}") from exc

    parsed = _parse_content(content)
    parsed.update(demo=demo, elapsed=round(time.time() - start, 2), full_text=content)
    return parsed


# ---------------------------------------------------------------------------
# 基础接口
# ---------------------------------------------------------------------------
@app.get("/")
def index() -> FileResponse:
    """返回前端首页。"""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict:
    """健康检查。"""
    return {"status": "ok", "time": time.strftime("%Y-%m-%d %H:%M:%S")}


@app.post("/api/generate")
def generate(req: GenerateRequest) -> JSONResponse:
    """生成高考满分作文（无需登录，不保存历史）。"""
    return JSONResponse(_generate(req))


# ---------------------------------------------------------------------------
# 多用户：认证接口
# ---------------------------------------------------------------------------
@app.post("/api/auth/register")
def register(req: AuthRequest) -> JSONResponse:
    """注册新用户并自动登录。"""
    username = req.username.strip()
    if not (3 <= len(username) <= 30):
        raise HTTPException(status_code=400, detail="用户名长度需为 3~30 个字符")
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="密码至少 6 位")

    store = get_storage()
    user = store.create_user(username, hash_password(req.password))
    if user is None:
        raise HTTPException(status_code=409, detail="用户名已存在")

    token = new_token()
    store.create_session(user["id"], token)
    return JSONResponse({"token": token, "user": _public_user(user)})


@app.post("/api/auth/login")
def login(req: AuthRequest) -> JSONResponse:
    """登录。"""
    store = get_storage()
    user = store.get_user_by_username(req.username.strip())
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = new_token()
    store.create_session(user["id"], token)
    return JSONResponse({"token": token, "user": _public_user(user)})


@app.post("/api/auth/logout")
def logout(authorization: str = Header(default="")) -> JSONResponse:
    """退出登录。"""
    token = _extract_token(authorization)
    if token:
        get_storage().delete_session(token)
    return JSONResponse({"ok": True})


@app.get("/api/auth/me")
def me(authorization: str = Header(default="")) -> JSONResponse:
    """获取当前登录用户信息。"""
    return JSONResponse({"user": _public_user(_require_user(authorization))})


# ---------------------------------------------------------------------------
# 多用户：作文历史接口
# ---------------------------------------------------------------------------
@app.post("/api/essays")
def create_essay(req: GenerateRequest, authorization: str = Header(default="")) -> JSONResponse:
    """生成作文并保存到当前用户的历史记录。"""
    user = _require_user(authorization)
    result = _generate(req)
    essay = get_storage().save_essay(
        user["id"], req.topic, req.style, result["title"], result["body"], result["char_count"]
    )
    return JSONResponse({"essay": essay, "demo": result["demo"], "elapsed": result["elapsed"]})


@app.get("/api/essays")
def list_essays(authorization: str = Header(default="")) -> JSONResponse:
    """列出当前用户的作文历史（不含正文）。"""
    user = _require_user(authorization)
    return JSONResponse({"essays": get_storage().list_essays(user["id"])})


@app.get("/api/essays/{essay_id}")
def get_essay(essay_id: str, authorization: str = Header(default="")) -> JSONResponse:
    """查看单篇作文详情。"""
    user = _require_user(authorization)
    essay = get_storage().get_essay(essay_id, user["id"])
    if not essay:
        raise HTTPException(status_code=404, detail="作文不存在")
    return JSONResponse({"essay": essay})


@app.delete("/api/essays/{essay_id}")
def delete_essay(essay_id: str, authorization: str = Header(default="")) -> JSONResponse:
    """删除单篇作文。"""
    user = _require_user(authorization)
    ok = get_storage().delete_essay(essay_id, user["id"])
    if not ok:
        raise HTTPException(status_code=404, detail="作文不存在")
    return JSONResponse({"ok": True})


# 静态资源（css / js）
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
