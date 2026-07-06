from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.config import get_settings
from app.core.dependencies import get_current_user
from app.integrations.latex_ocr.service import extract_latex, ocr_status
from app.models import User
from app.schemas import FormulaExtractIn

router = APIRouter(prefix='/formula', tags=['公式识别'])
settings = get_settings()


@router.get('/health')
async def formula_health():
    if not settings.formula_ocr_enabled:
        return {'enabled': False, 'ready': False}
    status = ocr_status()
    return {
        'enabled': True,
        'ready': status.get('available', False),
        'model_loaded': status.get('model_loaded', False),
        'error': status.get('error'),
    }


@router.post('/extract')
async def extract_formula(
    data: FormulaExtractIn,
    user: User = Depends(get_current_user),
):
    del user
    if not settings.formula_ocr_enabled:
        raise HTTPException(status_code=503, detail='公式识别服务未启用')

    try:
        latex, cost_ms = await extract_latex(data.image_base64)
    except ImportError as exc:
        msg = str(exc).strip() or 'rapid-latex-ocr 未安装'
        if 'rapid_latex_ocr' in msg or 'rapid-latex-ocr' in msg:
            detail = f'缺少 rapid-latex-ocr 依赖：{msg}。请在后端同一 Python 环境执行 pip install rapid-latex-ocr'
        else:
            detail = f'公式识别依赖加载失败：{msg}'
        raise HTTPException(status_code=503, detail=detail) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f'公式识别失败: {exc}') from exc

    return {
        'status': 'success',
        'latex': latex,
        'cost_ms': cost_ms,
    }
