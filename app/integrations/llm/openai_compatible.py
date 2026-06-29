from __future__ import annotations
import httpx
from app.core.config import get_settings
settings = get_settings()

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
        headers = {'Authorization': f'Bearer {settings.llm_api_key}', 'Content-Type': 'application/json'}
        with httpx.Client(timeout=180) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return data['choices'][0]['message']['content']

    # === 异步接口（FastAPI 端使用）===

    async def async_chat(self, messages: list[dict], temperature: float | None = None, max_tokens: int | None = None) -> str:
        url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
        payload = {
            'model': settings.llm_model,
            'messages': messages,
            'temperature': settings.llm_temperature if temperature is None else temperature,
            'max_tokens': settings.llm_max_tokens if max_tokens is None else max_tokens,
        }
        headers = {'Authorization': f'Bearer {settings.llm_api_key}', 'Content-Type': 'application/json'}
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return data['choices'][0]['message']['content']

    async def stream_chat(self, messages: list[dict], temperature: float | None = None, max_tokens: int | None = None):
        url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
        payload = {
            'model': settings.llm_model,
            'messages': messages,
            'temperature': settings.llm_temperature if temperature is None else temperature,
            'max_tokens': settings.llm_max_tokens if max_tokens is None else max_tokens,
            'stream': True,
        }
        headers = {'Authorization': f'Bearer {settings.llm_api_key}', 'Content-Type': 'application/json'}
        async with httpx.AsyncClient(timeout=180) as client:
            async with client.stream('POST', url, headers=headers, json=payload) as response:
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
                        piece = delta.get('content') or ''
                        if piece:
                            yield piece
                    except Exception:
                        continue
