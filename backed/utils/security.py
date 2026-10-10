"""通用安全工具

提供密码哈希、安全令牌、常量时间比较、限流键生成等。
⚠️ SQL 注入防护应依赖参数化查询（SQLAlchemy/DB-API），本模块不再提供正则检测。
不读项目 config；JWT 装配见 utils.auth，业务 Depends 见 core.permissions。
"""

import hmac
import secrets
from typing import Any

import bcrypt


class SecurityUtil:
    """通用安全工具类（静态方法集合）。"""

    @staticmethod
    def hash_password(password: str) -> str:
        """对密码进行 bcrypt 哈希。"""
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        """校验密码与哈希是否匹配。"""
        try:
            if not password or not hashed:
                return False
            return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
        except Exception:
            return False

    @staticmethod
    def generate_salt() -> str:
        """生成随机盐值（hex）。"""
        return secrets.token_hex(16)

    @staticmethod
    def generate_token(length: int = 32) -> str:
        """生成安全的 URL 安全随机令牌。"""
        return secrets.token_urlsafe(length)

    @staticmethod
    def safe_compare(a: Any, b: Any) -> bool:
        """常量时间比较，降低时序攻击风险。"""
        if type(a) is not type(b):
            return False
        if isinstance(a, str):
            return hmac.compare_digest(a, b)
        return hmac.compare_digest(str(a), str(b))

    @staticmethod
    def generate_rate_limit_key(ip: str, endpoint: str) -> str:
        """生成限流缓存键。"""
        safe_endpoint = endpoint.replace("/", "_").replace(":", "_")
        return f"ratelimit:{ip}:{safe_endpoint}"


# 模块级别名，便于直接 import
get_password_hash = SecurityUtil.hash_password
verify_password = SecurityUtil.verify_password
