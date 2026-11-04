"""密码哈希与登录令牌工具（仅用标准库，避免额外依赖）。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

_ITERATIONS = 120_000


def hash_password(password: str) -> str:
    """使用 PBKDF2-HMAC-SHA256 对密码加盐哈希，返回可安全存储的字符串。"""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return base64.b64encode(salt + dk).decode("ascii")


def verify_password(password: str, stored: str) -> bool:
    """校验密码是否与存储的哈希一致（常数时间比较）。"""
    try:
        raw = base64.b64decode(stored)
        salt, dk = raw[:16], raw[16:]
        check = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
        return hmac.compare_digest(check, dk)
    except Exception:  # noqa: BLE001 - 任何解码失败都视为不匹配
        return False


def new_token() -> str:
    """生成随机会话令牌。"""
    return secrets.token_hex(32)
