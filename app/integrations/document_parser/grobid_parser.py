from __future__ import annotations
import tempfile
import xml.etree.ElementTree as ET
import httpx
import fitz
import pdfplumber
from app.core.config import get_settings
from app.utils.text_utils import normalize_text

settings = get_settings()
TEI_NS = {'tei': 'http://www.tei-c.org/ns/1.0'}

class GrobidPyMuPDFParser:
    # "GROBID + PyMuPDF + pdfplumber" 解析链：
    # GROBID 重建论文结构，PyMuPDF 保留页码文本，pdfplumber 抽取表格。
    def parse(self, pdf_bytes: bytes, filename: str) -> dict:
        tei_xml = self._call_grobid(pdf_bytes, filename)
        grobid_items, meta, references = self._parse_tei(tei_xml)
        pages = self._parse_pages_with_pymupdf(pdf_bytes)
        figures_tables = self._parse_tables_with_pdfplumber(pdf_bytes)
        if not grobid_items:
            grobid_items = [
                {
                    'item_type': 'paragraph',
                    'level': None,
                    'content': p['text'],
                    'page_number': p['page_number'],
                    'order_index': i,
                }
                for i, p in enumerate(pages)
            ]
        return {
            'metadata': meta,
            'content_items': grobid_items,
            'figures_tables': figures_tables,
            'references': references,
            'pages': pages,
            'tei_xml': tei_xml,
        }

    def _call_grobid(self, pdf_bytes: bytes, filename: str) -> str:
        url = f"{settings.grobid_base_url.rstrip('/')}/api/processFulltextDocument"
        files = {'input': (filename, pdf_bytes, 'application/pdf')}
        data = {'teiCoordinates': ['persName', 'figure', 'ref', 'biblStruct', 'formula']}
        with httpx.Client(timeout=120) as client:
            response = client.post(url, files=files, data=data)
            response.raise_for_status()
            return response.text

    def _parse_tei(self, tei_xml: str) -> tuple[list[dict], dict, list[str]]:
        root = ET.fromstring(tei_xml.encode('utf-8'))
        title = self._text(root.find('.//tei:titleStmt/tei:title', TEI_NS))
        abstract = self._text(root.find('.//tei:profileDesc/tei:abstract', TEI_NS))
        authors = [self._text(a) for a in root.findall('.//tei:sourceDesc//tei:author//tei:persName', TEI_NS) if self._text(a)]
        keywords = [self._text(k) for k in root.findall('.//tei:keywords/tei:term', TEI_NS) if self._text(k)]
        items: list[dict] = []
        order = 0
        if abstract:
            items.append({'item_type': 'abstract', 'level': None, 'content': abstract, 'page_number': 1, 'order_index': order}); order += 1
        for div in root.findall('.//tei:text/tei:body//tei:div', TEI_NS):
            head = self._text(div.find('tei:head', TEI_NS))
            if head:
                items.append({'item_type': 'heading', 'level': 1, 'content': head, 'page_number': None, 'order_index': order}); order += 1
            for p in div.findall('tei:p', TEI_NS):
                text = self._text(p)
                if text:
                    items.append({'item_type': 'paragraph', 'level': None, 'content': text, 'page_number': None, 'order_index': order}); order += 1
        refs = [self._text(b) for b in root.findall('.//tei:listBibl/tei:biblStruct', TEI_NS) if self._text(b)]
        meta = {'title': title, 'authors': authors, 'keywords': keywords, 'abstract': abstract}
        return items, meta, refs

    def _parse_pages_with_pymupdf(self, pdf_bytes: bytes) -> list[dict]:
        doc = fitz.open(stream=pdf_bytes, filetype='pdf')
        pages = []
        for i, page in enumerate(doc, start=1):
            pages.append({'page_number': i, 'text': normalize_text(page.get_text('text'))})
        return pages

    def _parse_tables_with_pdfplumber(self, pdf_bytes: bytes) -> list[dict]:
        tables: list[dict] = []
        with tempfile.NamedTemporaryFile(suffix='.pdf') as tmp:
            tmp.write(pdf_bytes); tmp.flush()
            with pdfplumber.open(tmp.name) as pdf:
                for page_no, page in enumerate(pdf.pages, start=1):
                    for idx, table in enumerate(page.extract_tables() or []):
                        rows = ['\t'.join(cell or '' for cell in row) for row in table]
                        tables.append({'type': 'table', 'caption': f'Table extracted on page {page_no}', 'page_number': page_no, 'extracted_text': '\n'.join(rows), 'order_index': idx})
        return tables

    def _text(self, node) -> str:
        if node is None:
            return ''
        return normalize_text(' '.join(''.join(node.itertext()).split()))
