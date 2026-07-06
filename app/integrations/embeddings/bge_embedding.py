from __future__ import annotations
import logging
import os
from sentence_transformers import SentenceTransformer
from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

# ModelScope HF 模型名 -> ModelScope 仓库名 映射
_MODELSCOPE_MODEL_MAP = {
    'BAAI/bge-large-zh-v1.5': 'BAAI/bge-large-zh-v1.5',
}

_model: SentenceTransformer | None = None
_model_load_failed = False


def _is_valid_model_dir(path: str) -> bool:
    """验证目录是否为有效的模型目录（包含 config.json）"""
    return os.path.isdir(path) and os.path.isfile(os.path.join(path, 'config.json'))


def _download_from_modelscope(model_name: str, cache_dir: str) -> str | None:
    ms_model = _MODELSCOPE_MODEL_MAP.get(model_name, model_name)
    try:
        from modelscope import snapshot_download  # type: ignore[import-untyped]
        local_path = snapshot_download(ms_model, cache_dir=cache_dir)
        logger.info('ModelScope download ok: %s -> %s', ms_model, local_path)
        return local_path
    except Exception as e:
        logger.warning('ModelScope download failed for %s: %s', ms_model, e)
        return None


def _resolve_local_path(model_name: str) -> str:
    cache_dir = settings.hf_cache_dir

    # 1. 先查本地缓存（跳过网络），命中则直接返回
    model_id = model_name.split('/')[-1]               # bge-large-zh-v1.5
    model_id_alt = model_id.replace('.', '___')        # bge-large-zh-v1___5
    full_alt = model_name.replace('/', '___').replace('.', '___')  # BAAI___bge-large-zh-v1___5
    for root, dirs, files in os.walk(cache_dir):
        if '._____temp' in root:
            continue
        if (model_id in root or model_id_alt in root or full_alt in root) and _is_valid_model_dir(root):
            return root

    # 2. 本地未命中，尝试 ModelScope 下载
    local = _download_from_modelscope(model_name, cache_dir)
    if local and _is_valid_model_dir(local):
        return local

    raise FileNotFoundError(f"无法在 {cache_dir} 中定位模型 {model_name}，请检查挂载路径")

def _load_model() -> SentenceTransformer | None:
    global _model, _model_load_failed

    if _model is not None:
        return _model
    if _model_load_failed:
        return None

    model_name = settings.bge_embedding_model
    local_path = _resolve_local_path(model_name)

    try:
        import torch
        _model = SentenceTransformer(
            local_path,
            device=settings.embedding_device,
        )
        if settings.embedding_device.startswith('cuda'):
            _model.half()
        logger.info(
            'BGE embedding model loaded: %s (dims=%d, device=%s)',
            local_path,
            _model.get_sentence_embedding_dimension(),
            _model.device,
        )
        return _model
    except Exception as e:
        _model_load_failed = True
        logger.error('Failed to load BGE embedding model from %s: %s', local_path, e)
        raise


class BGEEmbedding:
    def encode_documents(self, texts: list[str]) -> list[list[float]]:
        model = _load_model()
        if model is None:
            raise RuntimeError('BGE embedding model not available')
        batch_size = 8
        all_vectors = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            vectors = model.encode(
                batch,
                normalize_embeddings=True,
                show_progress_bar=False,
                batch_size=batch_size,
            )
            all_vectors.extend([v.tolist() for v in vectors])
            import torch
            if settings.embedding_device.startswith('cuda'):
                torch.cuda.empty_cache()
        return all_vectors

    def encode_query(self, query: str) -> list[float]:
        model = _load_model()
        if model is None:
            raise RuntimeError('BGE embedding model not available')
        vector = model.encode([query], normalize_embeddings=True, show_progress_bar=False)[0]
        return vector.tolist()
