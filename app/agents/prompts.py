"""向后兼容：请优先使用 app.prompts.qa。"""
from app.prompts.qa import EMPTY_CONTEXT, SYSTEM_PROMPT, USER_PROMPT_TEMPLATE

__all__ = ['SYSTEM_PROMPT', 'USER_PROMPT_TEMPLATE', 'EMPTY_CONTEXT']
