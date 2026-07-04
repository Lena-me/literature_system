from __future__ import annotations

from app.core.config import get_settings
from app.integrations.document_parser.grobid_parser import GrobidPyMuPDFParser
from app.integrations.document_parser.mineru_parser import MinerUParser
import logging

settings = get_settings()
logger = logging.getLogger(__name__)


class HybridDocumentParser:
    """
    终极混合解析器 (Ensemble Parser)
    利用 Grobid 提取极其精准的 Metadata 和 References
    利用 MinerU 提取视觉极其精准的正文 Content 和 Tables/Figures
    """

    def __init__(self, mineru_parser: MinerUParser, grobid_parser: GrobidPyMuPDFParser) -> None:
        self.mineru = mineru_parser
        self.grobid = grobid_parser

    def parse(self, pdf_bytes: bytes, filename: str) -> dict:
        # 1. 首先运行 MinerU 获取高质量正文
        try:
            logger.info(f"Running MinerU for content extraction on {filename}")
            final_result = self.mineru.parse(pdf_bytes, filename)
            final_result['parser'] = 'hybrid (mineru+grobid)'
        except Exception as e:
            logger.warning(
                'MinerU failed: %s. Falling back entirely to Grobid '
                '(Grobid 无法提取 figure 图片，Markdown 中可能无图). '
                '若报错含 PageChars，请 pip install "pdftext>=0.6.3,<0.7" 后重跑解析.',
                e,
            )
            return self.grobid.parse(pdf_bytes, filename)

        # 2. 并行/串行运行 Grobid 榨取元数据
        try:
            logger.info(f"Running Grobid for metadata enhancement on {filename}")
            grobid_result = self.grobid.parse(pdf_bytes, filename)

            # --- 缝合魔法开始 ---

            # A. 元数据覆盖：Grobid 提取的作者和标题通常比 MinerU 的正则强
            g_meta = grobid_result.get('metadata', {})
            m_meta = final_result.get('metadata', {})

            if g_meta.get('title'):
                m_meta['title'] = g_meta['title']
            if g_meta.get('authors'):
                m_meta['authors'] = g_meta['authors']
            if g_meta.get('abstract') and len(g_meta['abstract']) > len(m_meta.get('abstract', '')):
                m_meta['abstract'] = g_meta['abstract']
            if g_meta.get('keywords'):
                # 列表去重合并
                m_meta['keywords'] = list(set(m_meta.get('keywords', []) + g_meta['keywords']))

            final_result['metadata'] = m_meta

            # B. 强行注入参考文献 (MinerU 通常无法结构化参考文献)
            if grobid_result.get('references'):
                final_result['references'] = grobid_result['references']

            # C. 保留 Grobid 的 TEI XML 备用
            final_result['tei_xml'] = grobid_result.get('tei_xml')

        except Exception as e:
            logger.error(f"Grobid metadata enhancement failed: {e}. Continuing with pure MinerU output.")

        return final_result


class FallbackDocumentParser:
    """传统的回退包装器"""

    def __init__(self, primary, fallback=None) -> None:
        self.primary = primary
        self.fallback = fallback

    def parse(self, pdf_bytes: bytes, filename: str) -> dict:
        try:
            return self.primary.parse(pdf_bytes, filename)
        except Exception as exc:
            if not self.fallback:
                raise
            parsed = self.fallback.parse(pdf_bytes, filename)
            parsed.setdefault('metadata', {})
            parsed['metadata']['parser_fallback_reason'] = f'{type(exc).__name__}: {str(exc)[:500]}'
            parsed['parser'] = 'fallback'
            return parsed


def get_document_parser():
    parser_name = (settings.document_parser or 'hybrid').lower().strip()

    mineru = MinerUParser()
    grobid = GrobidPyMuPDFParser()

    if parser_name == 'hybrid':
        # 启用终极混合解析模式
        return HybridDocumentParser(mineru_parser=mineru, grobid_parser=grobid)

    elif parser_name == 'mineru':
        if settings.mineru_fallback_to_grobid:
            return FallbackDocumentParser(primary=mineru, fallback=grobid)
        return mineru

    return grobid