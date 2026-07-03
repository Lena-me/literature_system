from __future__ import annotations
import os
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
        # 增加 consolidate 参数，如果后端配置了可以大幅提升元数据准确率
        data = {
            'teiCoordinates': ['persName', 'figure', 'ref', 'biblStruct', 'formula'],
            'consolidateHeader': '1',
            'consolidateCitations': '0'
        }
        with httpx.Client(timeout=120) as client:
            response = client.post(url, files=files, data=data)
            response.raise_for_status()
            return response.text

    def _parse_tei(self, tei_xml: str) -> tuple[list[dict], dict, list[str]]:
        root = ET.fromstring(tei_xml.encode('utf-8'))
        title = self._text(root.find('.//tei:titleStmt/tei:title', TEI_NS))
        abstract = self._text(root.find('.//tei:profileDesc/tei:abstract', TEI_NS))
        authors = [self._text(a) for a in root.findall('.//tei:sourceDesc//tei:author//tei:persName', TEI_NS) if
                   self._text(a)]
        keywords = [self._text(k) for k in root.findall('.//tei:keywords/tei:term', TEI_NS) if self._text(k)]

        items: list[dict] = []
        order = 0

        if abstract:
            items.append(
                {'item_type': 'abstract', 'level': None, 'content': abstract, 'page_number': 1, 'order_index': order})
            order += 1

        # ★ 修复项：使用递归方式深度遍历 body，避免结构丢失和文本重复
        body = root.find('.//tei:text/tei:body', TEI_NS)
        if body is not None:
            order = self._walk_tei_node(body, items, order, level=1)

        # ★ 优化项：更精准的参考文献提取，保留 DOI 和年份等结构化信息
        refs = []
        for bibl in root.findall('.//tei:listBibl/tei:biblStruct', TEI_NS):
            ref_text = self._text(bibl)
            if ref_text:
                refs.append(ref_text)

        meta = {'title': title, 'authors': authors, 'keywords': keywords, 'abstract': abstract}
        return items, meta, refs

    def _walk_tei_node(self, node: ET.Element, items: list[dict], order: int, level: int) -> int:
        """递归遍历 TEI 节点，精准保留章节层级"""
        for element in node:
            tag = element.tag.split('}')[-1] if '}' in element.tag else element.tag

            if tag == 'div':
                # 如果遇到嵌套的 div，递归进入，层级加深
                order = self._walk_tei_node(element, items, order, level + 1)
                continue

            text = self._text(element)
            if not text:
                continue

            if tag == 'head':
                # 记录真实的 heading 级别
                items.append({'item_type': 'heading', 'level': level, 'content': text, 'page_number': None,
                              'order_index': order})
            elif tag == 'p':
                items.append({'item_type': 'paragraph', 'level': None, 'content': text, 'page_number': None,
                              'order_index': order})
            elif tag == 'formula':
                items.append(
                    {'item_type': 'formula', 'level': None, 'content': text, 'page_number': None, 'order_index': order})
            elif tag == 'list':
                items.append(
                    {'item_type': 'list', 'level': None, 'content': text, 'page_number': None, 'order_index': order})
            elif tag == 'figure':
                fig_type = element.get('type')
                if fig_type == 'table':
                    items.append({'item_type': 'table', 'level': None, 'content': text, 'page_number': None,
                                  'order_index': order})
                else:
                    items.append({'item_type': 'figure_caption', 'level': None, 'content': text, 'page_number': None,
                                  'order_index': order})

            # 不论什么类型，处理完一个叶子节点，order + 1
            if tag != 'div':
                order += 1

        return order

    def _parse_pages_with_pymupdf(self, pdf_bytes: bytes) -> list[dict]:
        doc = fitz.open(stream=pdf_bytes, filetype='pdf')
        pages = []
        for i, page in enumerate(doc, start=1):
            pages.append({'page_number': i, 'text': normalize_text(page.get_text('text'))})
        return pages

    def _parse_tables_with_pdfplumber(self, pdf_bytes: bytes) -> list[dict]:
        tables: list[dict] = []
        tmp_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'runtime', 'tmp')
        os.makedirs(tmp_dir, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(suffix='.pdf', dir=tmp_dir)
        try:
            with os.fdopen(fd, 'wb') as tmp:
                tmp.write(pdf_bytes)
            with pdfplumber.open(tmp_path) as pdf:
                for page_no, page in enumerate(pdf.pages, start=1):
                    for idx, table in enumerate(page.extract_tables() or []):
                        rows = ['\t'.join(cell or '' for cell in row) for row in table]
                        tables.append(
                            {'type': 'table', 'caption': f'Table extracted on page {page_no}', 'page_number': page_no,
                             'extracted_text': '\n'.join(rows), 'order_index': idx})
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        return tables

    def _text(self, node: ET.Element) -> str:
        """优化文本提取，保留行内标签（如 ref, formula）的自然间距"""
        if node is None:
            return ''
        # 使用 itertext 获取所有文本碎片，修复粘连问题
        fragments = list(node.itertext())
        raw_text = ' '.join(f.strip() for f in fragments if f.strip())
        return normalize_text(raw_text)