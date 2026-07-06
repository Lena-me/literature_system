from __future__ import annotations

import json
import logging

import httpx

from app.integrations.llm.runtime_config import LLMRuntimeConfig, get_llm_runtime_config

logger = logging.getLogger(__name__)

# Windows 下 httpx 默认会读取系统代理，常导致 ConnectError；LLM 直连更稳定。
_HTTPX_CLIENT_KW = {'timeout': 180, 'trust_env': False}


def _headers(cfg: LLMRuntimeConfig) -> dict:
    h = {'Content-Type': 'application/json'}
    if cfg.api_key:
        h['Authorization'] = f'Bearer {cfg.api_key}'
    return h


def _build_payload(
    cfg: LLMRuntimeConfig,
    messages: list[dict],
    *,
    temperature: float | None,
    max_tokens: int | None,
    stream: bool = False,
) -> dict:
    payload = {
        'model': cfg.model_name,
        'messages': messages,
        'temperature': cfg.temperature if temperature is None else temperature,
        'max_tokens': cfg.max_tokens if max_tokens is None else max_tokens,
    }
    if stream:
        payload['stream'] = True
    return payload


def validate_llm_runtime_config(cfg: LLMRuntimeConfig) -> None:
    if not cfg.base_url:
        raise RuntimeError('LLM 未配置调用地址：请在 .env 设置 LLM_BASE_URL，或在后台模型配置中填写 api_endpoint')
    if not cfg.model_name:
        raise RuntimeError('LLM 未配置模型名：请在 .env 设置 LLM_MODEL，或在后台模型配置中填写 model_name')
    if not cfg.api_key:
        raise RuntimeError('LLM 未配置 API Key：请在 .env 设置 LLM_API_KEY')


async def _read_error_body(response: httpx.Response) -> str:
    try:
        text = (await response.aread()).decode('utf-8', errors='replace').strip()
        return text[:800] if text else ''
    except Exception:
        return ''


def _format_http_error(status_code: int, body: str, cfg: LLMRuntimeConfig) -> str:
    hint = ''
    if status_code == 401:
        hint = '请检查 LLM_API_KEY 是否与当前 base_url 匹配（换代理/换平台后 Key 也要一起换）。'
    elif status_code == 404:
        hint = '请检查 LLM_BASE_URL 是否为 OpenAI 兼容根路径，例如 https://xiaoai.plus/v1（不要重复 /chat/completions）。'
    detail = body or '(无响应体)'
    return (
        f'LLM API 返回 {status_code}：{detail} '
        f'[model={cfg.model_name}, base_url={cfg.base_url}, source={cfg.source}]'
        + (f' {hint}' if hint else '')
    )


def _format_request_error(exc: httpx.RequestError, cfg: LLMRuntimeConfig, url: str) -> str:
    detail = str(exc).strip() or exc.__class__.__name__
    return (
        f'LLM API 网络请求失败：{detail} '
        f'[url={url}, model={cfg.model_name}, base_url={cfg.base_url}, source={cfg.source}]。'
        '若刚修改 .env，请重启后端；若后台启用了 LLM 配置，其 api_endpoint 会覆盖 .env 的 LLM_BASE_URL。'
    )


class OpenAICompatibleLLM:
    def _resolve(self) -> LLMRuntimeConfig:
        cfg = get_llm_runtime_config()
        validate_llm_runtime_config(cfg)
        return cfg

    def chat(self, messages: list[dict], temperature: float | None = None, max_tokens: int | None = None) -> str:
        cfg = self._resolve()
        url = f"{cfg.base_url.rstrip('/')}/chat/completions"
        payload = _build_payload(cfg, messages, temperature=temperature, max_tokens=max_tokens)
        logger.debug('LLM chat model=%s source=%s url=%s', cfg.model_name, cfg.source, cfg.base_url)
        with httpx.Client(**_HTTPX_CLIENT_KW) as client:
            response = client.post(url, headers=_headers(cfg), json=payload)
            if response.status_code >= 400:
                raise RuntimeError(_format_http_error(response.status_code, response.text[:800], cfg))
            data = response.json()
            return self._extract_content(data)

    def _extract_content(self, data: dict, *, content_only: bool = False) -> str:
        msg = data.get('choices', [{}])[0].get('message', {})
        content = (msg.get('content') or '').strip()
        if content:
            return content
        if content_only:
            reasoning = (msg.get('reasoning_content') or '').strip()
            if not reasoning:
                return ''
            lines = [ln.strip() for ln in reasoning.splitlines() if ln.strip()]
            for candidate in reversed(lines):
                if 2 <= len(candidate) <= 20:
                    return candidate
            return ''
        reasoning = msg.get('reasoning_content') or ''
        if reasoning:
            return reasoning
        return ''

    async def async_chat(
        self,
        messages: list[dict],
        temperature: float | None = None,
        max_tokens: int | None = None,
        *,
        content_only: bool = False,
    ) -> str:
        cfg = self._resolve()
        url = f"{cfg.base_url.rstrip('/')}/chat/completions"
        payload = _build_payload(cfg, messages, temperature=temperature, max_tokens=max_tokens)
        logger.debug('LLM async_chat model=%s source=%s url=%s', cfg.model_name, cfg.source, cfg.base_url)
        try:
            async with httpx.AsyncClient(**_HTTPX_CLIENT_KW) as client:
                response = await client.post(url, headers=_headers(cfg), json=payload)
                if response.status_code >= 400:
                    raise RuntimeError(_format_http_error(response.status_code, response.text[:800], cfg))
                data = response.json()
                return self._extract_content(data, content_only=content_only)
        except httpx.RequestError as exc:
            raise RuntimeError(_format_request_error(exc, cfg, url)) from exc

    async def stream_chat(self, messages: list[dict], temperature: float | None = None, max_tokens: int | None = None):
        cfg = self._resolve()
        url = f"{cfg.base_url.rstrip('/')}/chat/completions"
        payload = _build_payload(cfg, messages, temperature=temperature, max_tokens=max_tokens, stream=True)
        logger.debug('LLM stream_chat model=%s source=%s url=%s', cfg.model_name, cfg.source, cfg.base_url)
        async with httpx.AsyncClient(**_HTTPX_CLIENT_KW) as client:
            try:
                async with client.stream('POST', url, headers=_headers(cfg), json=payload) as response:
                    if response.status_code >= 400:
                        body = await _read_error_body(response)
                        raise RuntimeError(_format_http_error(response.status_code, body, cfg))
                    async for line in response.aiter_lines():
                        if not line or not line.startswith('data:'):
                            continue
                        data = line.removeprefix('data:').strip()
                        if data == '[DONE]':
                            break
                        try:
                            obj = json.loads(data)
                            delta = obj['choices'][0].get('delta') or {}
                            reasoning = delta.get('reasoning_content') or ''
                            content = delta.get('content') or ''
                            if reasoning:
                                yield ('reasoning', reasoning)
                            if content:
                                yield ('content', content)
                        except Exception:
                            continue
            except httpx.HTTPStatusError as exc:
                body = ''
                if exc.response is not None:
                    try:
                        body = exc.response.text[:800]
                    except Exception:
                        pass
                raise RuntimeError(
                    _format_http_error(exc.response.status_code if exc.response else 0, body, cfg)
                ) from exc
            except httpx.RequestError as exc:
                raise RuntimeError(_format_request_error(exc, cfg, url)) from exc
