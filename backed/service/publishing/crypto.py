# -*- coding: utf-8 -*-
"""敏感字段加密：Webhook secret / API Token 等平台凭证落库前 Fernet 加密。

密钥管理策略：
  - 主密钥落在 backed/data/.fernet_key（权限 600），首运行时自动生成。
  - 环境变量 FERNET_KEY 可覆盖（CI/Docker 注入场景）。
  - 密钥轮换：改密钥后未加密的旧字段在读取时解密失败会返回空串，
    配合业务层的"配置失效 → 提示用户重配"逻辑实现平滑轮换。
"""

import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

ROOT = Path(__file__).resolve().parent.parent
_KEY_FILE = ROOT / "data" / ".fernet_key"

_fernet: Fernet | None = None


def _load_key() -> bytes:
    """读取或生成 Fernet 密钥。优先级：环境变量 > 文件 > 自动生成。"""
    env_key = os.environ.get("FERNET_KEY", "").strip()
    if env_key:
        return env_key.encode("utf-8")

    if _KEY_FILE.exists():
        return _KEY_FILE.read_bytes()

    _KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    _KEY_FILE.write_bytes(key)
    try:
        _KEY_FILE.chmod(0o600)
    except (OSError, AttributeError):
        pass   # Windows 不支持 POSIX chmod
    return key


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_load_key())
    return _fernet


def encrypt(plaintext: str) -> str:
    """加密明文。空串原样返回（避免存一堆空密文干扰判断）。"""
    if not plaintext:
        return ""
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(ciphertext: str) -> str:
    """解密密文。失败返回空串（密钥轮换 / 数据损坏时平滑降级）。"""
    if not ciphertext:
        return ""
    try:
        return _get_fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""
