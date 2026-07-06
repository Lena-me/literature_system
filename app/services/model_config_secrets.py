from __future__ import annotations

from app.utils.secret_crypto import decrypt_api_key, encrypt_api_key, is_encrypted, mask_api_key


def prepare_config_for_storage(config: dict | None, secret: str) -> dict:
    """写入 DB 前加密 config_json 中的 api_key。"""
    cfg = dict(config or {})
    raw_key = cfg.get('api_key')
    if raw_key is None or raw_key == '':
        cfg.pop('api_key', None)
        return cfg
    if is_encrypted(str(raw_key)):
        return cfg
    cfg['api_key'] = encrypt_api_key(str(raw_key).strip(), secret)
    return cfg


def merge_config_for_update(old_config: dict, incoming: dict | None, secret: str) -> dict:
    """更新时合并 config；api_key 留空则保留原密文。"""
    old = dict(old_config or {})
    inc = dict(incoming or {})
    new_key = inc.get('api_key')
    if new_key is None or str(new_key).strip() == '':
        inc.pop('api_key', None)
    merged = {**old, **inc}
    if 'api_key' in inc and inc['api_key']:
        merged['api_key'] = encrypt_api_key(str(inc['api_key']).strip(), secret)
    elif 'api_key' not in inc and old.get('api_key'):
        merged['api_key'] = old['api_key']
    return merged


def sanitize_config_for_response(config: dict | None, secret: str) -> dict:
    """API 响应脱敏：不返回明文或密文 api_key。"""
    cfg = dict(config or {})
    stored = cfg.pop('api_key', None)
    if stored:
        try:
            plain = decrypt_api_key(str(stored), secret) if secret else str(stored)
            if is_encrypted(str(stored)) and not secret:
                cfg['api_key_masked'] = '(已加密，未配置解密密钥)'
            else:
                cfg['api_key_masked'] = mask_api_key(plain)
            cfg['has_api_key'] = True
        except Exception:
            cfg['api_key_masked'] = '(解密失败)'
            cfg['has_api_key'] = True
    else:
        cfg['has_api_key'] = False
    return cfg


def resolve_api_key_from_config(config: dict | None, secret: str) -> str:
    """运行时从 config_json 解密 api_key。"""
    cfg = config or {}
    stored = cfg.get('api_key')
    if stored:
        return decrypt_api_key(str(stored), secret).strip()
    return ''
