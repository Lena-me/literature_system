from __future__ import annotations

from app.core.config import get_settings
from app.integrations.document_parser.grobid_parser import GrobidPyMuPDFParser
from app.integrations.document_parser.mineru_parser import MinerUParser

settings = get_settings()


class FallbackDocumentParser:
    """Parser wrapper that falls back to GROBID when the primary parser fails."""

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
            parsed['parser'] = 'grobid_fallback'
            return parsed


def get_document_parser():
    parser_name = (settings.document_parser or 'grobid').lower().strip()

    if parser_name == 'mineru':
        mineru = MinerUParser()
        if settings.mineru_fallback_to_grobid:
            return FallbackDocumentParser(
                primary=mineru,
                fallback=GrobidPyMuPDFParser(),
            )
        return mineru

    return GrobidPyMuPDFParser()
