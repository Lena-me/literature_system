from __future__ import annotations

import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ENC_PREFIX = 'enc:v1:'


def _derive_key(secret: str) -> bytes:
    return hashlib.sha256(secret.encode('utf-8')).digest()


def is_encrypted(value: str) -> bool:
    return bool(value) and value.startswith(ENC_PREFIX)


def encrypt_api_key(plain: str, secret: str) -> str:
    if not plain:
        return ''
    if is_encrypted(plain):
        return plain
    if not secret:
        raise RuntimeError('未配置 MODEL_CONFIG_SECRET_KEY，无法加密 API Key')
    key = _derive_key(secret)
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(nonce, plain.encode('utf-8'), None)
    blob = base64.urlsafe_b64encode(nonce + ciphertext).decode('ascii')
    return f'{ENC_PREFIX}{blob}'


def decrypt_api_key(stored: str, secret: str) -> str:
    if not stored:
        return ''
    if not is_encrypted(stored):
        return stored
    if not secret:
        raise RuntimeError('未配置 MODEL_CONFIG_SECRET_KEY，无法解密 API Key')
    raw = base64.urlsafe_b64decode(stored[len(ENC_PREFIX) :].encode('ascii'))
    nonce, ciphertext = raw[:12], raw[12:]
    key = _derive_key(secret)
    return AESGCM(key).decrypt(nonce, ciphertext, None).decode('utf-8')


def mask_api_key(key: str) -> str:
    if not key:
        return ''
    if len(key) <= 8:
        return '****'
    return f'{key[:4]}****{key[-4:]}'
