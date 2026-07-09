from __future__ import annotations

import json
import logging
import time

import httpx

from app.integrations.llm.runtime_config import LLMRuntimeConfig, get_llm_runtime_config
from app.services.model_call_stats_service import record_llm_call

logger = logging.getLogger(__name__)

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
        payload['stream_options'] = {'include_usage': True}
    if cfg.thinking_enabled:
        payload['thinking'] = {'type': 'enabled'}
        if cfg.reasoning_effort:
            payload['reasoning_effort'] = cfg.reasoning_effort
    return payload


def validate_llm_runtime_config(cfg: LLMRuntimeConfig) -> None:
    if not cfg.base_url:
        raise RuntimeError('LLM 未配置调用地址：请在管理后台模型配置中填写 api_endpoint')
    if not cfg.model_name:
        raise RuntimeError('LLM 未配置模型名：请在管理后台模型配置中填写 model_name')
    if not cfg.api_key:
        raise RuntimeError('LLM 未配置 API Key：请在管理后台模型配置中填写 api_key')


def _extract_usage_tokens(data: dict) -> int:
    usage = data.get('usage') or {}
    total = usage.get('total_tokens')
    if total is not None:
        return max(int(total), 0)
    prompt = int(usage.get('prompt_tokens') or 0)
    completion = int(usage.get('completion_tokens') or 0)
    return prompt + completion


def _estimate_tokens(text: str) -> int:
    return max(len(text) // 4, 1) if text else 0


def _record_call(cfg: LLMRuntimeConfig, *, success: bool, tokens: int, latency_ms: float) -> None:
    record_llm_call(cfg.config_id, success=success, tokens=tokens, latency_ms=latency_ms)


async def _read_error_body(response: httpx.Response) -> str:
    try:
        text = (await response.aread()).decode('utf-8', errors='replace').strip()
        return text[:800] if text else ''
    except Exception:
        return ''


def _format_http_error(status_code: int, body: str, cfg: LLMRuntimeConfig) -> str:
    hint = ''
    if status_code == 401:
        hint = '请检查管理后台配置的 API Key 是否与当前调用地址匹配。'
    elif status_code == 404:
        hint = '请检查 api_endpoint 是否为 OpenAI 兼容根路径，例如 https://xiaoai.plus/v1（不要重复 /chat/completions）。'
    detail = body or '(无响应体)'
    return (
        f'LLM API 返回 {status_code}：{detail} '
        f'[model={cfg.model_name}, base_url={cfg.base_url}, config_id={cfg.config_id}]'
        + (f' {hint}' if hint else '')
    )


def _format_request_error(exc: httpx.RequestError, cfg: LLMRuntimeConfig, url: str) -> str:
    detail = str(exc).strip() or exc.__class__.__name__
    return (
        f'LLM API 网络请求失败：{detail} '
        f'[url={url}, model={cfg.model_name}, base_url={cfg.base_url}, config_id={cfg.config_id}]。'
        '请检查管理后台模型配置中的 api_endpoint 与网络连通性。'
    )


class OpenAICompatibleLLM:
    def __init__(self, scenario: str = 'qa'):
        self.scenario = scenario

    def _resolve(self) -> LLMRuntimeConfig:
        cfg = get_llm_runtime_config(scenario=self.scenario)
        validate_llm_runtime_config(cfg)
        return cfg

    def chat(self, messages: list[dict], temperature: float | None = None, max_tokens: int | None = None) -> str:
        cfg = self._resolve()
        url = f"{cfg.base_url.rstrip('/')}/chat/completions"
        payload = _build_payload(cfg, messages, temperature=temperature, max_tokens=max_tokens)
        logger.debug('LLM chat model=%s config_id=%s url=%s', cfg.model_name, cfg.config_id, cfg.base_url)
        started = time.perf_counter()
        success = False
        tokens = 0
        try:
            with httpx.Client(**_HTTPX_CLIENT_KW) as client:
                response = client.post(url, headers=_headers(cfg), json=payload)
                if response.status_code >= 400:
                    raise RuntimeError(_format_http_error(response.status_code, response.text[:800], cfg))
                data = response.json()
                tokens = _extract_usage_tokens(data)
                success = True
                return self._extract_content(data)
        finally:
            _record_call(cfg, success=success, tokens=tokens, latency_ms=(time.perf_counter() - started) * 1000)

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
        logger.debug('LLM async_chat model=%s config_id=%s url=%s', cfg.model_name, cfg.config_id, cfg.base_url)
        started = time.perf_counter()
        success = False
        tokens = 0
        try:
            async with httpx.AsyncClient(**_HTTPX_CLIENT_KW) as client:
                response = await client.post(url, headers=_headers(cfg), json=payload)
                if response.status_code >= 400:
                    raise RuntimeError(_format_http_error(response.status_code, response.text[:800], cfg))
                data = response.json()
                tokens = _extract_usage_tokens(data)
                success = True
                return self._extract_content(data, content_only=content_only)
        except httpx.RequestError as exc:
            raise RuntimeError(_format_request_error(exc, cfg, url)) from exc
        finally:
            _record_call(cfg, success=success, tokens=tokens, latency_ms=(time.perf_counter() - started) * 1000)

    async def stream_chat(self, messages: list[dict], temperature: float | None = None, max_tokens: int | None = None):
        cfg = self._resolve()
        url = f"{cfg.base_url.rstrip('/')}/chat/completions"
        payload = _build_payload(cfg, messages, temperature=temperature, max_tokens=max_tokens, stream=True)
        logger.debug('LLM stream_chat model=%s config_id=%s url=%s', cfg.model_name, cfg.config_id, cfg.base_url)
        started = time.perf_counter()
        success = False
        tokens = 0
        streamed_chars = 0
        try:
            async with httpx.AsyncClient(**_HTTPX_CLIENT_KW) as client:
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
                            usage_tokens = _extract_usage_tokens(obj)
                            if usage_tokens > 0:
                                tokens = usage_tokens
                            delta = obj['choices'][0].get('delta') or {}
                            reasoning = delta.get('reasoning_content') or delta.get('reasoning') or ''
                            content = delta.get('content') or delta.get('text') or ''
                            streamed_chars += len(reasoning) + len(content)
                            if reasoning:
                                yield ('reasoning', reasoning)
                            if content:
                                yield ('content', content)
                        except Exception:
                            continue
                success = True
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
        finally:
            if not tokens and streamed_chars:
                tokens = _estimate_tokens('x' * streamed_chars)
            if success and streamed_chars == 0:
                logger.warning(
                    'LLM stream_chat returned zero tokens model=%s config_id=%s url=%s',
                    cfg.model_name,
                    cfg.config_id,
                    cfg.base_url,
                )
            _record_call(cfg, success=success, tokens=tokens, latency_ms=(time.perf_counter() - started) * 1000)
