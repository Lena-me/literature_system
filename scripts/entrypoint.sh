#!/bin/bash
set -e

MODELS_DIR="${MINERU_MODELS_DIR:-/app/mineru_models}"

echo "[entrypoint] Checking MinerU models in ${MODELS_DIR}..."

# mineru 2.x 期望 models/ 子目录（pdf-extract-kit-1.0 仓库原生结构）
if [ -d "${MODELS_DIR}/models/OCR/paddleocr_torch" ] && [ "$(ls -A "${MODELS_DIR}/models/OCR/paddleocr_torch" 2>/dev/null)" ]; then
    echo "[entrypoint] MinerU models found (models/ subdir), skipping download."
elif [ -d "${MODELS_DIR}/OCR/paddleocr_torch" ] && [ "$(ls -A "${MODELS_DIR}/OCR/paddleocr_torch" 2>/dev/null)" ]; then
    # 用户本地挂载的扁平结构（没有 models/ 前缀），创建 symlink 兼容
    echo "[entrypoint] Flat model structure detected, creating 'models' symlink..."
    ln -sfn . "${MODELS_DIR}/models"
    echo "[entrypoint] models/ symlink created (-> self)."
else
    echo "[entrypoint] Downloading MinerU models (one-time, ~2.5GB)..."
    TEMP_DIR=$(mktemp -d)
    python3 -c "
from huggingface_hub import snapshot_download
snapshot_download('opendatalab/pdf-extract-kit-1.0', local_dir='${TEMP_DIR}')"
    # minerU 2.x 保持 pdf-extract-kit-1.0 原生结构: models/ 子目录
    if [ -d "${TEMP_DIR}/models" ]; then
        echo "[entrypoint] Moving models directory to ${MODELS_DIR}..."
        mv "${TEMP_DIR}/models" "${MODELS_DIR}/models"
    fi
    rm -rf "${TEMP_DIR}"
    echo "[entrypoint] MinerU models download complete."
fi

echo "[entrypoint] Starting application..."
exec "$@"
