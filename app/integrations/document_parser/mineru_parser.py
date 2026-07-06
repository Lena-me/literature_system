from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

import fitz
import logging

from app.core.config import get_settings
from app.utils.text_utils import normalize_text

settings = get_settings()
logger = logging.getLogger(__name__)


def _check_pdftext_compatibility() -> None:
    """MinerU pipeline 依赖 pdftext<0.7；0.7 将 get_chars 改为 PageChars 导致 TypeError。"""
    if settings.mineru_backend != 'pipeline':
        return
    try:
        from importlib.metadata import version as pkg_version

        ver = pkg_version('pdftext')
    except Exception:
        return
    parts = ver.split('.')
    major = int(parts[0]) if parts and parts[0].isdigit() else 0
    if major >= 7:
        raise RuntimeError(
            f'pdftext {ver} 与 MinerU pipeline 不兼容（PageChars is not iterable）。'
            ' 请执行: pip install "pdftext>=0.6.3,<0.7" 后重启 Celery worker，'
            ' 或在 .env 中改用 MINERU_BACKEND=vlm（需 GPU）。'
        )


class MinerUParser:
    """MinerU CLI adapter that returns the existing parser result shape."""

    # ---------- 学位论文前置垃圾页关键词 ----------
    _THESIS_JUNK_PATTERNS = [
        r'答辩委员会',
        r'决议书',
        r'中图分类号',
        r'UDC',
        r'学校代码',
        r'学\s*号',
        r'密\s*级',
        r'授予学位单位',
        r'原创性声明',
        r'授权使用说明',
        r'学位论文版权使用授权书',
        r'学位论文原创性声明',
        r'关于学位论文使用授权的说明',
        r'保密\s*□?\s*年',
        r'指导教师',
        r'专业名称',
        r'学位类别',
        r'作者姓名',
        r'学院\s*[:：]',
        r'分类号',
    ]
    _THESIS_JUNK_RE = re.compile('|'.join(_THESIS_JUNK_PATTERNS))

    # ---------- 中文参考文献识别正则 ----------
    # 匹配: [1] 作者. 标题[J]. 期刊, 年份
    _CN_REF_PATTERN = re.compile(
        r'^\[\s*\d+(?:\s*[,，\-]\s*\d+)*\s*\].*?[JDCMPN]\s*[\.。]',
    )

    # ---------- 英文参考文献识别正则 ----------
    # 匹配: [1] J. Smith, et al., "Title," Journal, 2020.  / [1] J Smith et al. Title. Journal. 2020.
    _EN_REF_PATTERN = re.compile(
        r'^\[\s*\d+(?:\s*[,，\-]\s*\d+)*\s*\].*?(?:(?:\b(?:et\s+al|and)\b)|(?:[A-Z][a-z]+[,.]\s+[A-Z]\.)|(?:",?\s*".*?",))',
    )
    # 英文参考文献续行特征：DOI、页码范围、末尾年份、会议缩写
    _EN_REF_CONTINUATION_RE = re.compile(
        r'(doi:|DOI:|https?://doi\.org/|pp?\.\s*\d+[-–]\d+|'
        r'\b(?:Proc\.|Conf\.|Journal|Trans\.|ACM|IEEE|Springer|arXiv)\b|'
        r'[A-Z][a-z]+\s+et\s+al\.?|'
        r'\d{4}[.;,]?\s*$|'
        r'(?:vol\.?|pp\.?|no\.?)\s*\d+)',
        re.I,
    )

    # ---------- 公式检测正则 ----------
    # MinerU 经常把公式块误判为 paragraph，丢失了 $$ 包裹。
    # 此正则检测 LaTeX 公式特征命令，用于升维为 formula。
    _FORMULA_SIGNAL_RE = re.compile(
        r'\\(?:frac|sum|prod|int|lim|log|sqrt|mathrm|mathbb|mathcal|mathbf|mathit|'
        r'begin|end|tag|label|operatorname|DeclareMathOperator|'
        r'left|right|times|div|pm|nabla|partial|infty|approx|'
        r'alpha|beta|gamma|delta|epsilon|varepsilon|sigma|lambda|mu|pi|theta|omega|'
        r'cdot|qquad|quad|in|vert|'
        r'overline|underline|hat|tilde|bar|dot|vec|'
        r'text|textbf|textit|'
        r'Delta|Sigma|Omega|Pi|Gamma|Lambda|Theta|Phi)'
    )
    _TAG_RE = re.compile(r'\\tag\s*\{([^}]*)\}')
    _CJK_RE = re.compile(r'[\u4e00-\u9fff]')
    # 匹配结尾有 $$ 但开头没有的孤立公式（MinerU 切割 bug）
    _ORPHAN_CLOSING_RE = re.compile(r'\$\$\s*$')

    _KEYWORD_PREFIX_RE = re.compile(
        r'^(keywords?|关键词|关键字|index\s+terms)\s*[:：]\s*',
        flags=re.I
    )

    _KEYWORD_STOP_RE = re.compile(
        r'(?:'
        r'\*\s*The\s+authors|'
        r'\*\s*This\s+work|'
        r'\*\s*We\s+thank|'
        r'\*\s*This\s+research|'
        r'Acknowledgments?|'
        r'Acknowledgements?|'
        r'Funding|'
        r'Supported\s+by|'
        r'NSFC|'
        r'National\s+Natural\s+Science\s+Foundation|'
        r'Grant\s+No\.|'
        r'ACM\s+Reference\s+Format|'
        r'CCS\s+Concepts|'
        r'Additional\s+Key\s+Words|'
        r'Corresponding\s+author|'
        r'email\s*:|'
        r'@\w+|'
        r'doi[:：]|'
        r'https?://|'
        r'\b(?:University|University\s+of|Institute|College|School|Department|Laboratory)\b|'
        r'\b(?:IEEE|ACM|Springer|Elsevier|Wiley|Taylor\s+Francis)\b|'
        r'\b(?:et\s+al|and\s+the)\b|'
        r'\b(?:under\s+Grant|under\s+Contract|under\s+Award)\b|'
        r'National\s+Key\s+Research\s+and\s+Development\s+Program|'
        r'Research\s+Foundation|'
        r'Corresponding\s+Author|'
        r'First\s+author|'
        r'Second\s+author|'
        r'通讯作者|'
        r'第一作者|'
        r'第二作者|'
        r'致谢|'
        r'资助项目|'
        r'基金项目|'
        r'项目编号'
        r')',
        flags=re.I
    )

    _CHINESE_STOP_WORDS = {
        '的', '了', '和', '是', '就', '都', '而', '及', '与', '着', '或', '一个', '我们',
        '你们', '他们', '它们', '这', '那', '这些', '那些', '什么', '怎么', '如何',
        '为什么', '因为', '所以', '但是', '然而', '虽然', '如果', '可以', '可能', '应该',
        '会', '能', '要', '需要', '必须', '得', '有', '没有', '在', '从', '到', '向',
        '对', '对于', '关于', '通过', '基于', '使用', '利用', '采用', '实现', '表明',
        '显示', '发现', '认为', '提出', '研究', '分析', '讨论', '结果', '结论', '方法',
        '技术', '系统', '模型', '算法', '数据', '信息', '知识', '实验', '测试', '评估',
        '性能', '应用', '开发', '设计', '结构', '架构', '框架', '工具', '软件', '硬件',
        '论文', '文章', '文献', '本研究', '本文', '近年来', '目前', '随着', '由于',
        '因此', '同时', '并且', '以及', '包括', '例如', '比如', '等等', '一些', '许多',
        '大量', '部分', '全部', '主要', '重要', '关键', '核心', '基本', '基础', '相关',
        '不同', '相同', '类似', '比较', '对比', '结合', '综合', '整体', '局部', '具体',
        '一般', '特殊', '常见', '少见', '可能', '不可能', '一定', '不一定', '几乎', '大约',
        '左右', '上下', '前后', '之间', '以上', '以下', '以内', '以外', '之一',
        '等人', '基于多', '硕士学位', '签名', '土木工程', '方法研究',
        '广州', '大学', '陈川江', '陈', '川江', '刘', '张', '王', '李', '赵', '孙',
        '黄', '吴', '周', '徐', '朱', '马', '胡', '郭', '林', '何', '高', '罗', '梁',
        '谢', '宋', '唐', '许', '韩', '曹', '邓', '彭', '曾', '肖', '田', '董', '潘',
        '袁', '蔡', '蒋', '余', '于', '杜', '叶', '程', '魏', '苏', '吕', '丁', '任',
        '沈', '姚', '卢', '姜', '崔', '钟', '谭', '陆', '汪', '范', '金', '石', '廖',
        '贾', '夏', '付', '方', '邹', '熊', '白', '孟', '秦', '邱', '侯', '江', '尹',
        '薛', '闫', '段', '雷', '龙', '史', '陶', '黎', '贺', '顾', '毛', '郝', '龚',
        '邵', '万', '钱', '严', '赖', '覃', '洪', '武', '莫', '孔', '汤', '常', '温',
        '康', '施', '文', '彭', '牛', '樊', '葛', '邢', '安', '齐', '易', '乔', '伍',
        '庞', '颜', '倪', '庄', '聂', '章', '鲁', '岳', '翟', '殷', '詹', '申', '欧',
        '耿', '关', '兰', '焦', '俞', '左', '柳', '祝', '纪', '尚', '毕', '耿', '芦',
        '铁路', '路基', '填筑', '施工', '工序', '识别', '预警', '广州大学', '硕士',
        '学位论文', '论文', '研究', '设计', '实现', '分析', '讨论', '提出', '表明',
        '显示', '发现', '认为', '可能', '可以', '已经', '近年来', '目前', '随着',
        '由于', '因此', '然而', '但是', '同时', '并且', '以及', '包括', '例如', '比如',
        '等等', '一些', '许多', '大量', '部分', '全部', '主要', '重要', '关键', '核心',
        '基本', '基础', '相关', '不同', '相同', '类似', '比较', '对比', '结合', '综合',
        '整体', '局部', '具体', '一般', '特殊', '常见', '少见', '一定', '不一定', '几乎',
    }

    _ENGLISH_STOP_WORDS = {
        'first', 'second', 'third', 'last', 'finally', 'also', 'and', 'or', 'but', 'not',
        'this', 'that', 'these', 'those', 'with', 'for', 'of', 'in', 'on', 'at', 'to',
        'from', 'by', 'as', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have',
        'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may',
        'might', 'must', 'shall', 'can', 'cannot', 'need', 'want', 'like', 'get', 'make',
        'take', 'give', 'go', 'come', 'know', 'think', 'see', 'look', 'feel', 'say',
        'tell', 'ask', 'answer', 'find', 'show', 'use', 'work', 'study', 'research',
        'paper', 'article', 'document', 'system', 'method', 'approach', 'technique',
        'algorithm', 'model', 'framework', 'tool', 'software', 'hardware', 'data',
        'information', 'knowledge', 'result', 'analysis', 'evaluation', 'performance',
        'experiment', 'test', 'case', 'example', 'application', 'implementation',
        'development', 'design', 'structure', 'architecture', 'university', 'institute',
        'school', 'department', 'laboratory', 'college', 'author', 'authors', 'reference',
        'references', 'acknowledgments', 'acknowledgements', 'funding', 'grant',
        'national', 'natural', 'science', 'foundation', 'project', 'program', 'supported',
        'the', 'a', 'an', 'some', 'any', 'all', 'each', 'every', 'both', 'few', 'more',
        'most', 'other', 'another', 'such', 'no', 'nor', 'neither', 'either', 'enough',
        'little', 'less', 'least', 'much', 'many', 'more', 'most', 'several', 'few',
        'enough', 'how', 'when', 'where', 'why', 'what', 'which', 'who', 'whom', 'whose',
        'me', 'him', 'her', 'us', 'them', 'my', 'your', 'his', 'its', 'our', 'their',
        'mine', 'yours', 'hers', 'ours', 'theirs', 'myself', 'yourself', 'himself',
        'herself', 'ourselves', 'yourselves', 'themselves', 'it', 'its', 'they', 'their',
        'ieee', 'acm', 'springer', 'elsevier', 'wiley', 'taylor', 'francis', 'sage',
        'karger', 'mdpi', 'hindawi', 'iop', 'oup', 'cambridge', 'press', 'publisher',
        'proceedings', 'journal', 'transactions', 'letters', 'magazine', 'conference',
        'symposium', 'workshop', 'annual', 'international', 'national', 'regional',
        'dept', 'lab', 'center', 'centre', 'faculty', 'graduate', 'undergraduate',
        'phd', 'msc', 'bsc', 'professor', 'dr', 'mr', 'ms', 'mrs', 'miss', 'sir',
        'yang', 'zhang', 'li', 'wang', 'chen', 'liu', 'zhao', 'huang', 'wu', 'zhou',
        'xu', 'sun', 'ma', 'zhu', 'hu', 'guo', 'lin', 'he', 'gao', 'peng', 'liu',
        'chen', 'zhang', 'wang', 'li', 'zhao', 'liu', 'sun', 'huang', 'wu', 'zhu',
        'xu', 'lin', 'he', 'gao', 'guo', 'ma', 'peng', 'yang', 'han', 'liang', 'yu',
        'song', 'zheng', 'tang', 'feng', 'cao', 'xiang', 'zhong', 'dong', 'yuan',
        'xiao', 'wu', 'qian', 'jin', 'cheng', 'zhou', 'xiang', 'jiang', 'bo', 'lu',
        'zheng', 'tang', 'feng', 'cao', 'dong', 'yuan', 'xiao', 'qian', 'jin', 'cheng',
        'jiang', 'bo', 'lu', 'wang', 'zhang', 'li', 'chen', 'liu', 'zhao', 'sun',
        'huang', 'wu', 'zhu', 'xu', 'lin', 'he', 'gao', 'guo', 'ma', 'peng', 'yang',
        'yifan', 'yuhao', 'yingfei', 'lu', 'shing', 'chi', 'cheung', 'xiong', 'lu',
    }

    def parse(self, pdf_bytes: bytes, filename: str) -> dict:
        job_id = uuid4().hex
        base_output_dir = Path(settings.mineru_output_dir)
        base_output_dir.mkdir(parents=True, exist_ok=True)

        job_output_dir = base_output_dir / job_id
        job_output_dir.mkdir(parents=True, exist_ok=True)

        safe_name = self._safe_filename(filename)
        input_pdf = job_output_dir / safe_name
        input_pdf.write_bytes(pdf_bytes)

        try:
            self._run_mineru(input_pdf, job_output_dir)

            content_json = self._load_content_json(job_output_dir)
            markdown_text = self._load_markdown(job_output_dir)
            parsed = self._convert_outputs(
                markdown_text=markdown_text,
                content_json=content_json,
                pdf_bytes=pdf_bytes,
                filename=filename,
            )
            parsed['parser'] = 'mineru'
            parsed['mineru_output_dir'] = str(job_output_dir)

            # 在 cleanup 前收集图片数据，供 pipeline_service 上传到 MinIO
            parsed['_image_data'] = self._collect_output_images(
                job_output_dir,
                parsed.get('figures_tables', []),
            )

            return parsed
        finally:
            if not settings.mineru_keep_output:
                shutil.rmtree(job_output_dir, ignore_errors=True)

    def _run_mineru(self, input_pdf: Path, output_dir: Path) -> None:
        _check_pdftext_compatibility()
        cmd = [
            settings.mineru_command,
            '-p',
            str(input_pdf),
            '-o',
            str(output_dir),
        ]

        if settings.mineru_backend:
            cmd.extend(['-b', settings.mineru_backend])
        if settings.mineru_method:
            cmd.extend(['-m', settings.mineru_method])
        if settings.mineru_language:
            cmd.extend(['-l', settings.mineru_language])
        if settings.mineru_api_url:
            cmd.extend(['--api-url', settings.mineru_api_url])

        try:
            proc = subprocess.run( 
                cmd,
                capture_output=True,
                check=False,
                text=True,
                timeout=settings.mineru_timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(
                f'MinerU parse timed out after {settings.mineru_timeout_seconds}s'
            ) from exc

        if proc.returncode != 0:
            stdout = (proc.stdout or '')[-2000:]
            stderr = (proc.stderr or '')[-4000:]
            raise RuntimeError(
                f'MinerU parse failed: returncode={proc.returncode}\n'
                f'STDOUT:\n{stdout}\nSTDERR:\n{stderr}'
            )

    def _convert_outputs(
        self,
        markdown_text: str,
        content_json,
        pdf_bytes: bytes,
        filename: str,
    ) -> dict:
        pages = self._parse_pages_with_pymupdf(pdf_bytes)
        json_items, json_figures = self._items_from_content_json(content_json)

        if json_items:
            content_items = json_items
            figures_tables = json_figures
        else:
            content_items, figures_tables = self._items_from_markdown(markdown_text)

        if not content_items:
            content_items = [
                {
                    'item_type': 'paragraph',
                    'level': None,
                    'content': page['text'],
                    'bbox': None,
                    'page_number': page['page_number'],
                    'order_index': idx,
                }
                for idx, page in enumerate(pages)
                if page.get('text')
            ]
        content_items = self._post_process_items(content_items)

        metadata = self._extract_metadata(markdown_text, content_items, filename)
        return {
            'metadata': metadata,
            'content_items': content_items,
            'figures_tables': figures_tables,
            'references': [],
            'pages': pages,
            'markdown': markdown_text,
        }

    def _load_markdown(self, output_dir: Path) -> str:
        md_files = list(output_dir.rglob('*.md'))
        if not md_files:
            return ''

        md_files.sort(key=lambda p: p.stat().st_size, reverse=True)
        for path in md_files:
            try:
                text = path.read_text(encoding='utf-8', errors='ignore')
            except Exception:
                continue
            if text.strip():
                return text
        return ''

    def _load_content_json(self, output_dir: Path):
        json_files = list(output_dir.rglob('*.json'))
        if not json_files:
            return None

        def score(path: Path) -> tuple[int, int]:
            name = path.name.lower()
            if 'content_list_v2' in name:
                rank = 0
            elif 'content_list' in name:
                rank = 1
            elif 'middle' in name:
                rank = 2
            elif 'model' in name:
                rank = 3
            else:
                rank = 9
            return rank, -path.stat().st_size

        for path in sorted(json_files, key=score):
            try:
                data = json.loads(path.read_text(encoding='utf-8', errors='ignore'))
            except Exception:
                continue
            if data:
                return data
        return None

    def _flatten_content_json_blocks(self, data) -> list[dict]:
        """展开 MinerU content_list_v2 的「页 → 块」嵌套结构。"""
        if isinstance(data, dict):
            if isinstance(data.get('content_list'), list):
                raw = data.get('content_list') or []
            elif isinstance(data.get('pages'), list):
                blocks: list[dict] = []
                for page_idx, page in enumerate(data.get('pages') or []):
                    if isinstance(page, dict):
                        page_blocks = page.get('blocks') or page.get('content') or []
                    elif isinstance(page, list):
                        page_blocks = page
                    else:
                        continue
                    for block in page_blocks:
                        if isinstance(block, dict):
                            enriched = dict(block)
                            enriched.setdefault('page_idx', page_idx)
                            blocks.append(enriched)
                return blocks
            elif isinstance(data.get('blocks'), list):
                raw = data.get('blocks') or []
            else:
                return []
        elif isinstance(data, list):
            raw = data
        else:
            return []

        if not raw:
            return []

        if all(isinstance(page, list) for page in raw):
            blocks = []
            for page_idx, page in enumerate(raw):
                for block in page:
                    if isinstance(block, dict):
                        enriched = dict(block)
                        enriched.setdefault('page_idx', page_idx)
                        blocks.append(enriched)
            return blocks

        return [block for block in raw if isinstance(block, dict)]

    @staticmethod
    def _normalize_bbox(bbox) -> list[float] | None:
        """MinerU bbox 为 0~1000 比例坐标（左上原点），统一存为 [x0,y0,x1,y1]（0~1）。"""
        if not bbox:
            return None
        if isinstance(bbox, dict):
            if all(k in bbox for k in ('left', 'top', 'width', 'height')):
                left = float(bbox['left'])
                top = float(bbox['top'])
                width = float(bbox['width'])
                height = float(bbox['height'])
                return [left, top, left + width, top + height]
            return None
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            return None
        try:
            x0, y0, x1, y1 = (float(v) for v in bbox)
        except (TypeError, ValueError):
            return None
        if max(x0, y0, x1, y1) <= 1.0:
            return [x0, y0, x1, y1]
        scale = 1000.0 if max(x0, y0, x1, y1) <= 1000.0 else max(x1, y1)
        return [x0 / scale, y0 / scale, x1 / scale, y1 / scale]

    def _block_bbox(self, block: dict) -> list[float] | None:
        return self._normalize_bbox(block.get('bbox'))

    @staticmethod
    def _normalize_latex_for_katex(latex: str) -> str:
        """收紧 MinerU 松散 LaTeX，并替换 KaTeX 不支持的 \\tag。"""
        text = latex.strip()
        if not text:
            return text

        text = MinerUParser._TAG_RE.sub(r'\\quad\\text{(\1)}', text)
        text = re.sub(
            r'\\(mathit|mathrm|mathbf|mathcal|mathbb|mathfrak|mathsf|mathtt)\s*\{\s*([^}]+?)\s*\}',
            lambda m: f'\\{m.group(1)}{{{"".join(m.group(2).split())}}}',
            text,
        )
        text = re.sub(
            r'\\operatorname\s*\*\s*\{\s*([^}]+?)\s*\}',
            lambda m: f'\\operatorname*{{{"".join(m.group(1).split())}}}',
            text,
        )
        text = re.sub(
            r'\\operatorname\s*\{\s*([^}]+?)\s*\}',
            lambda m: f'\\operatorname{{{"".join(m.group(1).split())}}}',
            text,
        )
        text = re.sub(
            r'_\s*\{\s*([^}]+?)\s*\}',
            lambda m: f'_{{{"".join(m.group(1).split())}}}',
            text,
        )
        text = re.sub(
            r'\^\s*\{\s*([^}]+?)\s*\}',
            lambda m: '^{' + ''.join(m.group(1).split()) + '}',
            text,
        )
        text = re.sub(r'\{\s+', '{', text)
        text = re.sub(r'\s+\}', '}', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _render_rich_content(self, spans) -> str:
        """将 v2 JSON 的 paragraph_content / title_content 转为 Markdown 文本。"""
        if not isinstance(spans, list):
            return self._stringify_mineru_value(spans)

        parts: list[str] = []
        for span in spans:
            if not isinstance(span, dict):
                continue
            span_type = str(span.get('type') or '').lower()
            raw = span.get('content') or span.get('text') or ''
            if isinstance(raw, dict):
                raw = self._stringify_mineru_value(raw)
            text = str(raw)
            if not text:
                continue
            if 'equation_inline' in span_type or span_type in ('inline', 'inline_formula'):
                latex = self._normalize_latex_for_katex(text)
                parts.append(f'${latex}$')
            else:
                parts.append(text)
        return normalize_text(''.join(parts))

    def _render_list_content(self, content: dict) -> str:
        """将 v2 JSON 的 list/index 块转为可读文本列表。"""
        if not isinstance(content, dict):
            return ''
        list_items = content.get('list_items') or []
        lines: list[str] = []
        for item in list_items:
            if not isinstance(item, dict):
                continue
            spans = item.get('item_content') or item.get('content') or []
            if isinstance(spans, dict):
                if spans.get('item_content') is not None:
                    spans = spans.get('item_content')
                elif spans.get('content') is not None:
                    spans = [spans]
                else:
                    spans = []
            line = self._render_rich_content(spans)
            if line:
                lines.append(line)
        return normalize_text('\n'.join(lines))

    @staticmethod
    def _extract_image_path(block: dict) -> str | None:
        """从 MinerU v1/v2 图片块提取相对路径。"""
        for key in ('img_path', 'image_path', 'path'):
            val = block.get(key)
            if val:
                return str(val).strip()
        content = block.get('content')
        if isinstance(content, dict):
            source = content.get('image_source') or {}
            if isinstance(source, dict):
                path = source.get('path')
                if path:
                    return str(path).strip()
        return None

    def _extract_image_caption(self, block: dict, block_content: dict | None = None) -> str:
        block_content = block_content if isinstance(block_content, dict) else block.get('content')
        for src in (block.get('img_caption'), block.get('caption'), block.get('text')):
            cap = self._stringify_mineru_value(src)
            if cap:
                return cap
        if isinstance(block_content, dict):
            cap_spans = block_content.get('image_caption') or block_content.get('caption')
            if isinstance(cap_spans, list):
                return self._render_rich_content(cap_spans)
            cap = self._stringify_mineru_value(cap_spans)
            if cap:
                return cap
        return ''

    def _extract_image_footnote(self, block: dict, block_content: dict | None = None) -> str:
        block_content = block_content if isinstance(block_content, dict) else block.get('content')
        footnote = self._stringify_mineru_value(block.get('img_footnote') or block.get('footnote') or '')
        if footnote:
            return footnote
        if isinstance(block_content, dict):
            spans = block_content.get('image_footnote') or block_content.get('footnote')
            if isinstance(spans, list):
                return self._render_rich_content(spans)
            return self._stringify_mineru_value(spans)
        return ''

    @staticmethod
    def _is_page_metadata_block(block_type: str) -> bool:
        return any(
            token in block_type
            for token in ('page_header', 'page_footer', 'page_number')
        )

    def _wrap_latex_content(self, latex: str, math_type: str = '') -> str:
        latex = self._normalize_latex_for_katex(latex)
        if not latex:
            return ''
        if math_type in ('equation_inline', 'inline', 'inline_formula'):
            return f'${latex}$'
        return f'$$\n{latex}\n$$'

    @staticmethod
    def _should_upgrade_paragraph_to_formula(content: str) -> bool:
        """仅将纯 LaTeX 段落升维为 formula，跳过中英文混排 + 行内公式。"""
        text = content.strip()
        if not text or (text.startswith('$$') and text.endswith('$$')):
            return False
        if '$' in text:
            return False
        if MinerUParser._CJK_RE.search(text):
            return False
        return bool(MinerUParser._FORMULA_SIGNAL_RE.search(text))

    def _items_from_content_json(self, data) -> tuple[list[dict], list[dict]]:
        if not data:
            return [], []

        blocks = self._flatten_content_json_blocks(data)

        content_items: list[dict] = []
        figures_tables: list[dict] = []
        order = 0

        for block in blocks:
            if not isinstance(block, dict):
                continue

            block_type = str(
                block.get('type')
                or block.get('block_type')
                or block.get('category')
                or block.get('category_type')
                or ''
            ).lower()

            page_number = block.get('page_number') or block.get('page_no') or block.get('page')
            page_idx = block.get('page_idx')
            if page_number is None and isinstance(page_idx, int):
                page_number = page_idx + 1

            text_level = block.get('text_level') or block.get('level')
            level = self._to_int(text_level, default=1) if text_level not in (None, '') else None

            if self._is_page_metadata_block(block_type):
                continue

            nested_content = block.get('content') if isinstance(block.get('content'), dict) else {}

            if 'table' in block_type:
                caption_spans = (
                    block.get('table_caption')
                    or block.get('caption')
                    or nested_content.get('table_caption')
                    or block.get('text')
                    or ''
                )
                if isinstance(caption_spans, list):
                    caption = self._render_rich_content(caption_spans)
                else:
                    caption = self._stringify_mineru_value(caption_spans)
                raw_body = (
                    block.get('table_body')
                    or block.get('html')
                    or nested_content.get('html')
                    or nested_content.get('table_body')
                    or (nested_content if nested_content else None)
                    or block.get('text')
                    or ''
                )
                body = self._format_table_body(raw_body)
                footnote_spans = block.get('table_footnote') or nested_content.get('table_footnote') or ''
                if isinstance(footnote_spans, list):
                    footnote = self._render_rich_content(footnote_spans)
                else:
                    footnote = self._stringify_mineru_value(footnote_spans)
                table_text = normalize_text('\n'.join(x for x in [caption, body, footnote] if x))
                if not table_text:
                    continue

                figures_tables.append(
                    {
                        'type': 'table',
                        'caption': caption or 'Table extracted by MinerU',
                        'page_number': page_number,
                        'extracted_text': table_text,
                        'order_index': len(figures_tables),
                    }
                )
                content_items.append(
                    {
                        'item_type': 'table',
                        'level': None,
                        'content': table_text,
                        'bbox': self._block_bbox(block),
                        'page_number': page_number,
                        'order_index': order,
                    }
                )
                order += 1
                continue

            if 'image' in block_type or 'figure' in block_type:
                caption = self._extract_image_caption(block, nested_content)
                footnote = self._extract_image_footnote(block, nested_content)
                extracted_text = normalize_text('\n'.join(x for x in [caption, footnote] if x))
                image_path = self._extract_image_path(block)

                figures_tables.append(
                    {
                        'type': 'figure',
                        'caption': caption or 'Figure extracted by MinerU',
                        'page_number': page_number,
                        'image_path': str(image_path) if image_path else None,
                        'extracted_text': extracted_text,
                        'order_index': len(figures_tables),
                    }
                )
                md_image = self._build_image_markdown(caption, image_path, footnote)
                content_items.append(
                    {
                        'item_type': 'figure',
                        'level': None,
                        'content': md_image,
                        'bbox': self._block_bbox(block),
                        'page_number': page_number,
                        'order_index': order,
                    }
                )
                order += 1
                continue

            if 'equation' in block_type or 'formula' in block_type:
                # MinerU 的 formula/equation 块的 LaTeX 深层嵌套在 content 字典的 math_content 字段中
                block_content = block.get('content') or {}
                latex = ''
                math_type = ''
                if isinstance(block_content, dict):
                    # 精准提取 math_content 字段中的 LaTeX 代码
                    math_content = block_content.get('math_content') or ''
                    math_type = str(block_content.get('math_type') or block.get('math_type') or '').lower()
                    if isinstance(math_content, str) and math_content.strip():
                        latex = math_content.strip()
                    elif isinstance(math_content, dict):
                        latex = self._stringify_mineru_value(math_content)
                    elif isinstance(math_content, list):
                        latex = ''.join(str(x) for x in math_content if x)
                    else:
                        # 兜底：从整个 content 字典提取
                        latex = self._stringify_mineru_value(block_content)
                else:
                    latex = self._stringify_mineru_value(block_content)

                latex = self._wrap_latex_content(latex, math_type)
                if not latex:
                    continue

                content_items.append(
                    {
                        'item_type': 'formula',
                        'level': None,
                        'content': latex,
                        'bbox': self._block_bbox(block),
                        'page_number': page_number,
                        'order_index': order,
                    }
                )
                order += 1
                continue

            if block_type in ('list', 'index') or (
                isinstance(nested_content, dict) and nested_content.get('list_items')
            ):
                text = self._render_list_content(nested_content)
                if text:
                    content_items.append(
                        {
                            'item_type': 'paragraph',
                            'level': None,
                            'content': text,
                            'bbox': self._block_bbox(block),
                            'page_number': page_number,
                            'order_index': order,
                        }
                    )
                    order += 1
                continue

            block_content = block.get('content')
            if isinstance(block_content, dict):
                if 'paragraph_content' in block_content:
                    text = self._render_rich_content(block_content.get('paragraph_content'))
                elif 'title_content' in block_content:
                    text = self._render_rich_content(block_content.get('title_content'))
                    title_level = block_content.get('level') or block.get('level') or level
                    if text:
                        content_items.append(
                            {
                                'item_type': 'heading',
                                'level': self._to_int(title_level, default=1),
                                'content': text,
                                'bbox': self._block_bbox(block),
                                'page_number': page_number,
                                'order_index': order,
                            }
                        )
                        order += 1
                    continue
                elif block_content.get('list_items'):
                    text = self._render_list_content(block_content)
                else:
                    text = ''
            else:
                text = ''

            if not text:
                text = self._stringify_mineru_value(
                    block.get('text')
                    or block_content
                    or block.get('html')
                    or block.get('caption')
                    or ''
                )
                text = normalize_text(text)
            if not text:
                continue

            if 'title' in block_type or 'heading' in block_type or level is not None:
                item_type = 'heading'
                item_level = level or 1
            elif 'equation' in block_type or 'formula' in block_type:
                item_type = 'formula'
                item_level = None
            else:
                item_type = 'paragraph'
                item_level = None

            content_items.append(
                {
                    'item_type': item_type,
                    'level': item_level,
                    'content': text,
                    'bbox': self._block_bbox(block),
                    'page_number': page_number,
                    'order_index': order,
                }
            )
            order += 1

        return content_items, figures_tables

    def _items_from_markdown(self, markdown_text: str) -> tuple[list[dict], list[dict]]:
        content_items: list[dict] = []
        figures_tables: list[dict] = []
        if not markdown_text.strip():
            return content_items, figures_tables

        lines = markdown_text.splitlines()
        order = 0
        paragraph_buffer: list[str] = []

        def flush_paragraph() -> None:
            nonlocal order
            text = normalize_text('\n'.join(paragraph_buffer).strip())
            paragraph_buffer.clear()
            if not text:
                return
            content_items.append(
                {
                    'item_type': 'paragraph',
                    'level': None,
                    'content': text,
                    'bbox': None,
                    'page_number': None,
                    'order_index': order,
                }
            )
            order += 1

        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                flush_paragraph()
                i += 1
                continue

            heading = re.match(r'^(#{1,6})\s+(.+)$', line)
            if heading:
                flush_paragraph()
                content_items.append(
                {
                    'item_type': 'heading',
                    'level': len(heading.group(1)),
                    'content': normalize_text(heading.group(2)),
                    'bbox': None,
                    'page_number': None,
                    'order_index': order,
                }
            )
                order += 1
                i += 1
                continue

            image = re.match(r'^!\[(.*?)\]\((.*?)\)', line)
            if image:
                flush_paragraph()
                caption = normalize_text(image.group(1) or '')
                image_path = image.group(2) or None
                md_image = self._build_image_markdown(caption, image_path)
                figures_tables.append(
                    {
                        'type': 'figure',
                        'caption': caption or 'Figure extracted by MinerU',
                        'page_number': None,
                        'image_path': image_path,
                        'extracted_text': md_image,
                        'order_index': len(figures_tables),
                    }
                )
                content_items.append(
                    {
                        'item_type': 'figure',
                        'level': None,
                        'content': md_image,
                        'bbox': None,
                        'page_number': None,
                        'order_index': order,
                    }
                )
                order += 1
                i += 1
                continue

            if self._looks_like_table_line(line):
                flush_paragraph()
                table_lines = []
                while i < len(lines) and self._looks_like_table_line(lines[i].strip()):
                    table_lines.append(lines[i].strip())
                    i += 1
                table_text = '\n'.join(table_lines)
                figures_tables.append(
                    {
                        'type': 'table',
                        'caption': 'Table extracted by MinerU',
                        'page_number': None,
                        'extracted_text': table_text,
                        'order_index': len(figures_tables),
                    }
                )
                content_items.append(
                    {
                        'item_type': 'table',
                        'level': None,
                        'content': table_text,
                        'bbox': None,
                        'page_number': None,
                        'order_index': order,
                    }
                )
                order += 1
                continue

            paragraph_buffer.append(line)
            i += 1

        flush_paragraph()
        return content_items, figures_tables

    def _looks_like_table_line(self, line: str) -> bool:
        return line.count('|') >= 2

    # ======================== 辅助方法 ========================

    @staticmethod
    def _build_image_markdown(caption: str, image_path, footnote: str = '') -> str:
        """组装图片 Markdown：图片行 + 可见图题（与 MinerU 原生 .md 一致）。

        图题放在图片下方独立一行，而不是写在 alt 文本里（alt 在浏览器中不可见）。
        """
        cap = (caption or '').strip()
        note = (footnote or '').strip()
        path = str(image_path or '').strip()
        if path:
            path = path.replace('\\', '/')
            lines = [f'![]({path})']
            if cap:
                lines.append(cap)
            if note:
                lines.append(note)
            return '\n'.join(lines)
        return normalize_text('\n'.join(x for x in [cap, note] if x))

    @staticmethod
    def _format_table_body(raw_body) -> str:
        """将表格 body 格式化为可渲染文本：2D数组→Markdown表格，HTML→转Markdown，纯文本→原样返回。"""
        # 严格二维数组 (list[list]) → 转 Markdown 表格
        if isinstance(raw_body, list) and len(raw_body) > 0 and isinstance(raw_body[0], list):
            lines = []
            for i, row in enumerate(raw_body):
                if isinstance(row, list):
                    cells = [str(cell) for cell in row]
                    lines.append('| ' + ' | '.join(cells) + ' |')
                    if i == 0:
                        lines.append('| ' + ' | '.join('---' for _ in cells) + ' |')
                else:
                    lines.append(str(row))
            return '\n'.join(lines)

        text = raw_body if isinstance(raw_body, str) else json.dumps(raw_body, ensure_ascii=False)
        # HTML 表格 → 尝试转为 Markdown 表格
        if '<table' in text.lower():
            md = MinerUParser._convert_html_table_to_markdown(text)
            return md
        return text

    @staticmethod
    def _convert_html_table_to_markdown(html_text: str) -> str:
        """解析 HTML <table> 并转为 Markdown 表格，解析失败则原样返回。"""
        # 提取所有 <tr>...</tr>
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html_text, re.I | re.S)
        if not rows:
            return html_text

        lines = []
        for i, row in enumerate(rows):
            # 提取 <td> 或 <th> 内容
            cells = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', row, re.I | re.S)
            if not cells:
                continue
            clean_cells = [re.sub(r'<[^>]+>', '', c).replace('\n', ' ').strip() for c in cells]
            lines.append('| ' + ' | '.join(clean_cells) + ' |')
            if i == 0:
                lines.append('| ' + ' | '.join('---' for _ in clean_cells) + ' |')

        return '\n'.join(lines) if lines else html_text

    @staticmethod
    def _is_html_garbage(text: str) -> bool:
        """检测文本是否为纯 HTML 碎片（标签占比过高）。"""
        text = text.strip()
        if not text:
            return False
        if not re.search(r'<\s*(table|tr|td|th|thead|tbody|colgroup|col|img|br|hr|div|span|p)\b', text, re.I):
            return False
        clean = re.sub(r'<[^>]+>', '', text).strip()
        ratio = len(clean) / max(len(text), 1)
        return ratio < 0.2

    @staticmethod
    def _collect_output_images(output_dir: Path, figures_tables: list[dict]) -> dict[str, bytes]:
        """解析阶段从 MinerU 输出目录读取图片字节，供 pipeline 上传 MinIO。"""
        import logging
        logger = logging.getLogger(__name__)

        image_data: dict[str, bytes] = {}
        output_dir = Path(output_dir)
        found = 0
        missed = 0

        for ft in figures_tables:
            if ft.get('type') != 'figure':
                continue
            img_path = ft.get('image_path')
            if not img_path:
                continue

            img_file = Path(img_path)
            if not img_file.is_absolute():
                img_file = output_dir / img_file
            if not img_file.is_file():
                candidates = list(output_dir.rglob(Path(img_path).name))
                if candidates:
                    img_file = candidates[0]
                else:
                    missed += 1
                    logger.warning('Image file not found: %s (searched in %s)', img_path, output_dir)
                    continue

            try:
                normalized_key = str(img_path).replace('\\', '/')
                image_data[normalized_key] = img_file.read_bytes()
                found += 1
            except Exception as e:
                missed += 1
                logger.warning('Failed to read image %s: %s', img_file, e)
                continue

        logger.info('Collected %d figure images (%d missed) from %s', found, missed, output_dir)

        # 兜底：扫描 MinerU 输出目录中的图片文件（部分 figure 无 image_path 或路径不一致）
        if output_dir.is_dir():
            seen_names = {Path(k).name for k in image_data}
            for pattern in ('*.png', '*.jpg', '*.jpeg', '*.webp', '*.gif'):
                for img_file in output_dir.rglob(pattern):
                    if not img_file.is_file():
                        continue
                    name = img_file.name
                    if name in seen_names:
                        continue
                    try:
                        rel = str(img_file.relative_to(output_dir)).replace('\\', '/')
                        image_data[rel] = img_file.read_bytes()
                        image_data[name] = image_data[rel]
                        seen_names.add(name)
                        found += 1
                    except Exception as e:
                        logger.debug('Skip orphan image %s: %s', img_file, e)

        return image_data

    # ============================================================

    def _extract_metadata(self, markdown_text: str, content_items: list[dict], filename: str) -> dict:
        title = ''

        for item in content_items[:20]:
            text = normalize_text(str(item.get('content') or ''))
            if item.get('item_type') == 'heading' and len(text) >= 8:
                if not re.search(r'^(abstract|摘要|keywords?|关键词|关键字|index terms)\b', text, flags=re.I):
                    title = text.strip('# ').strip()
                    break

        if not title:
            for line in markdown_text.splitlines()[:80]:
                line = normalize_text(line.strip('#').strip())
                if not line or line.startswith('!['):
                    continue
                if re.search(r'^(abstract|摘要|keywords?|关键词|关键字|index terms)\b', line, flags=re.I):
                    continue
                if len(line) >= 8:
                    title = line
                    break

        return {
            'title': title or filename,
            'authors': [],
            'keywords': self._extract_keywords(markdown_text, content_items, title),
            'abstract': self._extract_abstract(content_items),
        }

    def _extract_abstract(self, content_items: list[dict]) -> str:
        for idx, item in enumerate(content_items):
            text = item.get('content') or ''
            if item.get('item_type') == 'heading' and re.search(r'摘要|abstract', text, flags=re.I):
                parts = []
                for nxt in content_items[idx + 1:]:
                    if nxt.get('item_type') == 'heading':
                        break
                    if nxt.get('content'):
                        parts.append(nxt['content'])
                return normalize_text('\n'.join(parts))

        for item in content_items[:40]:
            text = item.get('content') or ''
            if re.match(r'^(摘要|Abstract)\s*[:：]', text, flags=re.I):
                return normalize_text(re.sub(r'^(摘要|Abstract)\s*[:：]\s*', '', text, flags=re.I))
        return ''

    def _extract_keywords(self, markdown_text: str, content_items: list[dict], title: str) -> list[str]:
        candidates: list[str] = []

        for idx, item in enumerate(content_items):
            text = normalize_text(str(item.get('content') or ''))
            if item.get('item_type') == 'heading' and re.search(
                r'keywords?|index\s+terms|关键词|关键字',
                text,
                flags=re.I,
            ):
                keyword_text = ''
                for nxt in content_items[idx + 1: idx + 6]:
                    if nxt.get('item_type') == 'heading':
                        break
                    nxt_text = str(nxt.get('content') or '')
                    if self._KEYWORD_STOP_RE.search(nxt_text):
                        break
                    keyword_text += nxt_text + ' '
                if keyword_text.strip():
                    candidates.append(keyword_text.strip())

        for idx, item in enumerate(content_items):
            text = normalize_text(str(item.get('content') or ''))
            if re.match(r'^(keywords?|关键词|关键字)\s*[:：]', text, flags=re.I):
                remaining_text = text
                for nxt in content_items[idx + 1: idx + 4]:
                    if nxt.get('item_type') == 'heading':
                        break
                    nxt_text = str(nxt.get('content') or '')
                    if self._KEYWORD_STOP_RE.search(nxt_text):
                        break
                    remaining_text += ' ' + nxt_text
                candidates.append(remaining_text)

        if not candidates:
            patterns = [
                r'(?:keywords?|index\s+terms)\s*[:：]\s*([^$\n]+?)(?=\n\n|\n[A-Z]|\n\*\s|$)',
                r'(?:关键词|关键字)\s*[:：]\s*([^$\n]+?)(?=\n\n|\n[A-Z]|\n\*\s|$)',
            ]
            for pattern in patterns:
                for match in re.finditer(pattern, markdown_text, flags=re.I):
                    candidates.append(match.group(1))

        joined = '；'.join(candidates)

        if not joined:
            joined = self._extract_keywords_from_content(content_items, title)

        if not joined:
            abstract = self._extract_abstract(content_items)
            joined = self._extract_keywords_with_llm(title, abstract)

        if not joined:
            return []

        joined = self._KEYWORD_PREFIX_RE.sub('', joined)

        joined = re.sub(
            r'\b(CCS Concepts|ACM Reference Format|Additional Key Words|Acknowledgments?|Acknowledgements?).*',
            '',
            joined,
            flags=re.I | re.S,
        )

        for stop_pattern in [
            r'\*\s*The\s+authors.*',
            r'\*\s*This\s+work.*',
            r'\*\s*We\s+thank.*',
            r'Acknowledgments?.*',
            r'Acknowledgements?.*',
            r'Funding.*',
            r'Supported\s+by.*',
            r'Corresponding\s+author.*',
            r'通讯作者.*',
            r'致谢.*',
            r'基金项目.*',
            r'资助项目.*',
        ]:
            joined = re.sub(stop_pattern, '', joined, flags=re.I | re.S)

        raw_terms = re.split(r'[;；,，、\n]+', joined)
        result: list[str] = []
        seen: set[str] = set()

        for term in raw_terms:
            term = self._clean_keyword_term(term)
            if not term or len(term) > 80:
                continue

            if self._is_bad_keyword(term):
                continue

            key = term.lower()
            if key not in seen:
                result.append(term)
                seen.add(key)

            if len(result) >= 12:
                break

        return result

    def _clean_keyword_term(self, term: str) -> str:
        term = normalize_text(term.strip(' .;；,，:：'))
        term = self._KEYWORD_PREFIX_RE.sub('', term)
        term = re.sub(r'^\*\s*', '', term)
        term = re.sub(r'\s+', ' ', term)
        term = re.sub(r'\b(?:The|the|A|a|An|an)\s+', '', term)
        term = re.sub(r'\s+\b(?:and|or|et|al)\b', '', term, flags=re.I)
        term = re.sub(r'\*+', '', term)
        term = re.sub(r'^-+|-+$', '', term)
        term = re.sub(r'^["\']+|["\']+$', '', term)
        term = re.sub(r'\b(?:et\s+al\.?|etc\.?|etc)\b', '', term, flags=re.I)
        term = term.strip()
        return term

    def _is_bad_keyword(self, term: str) -> bool:
        term_lower = term.lower()

        if term_lower in self._CHINESE_STOP_WORDS or term_lower in self._ENGLISH_STOP_WORDS:
            return True

        if re.search(r'^(作者|author|致谢|acknowledgment|funding|grant|doi|https?://)', term_lower):
            return True

        if re.search(r'\b(university|institute|school|department|laboratory|college)\b', term_lower):
            return True

        if re.search(r'@\w+', term):
            return True

        if len(term) == 1:
            return True

        if re.search(r'^\d+$', term):
            return True

        return False

    def _extract_keywords_from_content(self, content_items: list[dict], title: str) -> str:
        title_text = title or ''
        abstract_text = ''
        heading_text = ''
        paragraph_text = ''

        for item in content_items[:150]:
            text = normalize_text(str(item.get('content') or ''))
            if not text:
                continue

            if item.get('item_type') == 'heading':
                if item.get('level') == 1 and not title_text:
                    title_text = text
                elif re.search(r'摘要|abstract', text, flags=re.I):
                    continue
                else:
                    heading_text += text + ' '
            elif re.match(r'^(摘要|Abstract)\s*[:：]', text, flags=re.I):
                abstract_text = text + ' '
            elif item.get('item_type') == 'paragraph' and len(paragraph_text) < 3000:
                paragraph_text += text[:800] + ' '

        all_text = title_text + ' ' + abstract_text + ' ' + heading_text + ' ' + paragraph_text
        return self._extract_keywords_from_text(all_text)

    def _extract_keywords_from_text(self, text: str) -> str:
        text = normalize_text(text)
        if not text:
            return ''

        keywords = []
        seen = set()

        cn_keywords = self._extract_cn_keywords_jieba(text)
        for kw in cn_keywords:
            if kw.lower() not in seen:
                keywords.append(kw)
                seen.add(kw.lower())

        en_keywords = self._extract_en_keywords(text)
        for kw in en_keywords:
            if kw.lower() not in seen:
                keywords.append(kw)
                seen.add(kw.lower())

        return '，'.join(keywords[:12])

    def _extract_cn_keywords_jieba(self, text: str) -> list[str]:
        try:
            import jieba
            import jieba.posseg as pseg

            keywords = []
            seen = set()

            words = pseg.lcut(text)
            for word, flag in words:
                word = word.strip()
                if not word:
                    continue

                if flag.startswith('n') and len(word) >= 2:
                    if word.lower() not in seen and word not in self._CHINESE_STOP_WORDS:
                        keywords.append(word)
                        seen.add(word.lower())

            return keywords[:10]
        except Exception:
            return self._extract_cn_keywords_fallback(text)

    def _extract_cn_keywords_fallback(self, text: str) -> list[str]:
        cn_pattern = r'[\u4e00-\u9fa5]{2,8}'
        cn_matches = re.findall(cn_pattern, text)

        cn_counter: dict[str, int] = {}
        for word in cn_matches:
            if word.lower() not in self._CHINESE_STOP_WORDS and len(word) >= 2:
                cn_counter[word] = cn_counter.get(word, 0) + 1

        cn_sorted = sorted(cn_counter.items(), key=lambda x: x[1], reverse=True)[:10]
        return [k for k, v in cn_sorted]

    def _extract_en_keywords(self, text: str) -> list[str]:
        keywords = []
        seen = set()

        noun_pattern = r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}'
        matches = re.findall(noun_pattern, text)

        for match in matches:
            match = match.strip()
            if not match:
                continue

            words = match.split()
            if all(w.lower() not in self._ENGLISH_STOP_WORDS for w in words):
                if match.lower() not in seen:
                    keywords.append(match)
                    seen.add(match.lower())

        en_pattern = r'\b[A-Z][a-zA-Z0-9_-]{2,18}\b'
        single_matches = re.findall(en_pattern, text)
        for match in single_matches:
            if match.lower() not in seen and match.lower() not in self._ENGLISH_STOP_WORDS:
                keywords.append(match)
                seen.add(match.lower())

        filtered_keywords = []
        for kw in keywords:
            kw_lower = kw.lower()
            kw_words = kw.split()
            
            is_all_names = all(
                w.lower() in self._ENGLISH_STOP_WORDS or (len(w) <= 6 and w.istitle())
                for w in kw_words
            )
            
            if len(kw_words) == 1 and len(kw) <= 5 and kw.isalpha() and kw.istitle():
                continue
            
            if kw_lower in self._ENGLISH_STOP_WORDS:
                continue
            
            filtered_keywords.append(kw)

        return filtered_keywords[:10]

    def _extract_keywords_with_llm(self, title: str, abstract: str) -> str:
        if not title and not abstract:
            return ''

        try:
            from app.integrations.llm.openai_compatible import OpenAICompatibleLLM

            llm = OpenAICompatibleLLM(scenario='parse')
            prompt = f"""请根据以下论文信息提取最多10个关键词。
标题：{title}
摘要：{abstract}

要求：
1. 只输出关键词，用英文逗号分隔
2. 关键词要具有代表性，避免虚词
3. 中英文关键词均可
4. 不要包含"关键词"、"Keywords"等标签"""

            response = llm.chat([{'role': 'user', 'content': prompt}], temperature=0.1, max_tokens=200)
            return response.strip()
        except Exception:
            return ''

    def _extract_authors(self, markdown_text: str, title: str) -> list[str]:
        lines = [
            normalize_text(x.strip())
            for x in markdown_text.splitlines()[:80]
            if normalize_text(x.strip())
        ]
        if not lines:
            return []

        start = 0
        if title:
            for i, line in enumerate(lines[:30]):
                if title.lower() in line.lower() or line.lower() in title.lower():
                    start = i + 1
                    break

        author_lines = []
        for line in lines[start:start + 12]:
            if re.search(r'^(abstract|摘要|keywords?|关键词|关键字|index terms|introduction)\b', line, flags=re.I):
                break
            if '@' in line or re.search(
                r'\b(university|institute|school|department|laboratory|college)\b',
                line,
                flags=re.I,
            ):
                continue
            if 2 <= len(line) <= 250:
                author_lines.append(line)

        if not author_lines:
            return []

        text = ' '.join(author_lines[:3])
        text = re.sub(r'\d+|[*\u2020\u2021\u00a7]|\([^)]*\)', ' ', text)

        parts = re.split(r'\s*,\s*|\s+and\s+|；|;|、', text)
        authors = []
        seen = set()

        for part in parts:
            part = normalize_text(part.strip())
            if not part or len(part) > 60:
                continue
            if re.search(
                r'\b(abstract|keywords|university|institute|department|school)\b',
                part,
                flags=re.I,
            ):
                continue
            key = part.lower()
            if key not in seen:
                authors.append(part)
                seen.add(key)

            if len(authors) >= 20:
                break

        return authors

    def _post_process_items(self, items: list[dict]) -> list[dict]:
        cleaned_items = []

        for item in items:
            if item.get('item_type') not in ('paragraph', 'heading', 'list', 'abstract'):
                cleaned_items.append(item)
                continue

            text = str(item.get('content', '')).strip()
            if not text:
                continue

            if self._is_html_garbage(text):
                order_idx = item.get('order_index', 999)
                if isinstance(order_idx, (int, float)) and order_idx < 15:
                    continue

            text_no_space = text.replace(' ', '').replace('\n', '').replace('\r', '')
            if len(text_no_space) < 200:
                if self._THESIS_JUNK_RE.search(text_no_space):
                    continue
                if len(text_no_space) < 30 and re.match(
                    r'^(分类号|UDC|密级|学校代码|学号|指导教师|专业名称|学位类别|作者姓名|学院|答辩委员会|答辩日期|原创性声明|授权使用说明)',
                    text_no_space,
                ):
                    continue
                if len(text) < 15 and not re.search(r'[。！？：:;.!?]$', text) and (
                    '学位' in text or text in ['公开', '保密', '内部']
                ):
                    continue

            if re.search(r'(?:\.{3,}|\u2026{2,})\s*\d+$', text):
                continue
            if re.match(r'^(目录|Contents?|图目录|表目录)$', text, re.I):
                continue

            if item.get('item_type') in ('paragraph', 'list') and len(text) < 100 and not re.search(r'[。！？;.!?]$', text):
                if re.match(r'^第[一二三四五六七八九十\d]+章\s*[\u4e00-\u9fa5a-zA-Z]', text):
                    item['item_type'] = 'heading'
                    item['level'] = 1
                elif re.match(r'^\d+\.\d+\.\d+\s*[\u4e00-\u9fa5a-zA-Z]', text):
                    item['item_type'] = 'heading'
                    item['level'] = 3
                elif re.match(r'^\d+\.\d+\s*[\u4e00-\u9fa5a-zA-Z]', text):
                    item['item_type'] = 'heading'
                    item['level'] = 2
                elif re.match(r'^\d+\.\s+[\u4e00-\u9fa5a-zA-Z]', text):
                    item['item_type'] = 'heading'
                    item['level'] = 1
                elif re.match(r'^[IVX]+\.\s+[A-Z\s]+$', text):
                    item['item_type'] = 'heading'
                    item['level'] = 1

            item['content'] = text
            cleaned_items.append(item)

        # ---------- 2.4 修复 MinerU 切割错误的行内定界符 ----------
        for item in cleaned_items:
            if item.get('item_type') not in ('paragraph', 'list', 'table'):
                continue
            content = item.get('content', '')
            if '$$' in content and '$' in content:
                item['content'] = re.sub(
                    r'(\$[^$\n]*?)\$\$(\\[a-zA-Z]+)',
                    r'\1$ $\2',
                    content,
                )

        # ---------- 2.5 公式升维：检测被 MinerU 误判为 paragraph 的 LaTeX 公式 ----------
        for item in cleaned_items:
            if item.get('item_type') not in ('paragraph', 'list'):
                continue

            content = item.get('content', '').strip()
            if not content:
                continue

            # MinerU 已输出完整 $$...$$ 包裹，只需升维并规范化 LaTeX
            if content.startswith('$$') and content.endswith('$$'):
                inner = self._normalize_latex_for_katex(content[2:-2])
                item['content'] = f'$$\n{inner}\n$$'
                item['item_type'] = 'formula'
                continue

            # 无 $$ 包裹但有 LaTeX 命令 → 补包裹后升维（跳过中英文混排 / 行内公式段落）
            if self._should_upgrade_paragraph_to_formula(content):
                content = self._ORPHAN_CLOSING_RE.sub('', content).strip()
                content = self._normalize_latex_for_katex(content)

                if content.count(r'\tag') > 1:
                    content = re.sub(r'(\\tag\{[^}]+\})\s*', r'\1 \\\\ \n', content)
                    content = re.sub(r' \\\\ \n$', '\n', content)
                    item['content'] = '$$\n\\begin{align}\n' + content + '\\end{align}\n$$'
                else:
                    item['content'] = '$$\n' + content + '\n$$'

                item['item_type'] = 'formula'

        final_items = []
        for item in cleaned_items:
            curr_type = item.get('item_type')

            if final_items and curr_type in ('paragraph', 'list') and final_items[-1].get('item_type') in (
            'paragraph', 'list'):
                prev_text = final_items[-1]['content'].strip()
                curr_text = item['content'].strip()

                ends_without_period = not re.search(r'[。！？：:;.!?]["\u201c\u201d\'\u2019\)\]）】]?$', prev_text)
                starts_with_citation = bool(re.match(r'^\[\s*\d+(?:\s*[,，\-]\s*\d+)*\]', curr_text))
                is_standalone_citation = bool(re.match(r'^\[\s*\d+(?:\s*[,，\-]\s*\d+)*\][。！？.!?]?$', curr_text))
                starts_with_lowercase = bool(re.match(r'^[a-z]', curr_text))

                prev_is_cn_ref = bool(self._CN_REF_PATTERN.search(prev_text))
                curr_is_cn_ref_continuation = bool(
                    not re.match(r'^\[\s*\d+', curr_text)
                    and (
                        re.search(r'[JDCMPN]\s*[\.。]', curr_text)
                        or re.search(r'\d{4}[,，]\s*\d+', curr_text)
                        or re.search(r'(in Chinese|\(in Chinese\)|doi:|DOI:)', curr_text, re.I)
                    )
                )

                prev_is_en_ref = bool(
                    self._EN_REF_PATTERN.search(prev_text)
                    and not prev_is_cn_ref
                )
                curr_is_en_ref_continuation = bool(
                    not re.match(r'^\[\s*\d+', curr_text)
                    and self._EN_REF_CONTINUATION_RE.search(curr_text)
                )

                should_merge = False

                if ends_without_period:
                    should_merge = True
                elif starts_with_citation or is_standalone_citation:
                    should_merge = True
                elif starts_with_lowercase:
                    should_merge = True
                elif prev_is_cn_ref and ends_without_period:
                    should_merge = True
                elif prev_is_cn_ref and curr_is_cn_ref_continuation:
                    should_merge = True
                elif prev_is_en_ref and ends_without_period:
                    should_merge = True
                elif prev_is_en_ref and curr_is_en_ref_continuation:
                    should_merge = True

                if should_merge:
                    final_items[-1]['item_type'] = 'paragraph'
                    if not final_items[-1].get('page_number') and item.get('page_number'):
                        final_items[-1]['page_number'] = item.get('page_number')
                    if not final_items[-1].get('bbox') and item.get('bbox'):
                        final_items[-1]['bbox'] = item.get('bbox')
                    if re.search(r'[a-zA-Z0-9]$', prev_text) and re.match(r'^[a-zA-Z0-9\[\(]', curr_text):
                        final_items[-1]['content'] = f"{prev_text} {curr_text}"
                    else:
                        final_items[-1]['content'] = f"{prev_text}{curr_text}"
                    continue

            final_items.append(item)

        return final_items

    def _stringify_mineru_value(self, value) -> str:
        if value is None:
            return ''
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return '\n'.join(self._stringify_mineru_value(x) for x in value if x is not None)
        if isinstance(value, dict):
            if value.get('list_items'):
                return self._render_list_content(value)
            if 'item_content' in value:
                return self._render_rich_content(value.get('item_content'))
            for key in ('math_content', 'text', 'content', 'html', 'caption'):
                if key in value:
                    return self._stringify_mineru_value(value.get(key))
            for key in (
                'page_header_content',
                'page_footer_content',
                'page_number_content',
                'title_content',
                'paragraph_content',
            ):
                if key in value:
                    return self._render_rich_content(value.get(key))
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    def _parse_pages_with_pymupdf(self, pdf_bytes: bytes) -> list[dict]:
        try:
            doc = fitz.open(stream=pdf_bytes, filetype='pdf')
            pages = [
                {'page_number': i, 'text': normalize_text(page.get_text('text'))}
                for i, page in enumerate(doc, start=1)
            ]
            doc.close()
            return pages
        except Exception:
            return []

    def _safe_filename(self, filename: str) -> str:
        name = Path(filename or 'input.pdf').name
        name = re.sub(r'[^\w.\-()\u4e00-\u9fa5]+', '_', name)
        if not name.lower().endswith('.pdf'):
            name = f'{name}.pdf'
        return name

    def _to_int(self, value, default: int) -> int:
        try:
            return int(value)
        except Exception:
            return default
