"""推荐记录落库加密（OPS-002）。

Fernet 封装：encrypt_json/decrypt_json 用于 RecommendationRecord 的
profile/result 两列（应用层透明加解密，经 TypeDecorator 挂载）。

密钥约定：record_encryption_key 为任意字符串；不是合法 Fernet 密钥时按
sha256 派生（用户无需手工生成 base64 密钥，轮换语义同普通口令）。
为空则明文落库（显式降级，启动时 warning）。
"""

import base64
import hashlib
import json

from cryptography.fernet import Fernet, InvalidToken


def _fernet_from_secret(secret: str) -> Fernet:
    """任意字符串密钥 → 合法 Fernet 密钥（非 base64 输入按 sha256 派生）。"""
    try:
        raw = secret.encode("utf-8")
        # 合法 Fernet key 是 32 字节 url-safe base64；直接校验可用性
        if len(base64.urlsafe_b64decode(secret)) == 32:
            return Fernet(secret)
    except Exception:
        pass
    derived = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(derived)


def encrypt_json(data: dict, secret: str) -> str:
    """序列化并加密 JSON 对象，返回可存入 JSON 列的密文字符串。"""
    f = _fernet_from_secret(secret)
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    return f.encrypt(payload).decode("utf-8")


def decrypt_json(token: str, secret: str) -> dict:
    """解密并反序列化 JSON 对象；密文不合法/密钥不符时抛 InvalidToken。"""
    f = _fernet_from_secret(secret)
    try:
        payload = f.decrypt(token.encode("utf-8"))
    except InvalidToken:
        raise
    return json.loads(payload.decode("utf-8"))
