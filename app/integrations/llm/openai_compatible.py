from __future__ import annotations
import httpx
from app.core.config import get_settings
settings = get_settings()


def _headers() -> dict:
    """构建请求头，api_key 为空时省略 Authorization"""
    h = {'Content-Type': 'application/json'}
    key = (settings.llm_api_key or '').strip()
    if key:
        h['Authorization'] = f'Bearer {key}'
    return h


class OpenAICompatibleLLM:
    # === 同步接口（Celery worker 使用）===

    def chat(self, messages: list[dict], temperature: float | None = None, max_tokens: int | None = None) -> str:
        url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
        payload = {
            'model': settings.llm_model,
            'messages': messages,
            'temperature': settings.llm_temperature if temperature is None else temperature,
            'max_tokens': settings.llm_max_tokens if max_tokens is None else max_tokens,
        }
        headers = _headers()
        with httpx.Client(timeout=180) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return self._extract_content(data)

    # === 异步接口（FastAPI 端使用）===

    def _extract_content(self, data: dict, *, content_only: bool = False) -> str:
        """从 LLM 响应中提取文本内容，兼容推理模型（reasoning_content）"""
        msg = data.get('choices', [{}])[0].get('message', {})
        content = (msg.get('content') or '').strip()
        if content:
            return content
        if content_only:
            # 标题等短文本任务：不回退到 reasoning，避免整段思维链被当成标题
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
        url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
        payload = {
            'model': settings.llm_model,
            'messages': messages,
            'temperature': settings.llm_temperature if temperature is None else temperature,
            'max_tokens': settings.llm_max_tokens if max_tokens is None else max_tokens,
        }
        headers = _headers()
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return self._extract_content(data, content_only=content_only)

    async def stream_chat(self, messages: list[dict], temperature: float | None = None, max_tokens: int | None = None):
        """流式输出；yield (channel, text)，channel 为 reasoning | content。"""
        url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
        payload = {
            'model': settings.llm_model,
            'messages': messages,
            'temperature': settings.llm_temperature if temperature is None else temperature,
            'max_tokens': settings.llm_max_tokens if max_tokens is None else max_tokens,
            'stream': True,
        }
        headers = _headers()
        async with httpx.AsyncClient(timeout=180) as client:
            try:
                async with client.stream('POST', url, headers=headers, json=payload) as response:
                    if response.status_code == 401:
                        import logging
                        logging.getLogger(__name__).error(
                            'LLM 认证失败 (401)。请检查环境变量 LLM_API_KEY 是否正确。'
                            '当前 base_url=%s, model=%s, api_key_set=%s',
                            settings.llm_base_url, settings.llm_model,
                            bool((settings.llm_api_key or '').strip()),
                        )
                        raise RuntimeError(
                            'LLM API 认证失败 (401)。请检查 LLM_API_KEY 环境变量是否配置了有效的 API Key。'
                        )
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line or not line.startswith('data:'):
                            continue
                        data = line.removeprefix('data:').strip()
                        if data == '[DONE]':
                            break
                        try:
                            import json
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
            except httpx.HTTPStatusError:
                raise
            except httpx.RequestError as e:
                raise RuntimeError(f'LLM API 请求失败: {e}') from e
