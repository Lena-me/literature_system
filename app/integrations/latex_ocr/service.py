from __future__ import annotations

import asyncio
import base64
import io
import re
import threading

from PIL import Image

_model = None
_model_lock = threading.Lock()


def _load_model():
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is None:
            from rapid_latex_ocr import LaTeXOCR

            _model = LaTeXOCR()
    return _model


def _decode_image_bytes(image_base64: str) -> bytes:
    base64_data = image_base64.strip()
    if 'base64,' in base64_data:
        base64_data = base64_data.split('base64,', 1)[1]
    image_bytes = base64.b64decode(base64_data)
    img = Image.open(io.BytesIO(image_bytes))
    if img.mode == 'RGB':
        return image_bytes
    buf = io.BytesIO()
    img.convert('RGB').save(buf, format='PNG')
    return buf.getvalue()


_GLUE_COMMANDS = (
    'sim', 'simeq', 'cong', 'approx', 'equiv', 'propto',
    'in', 'notin', 'ni', 'subset', 'supset', 'subseteq', 'supseteq',
    'to', 'mapsto', 'gets', 'leftrightarrow', 'Leftrightarrow',
    'rightarrow', 'leftarrow', 'Rightarrow', 'Leftarrow',
    'cdot', 'times', 'circ', 'bullet', 'pm', 'mp', 'cap', 'cup', 'vee', 'wedge',
    'leq', 'geq', 'neq', 'le', 'ge', 'lt', 'gt',
    'mid', 'parallel', 'perp', 'models', 'vdash', 'dashv',
)


def normalize_ocr_latex(latex: str) -> str:
    text = latex.strip()
    text = re.sub(r'([)\}_\w])\s*~\s*(?=\\|[A-Za-z{])', r'\1 \\sim ', text)
    for cmd in _GLUE_COMMANDS:
        text = re.sub(rf'\\{cmd}(?=[A-Za-z\\])', rf'\\{cmd} ', text)
    return text


def extract_latex_sync(image_base64: str) -> tuple[str, float]:
    model = _load_model()
    image_bytes = _decode_image_bytes(image_base64)
    result, elapsed = model(image_bytes)
    latex = (result or '').strip()
    if not latex:
        raise ValueError('未识别到公式内容，请扩大框选区域后重试')
    return normalize_ocr_latex(latex), float(elapsed or 0)


async def extract_latex(image_base64: str) -> tuple[str, float]:
    return await asyncio.to_thread(extract_latex_sync, image_base64)


def ocr_status() -> dict:
    if _model is not None:
        return {'available': True, 'model_loaded': True}
    try:
        import rapid_latex_ocr  # noqa: F401
    except ImportError as exc:
        return {'available': False, 'model_loaded': False, 'error': str(exc).strip() or 'rapid-latex-ocr 未安装'}
    return {'available': True, 'model_loaded': False}
