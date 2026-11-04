"""数据存储层：多用户信息与作文历史的持久化。

支持两种后端（通过环境变量 DB_BACKEND 选择）：
  - sqlite（默认）：本地 SQLite，开箱即用，适合本地开发与演示；
  - supabase：部署到 Vercel 时使用，数据存到 Supabase（Postgres），
    需配置 SUPABASE_URL 与 SUPABASE_SERVICE_ROLE_KEY 并执行 supabase/schema.sql。

两种后端对外提供统一的接口（get_storage() 返回）。
"""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

DB_BACKEND = os.getenv("DB_BACKEND", "sqlite").strip().lower()
DB_PATH = os.getenv("DB_PATH", "data/app.db")
SESSION_TTL_HOURS = int(os.getenv("SESSION_TTL_HOURS", "72"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _expiry() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)).isoformat()


class SQLiteStorage:
    """本地 SQLite 后端。"""

    def __init__(self, path: str) -> None:
        import pathlib

        pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init()

    def _init(self) -> None:
        with self._lock, self.conn:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS essays (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    topic TEXT NOT NULL,
                    style TEXT,
                    title TEXT,
                    content TEXT,
                    char_count INTEGER,
                    created_at TEXT NOT NULL
                );
                """
            )

    # ---- 用户 ----
    def create_user(self, username: str, password_hash: str):
        try:
            with self._lock, self.conn:
                cur = self.conn.execute(
                    "INSERT INTO users(username, password_hash, created_at) VALUES(?,?,?)",
                    (username, password_hash, _now()),
                )
                uid = cur.lastrowid
        except sqlite3.IntegrityError:
            return None  # 用户名已存在
        return self.get_user_by_id(uid)

    def get_user_by_username(self, username: str):
        row = self.conn.execute(
            "SELECT * FROM users WHERE username=?", (username,)
        ).fetchone()
        return self._to_user(row)

    def get_user_by_id(self, user_id):
        row = self.conn.execute(
            "SELECT * FROM users WHERE id=?", (int(user_id),)
        ).fetchone()
        return self._to_user(row)

    @staticmethod
    def _to_user(row):
        if not row:
            return None
        return {"id": str(row["id"]), "username": row["username"],
                "password_hash": row["password_hash"], "created_at": row["created_at"]}

    # ---- 会话 ----
    def create_session(self, user_id, token: str) -> None:
        with self._lock, self.conn:
            self.conn.execute(
                "INSERT INTO sessions(token, user_id, created_at, expires_at) VALUES(?,?,?,?)",
                (token, int(user_id), _now(), _expiry()),
            )

    def get_user_by_token(self, token: str):
        row = self.conn.execute(
            "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id "
            "WHERE s.token=? AND s.expires_at>?",
            (token, _now()),
        ).fetchone()
        return self._to_user(row)

    def delete_session(self, token: str) -> None:
        with self._lock, self.conn:
            self.conn.execute("DELETE FROM sessions WHERE token=?", (token,))

    # ---- 作文 ----
    def save_essay(self, user_id, topic, style, title, content, char_count):
        with self._lock, self.conn:
            cur = self.conn.execute(
                "INSERT INTO essays(user_id, topic, style, title, content, char_count, created_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (int(user_id), topic, style, title, content, char_count, _now()),
            )
            eid = cur.lastrowid
        return self.get_essay(eid, user_id)

    def list_essays(self, user_id):
        rows = self.conn.execute(
            "SELECT id, topic, style, title, char_count, created_at FROM essays "
            "WHERE user_id=? ORDER BY id DESC",
            (int(user_id),),
        ).fetchall()
        return [
            {"id": str(r["id"]), "topic": r["topic"], "style": r["style"],
             "title": r["title"], "char_count": r["char_count"], "created_at": r["created_at"]}
            for r in rows
        ]

    def get_essay(self, essay_id, user_id):
        row = self.conn.execute(
            "SELECT * FROM essays WHERE id=? AND user_id=?",
            (int(essay_id), int(user_id)),
        ).fetchone()
        if not row:
            return None
        return {"id": str(row["id"]), "topic": row["topic"], "style": row["style"],
                "title": row["title"], "content": row["content"],
                "char_count": row["char_count"], "created_at": row["created_at"]}

    def delete_essay(self, essay_id, user_id) -> bool:
        with self._lock, self.conn:
            cur = self.conn.execute(
                "DELETE FROM essays WHERE id=? AND user_id=?",
                (int(essay_id), int(user_id)),
            )
        return cur.rowcount > 0


class SupabaseStorage:
    """Supabase（Postgres）后端，用于 Vercel 部署。"""

    def __init__(self, url: str, service_key: str) -> None:
        try:
            from supabase import create_client
        except ImportError as exc:
            raise RuntimeError(
                "使用 supabase 后端需要安装依赖：pip install supabase"
            ) from exc
        self.client = create_client(url, service_key)

    def create_user(self, username, password_hash):
        try:
            data = self.client.table("users").insert({
                "username": username, "password_hash": password_hash, "created_at": _now()
            }).execute().data
            return data[0] if data else None
        except Exception:  # noqa: BLE001 - 唯一约束冲突即视为已存在
            return None

    def get_user_by_username(self, username):
        data = self.client.table("users").select("*").eq("username", username).execute().data
        return data[0] if data else None

    def get_user_by_id(self, user_id):
        data = self.client.table("users").select("*").eq("id", user_id).execute().data
        return data[0] if data else None

    def create_session(self, user_id, token):
        self.client.table("sessions").insert({
            "token": token, "user_id": user_id, "created_at": _now(), "expires_at": _expiry()
        }).execute()

    def get_user_by_token(self, token):
        data = self.client.table("sessions").select("users(*)") \
            .eq("token", token).gt("expires_at", _now()).execute().data
        if not data:
            return None
        return data[0].get("users")

    def delete_session(self, token):
        self.client.table("sessions").delete().eq("token", token).execute()

    def save_essay(self, user_id, topic, style, title, content, char_count):
        data = self.client.table("essays").insert({
            "user_id": user_id, "topic": topic, "style": style, "title": title,
            "content": content, "char_count": char_count, "created_at": _now()
        }).execute().data
        return data[0] if data else None

    def list_essays(self, user_id):
        return self.client.table("essays") \
            .select("id, topic, style, title, char_count, created_at") \
            .eq("user_id", user_id).order("created_at", desc=True).execute().data

    def get_essay(self, essay_id, user_id):
        data = self.client.table("essays").select("*") \
            .eq("id", essay_id).eq("user_id", user_id).execute().data
        return data[0] if data else None

    def delete_essay(self, essay_id, user_id) -> bool:
        data = self.client.table("essays").delete() \
            .eq("id", essay_id).eq("user_id", user_id).execute().data
        return bool(data)


_storage = None


def get_storage():
    """根据环境变量返回存储后端单例（懒加载）。"""
    global _storage
    if _storage is None:
        if DB_BACKEND == "supabase":
            url = os.getenv("SUPABASE_URL", "").strip()
            key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
            if not url or not key:
                raise RuntimeError(
                    "DB_BACKEND=supabase 时需配置 SUPABASE_URL 与 SUPABASE_SERVICE_ROLE_KEY"
                )
            _storage = SupabaseStorage(url, key)
        else:
            _storage = SQLiteStorage(DB_PATH)
    return _storage
