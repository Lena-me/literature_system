from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Tuple

from app.core.config import get_settings
from app.integrations.llm.openai_compatible import OpenAICompatibleLLM

settings = get_settings()
logger = logging.getLogger(__name__)

# 常用标签 -> (primary, secondary, tertiary)
SUBJECT_TAXONOMY: dict[str, Tuple[str, str | None, str | None]] = {
    '计算机科学': ('计算机科学', '人工智能', None),
    '人工智能': ('计算机科学', '人工智能', None),
    '机器学习': ('计算机科学', '人工智能', '机器学习'),
    '深度学习': ('计算机科学', '人工智能', '深度学习'),
    '自然语言处理': ('计算机科学', '人工智能', '自然语言处理'),
    '计算机视觉': ('计算机科学', '人工智能', '计算机视觉'),
    '数据挖掘': ('计算机科学', '数据科学', '数据挖掘'),
    '知识图谱': ('计算机科学', '人工智能', '知识图谱'),
    '推荐系统': ('计算机科学', '人工智能', '推荐系统'),
    '信息检索': ('计算机科学', '信息科学', '信息检索'),
    '软件工程': ('计算机科学', '软件工程', None),
    '数据库': ('计算机科学', '计算机系统', '数据库'),
    '分布式系统': ('计算机科学', '计算机系统', '分布式系统'),
    '网络安全': ('计算机科学', '网络安全', None),
    '生物信息学': ('生物学', '生物信息学', None),
    '医学影像': ('医学', '医学影像', None),
    '信号处理': ('工程学', '电子工程', '信号处理'),
    '通信技术': ('工程学', '电子工程', '通信技术'),
    '控制工程': ('工程学', '控制科学', '控制工程'),
    '机器人': ('工程学', '自动化', '机器人'),
    '量子计算': ('物理学', '量子信息', '量子计算'),
    '物理学': ('物理学', '应用物理', None),
    '化学': ('化学', '应用化学', None),
    '材料科学': ('材料科学', '材料工程', None),
    '能源科学': ('能源科学', '能源工程', None),
    '环境科学': ('环境科学', '环境工程', None),
    '数学': ('数学', '应用数学', None),
    '统计学': ('数学', '统计学', None),
    '经济学': ('经济学', '应用经济', None),
    '管理学': ('管理学', '组织管理', None),
    '教育学': ('教育学', '教育研究', None),
    '心理学': ('心理学', '应用心理', None),
    '社会学': ('社会学', '社会研究', None),
    '法学': ('法学', '应用法学', None),
    '文学': ('文学', '文学研究', None),
    '历史学': ('历史学', '历史研究', None),
    '哲学': ('哲学', '哲学研究', None),
    '艺术学': ('艺术学', '艺术创作', None),
    '体育科学': ('体育科学', '运动科学', None),
    '健康科学': ('医学', '健康科学', None),
    '工程学': ('工程学', '工程技术', None),
    '医学': ('医学', '临床医学', None),
    '生物学': ('生物学', '生命科学', None),
}

# 顶级领域在缺少下级时，结合标题关键词推断二级方向
TITLE_SECONDARY_HINTS: dict[str, list[tuple[tuple[str, ...], str]]] = {
    '材料科学': [
        (('纳米', 'nanomat', '二维材料'), '纳米材料'),
        (('复合', 'composite'), '复合材料'),
        (('高分子', 'polymer', '聚合物'), '高分子材料'),
        (('金属', 'metal', '合金'), '金属材料'),
        (('陶瓷', 'ceramic'), '陶瓷材料'),
        (('半导体', 'semiconductor'), '半导体材料'),
    ],
    '工程学': [
        (('机械', 'mechanical', '机床'), '机械工程'),
        (('土木', 'civil', '结构'), '土木工程'),
        (('电气', 'electric', '电力'), '电气工程'),
        (('化工', 'chemical process'), '化学工程'),
        (('航空', '航天', 'aero'), '航空航天工程'),
    ],
    '物理学': [
        (('凝聚态', 'condensed'), '凝聚态物理'),
        (('光学', 'optics', '激光'), '光学'),
        (('粒子', 'particle'), '粒子物理'),
        (('天体', 'astro'), '天体物理'),
    ],
    '化学': [
        (('有机', 'organic'), '有机化学'),
        (('无机', 'inorganic'), '无机化学'),
        (('分析', 'analytical'), '分析化学'),
        (('物理化学', 'physical chem'), '物理化学'),
    ],
    '医学': [
        (('临床', 'clinical'), '临床医学'),
        (('影像', 'imaging', '超声', 'mri', 'ct'), '医学影像'),
        (('肿瘤', 'cancer', 'oncology'), '肿瘤学'),
        (('神经', 'neuro'), '神经医学'),
    ],
    '计算机科学': [
        (('图像', '视觉', 'vision', '去噪', 'segmentation'), '计算机视觉'),
        (('nlp', '文本', '语言', 'translation', 'bert'), '自然语言处理'),
        (('推荐', 'recommend'), '推荐系统'),
        (('知识图谱', 'graph'), '知识图谱'),
        (('网络', 'security', '安全'), '网络安全'),
        (('数据库', 'database', 'sql'), '数据库'),
    ],
}

# 宽泛顶级领域在无法从标题/同批标签推断时的二级兜底（保证至少两级）
BROAD_DEFAULT_SECONDARY: dict[str, str] = {
    '计算机科学': '人工智能',
    '材料科学': '材料工程',
    '工程学': '工程技术',
    '物理学': '应用物理',
    '化学': '应用化学',
    '医学': '临床医学',
    '生物学': '生命科学',
    '体育科学': '运动科学',
    '能源科学': '能源工程',
    '环境科学': '环境工程',
    '数学': '应用数学',
    '经济学': '应用经济',
    '管理学': '组织管理',
    '教育学': '教育研究',
    '心理学': '应用心理',
    '社会学': '社会研究',
    '法学': '应用法学',
    '文学': '文学研究',
    '历史学': '历史研究',
    '哲学': '哲学研究',
    '艺术学': '艺术创作',
}

_BROAD_PRIMARIES = frozenset(BROAD_DEFAULT_SECONDARY.keys())

# 未知标签的二级兜底
_UNKNOWN_SECONDARY = '综合研究'


def _nullish(value: Any) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    return text == '' or text.lower() in {'null', 'none', 'undefined', 'nan'}


def _normalize_label(label: str) -> str:
    return str(label or '').strip()


def _lookup_taxonomy(label: str) -> Tuple[str, str | None, str | None] | None:
    key = _normalize_label(label)
    if not key:
        return None
    if key in SUBJECT_TAXONOMY:
        return SUBJECT_TAXONOMY[key]
    for known, path in SUBJECT_TAXONOMY.items():
        if key in known or known in key:
            return path
    return None


def _build_path(primary: str, secondary: str | None, tertiary: str | None) -> str:
    parts = [primary]
    if secondary:
        parts.append(secondary)
    if tertiary:
        parts.append(tertiary)
    return '/'.join(parts)


def _infer_secondary_from_title(primary: str, title: str) -> str | None:
    if not title:
        return None
    lowered = title.lower()
    for keywords, secondary in TITLE_SECONDARY_HINTS.get(primary, []):
        if any(kw.lower() in lowered for kw in keywords):
            return secondary
    return None


def _apply_taxonomy_to_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """taxonomy 为权威来源：已知标签完全按映射表覆盖 LLM 结果。"""
    label = _normalize_label(item['subject_label'])
    tax = _lookup_taxonomy(label)

    if tax:
        primary, secondary, tertiary = tax
    else:
        primary = _normalize_label(item.get('primary_domain', '')) or label
        secondary = None if _nullish(item.get('secondary_domain')) else _normalize_label(item['secondary_domain'])
        tertiary = None if _nullish(item.get('tertiary_domain')) else _normalize_label(item['tertiary_domain'])

    item['primary_domain'] = primary
    item['secondary_domain'] = secondary
    item['tertiary_domain'] = tertiary
    item['domain_path'] = _build_path(primary, secondary, tertiary)
    return item


def _resolve_secondary(
    primary: str,
    label: str,
    paper_title: str,
    peer_secondaries: list[str],
) -> str:
    """按优先级推断 secondary_domain，保证有返回值。"""
    inferred = _infer_secondary_from_title(primary, paper_title)
    if inferred:
        return inferred

    if peer_secondaries:
        counts: dict[str, int] = {}
        for s in peer_secondaries:
            counts[s] = counts.get(s, 0) + 1
        return max(counts.items(), key=lambda x: x[1])[0]

    if label != primary:
        return label

    return BROAD_DEFAULT_SECONDARY.get(primary) or _UNKNOWN_SECONDARY


def _enrich_from_batch_peers(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """同篇文献内：用更细标签的路径补全缺少二级的条目。"""
    specific_paths: list[tuple[str, str | None, str | None]] = []
    all_secondaries: list[str] = []
    for item in items:
        p = item['primary_domain']
        s = item.get('secondary_domain')
        t = item.get('tertiary_domain')
        if s:
            specific_paths.append((p, s, t))
            all_secondaries.append(s)

    if not specific_paths:
        return items

    secondary_by_primary: dict[str, dict[str, int]] = {}
    for p, s, _t in specific_paths:
        if not s:
            continue
        secondary_by_primary.setdefault(p, {})
        secondary_by_primary[p][s] = secondary_by_primary[p].get(s, 0) + 1

    for item in items:
        if item.get('secondary_domain'):
            continue
        primary = item['primary_domain']
        label = item['subject_label']
        counts = secondary_by_primary.get(primary)
        if counts:
            dominant_secondary = max(counts.items(), key=lambda x: x[1])[0]
        else:
            tax = _lookup_taxonomy(label)
            if tax and tax[1]:
                dominant_secondary = tax[1]
            else:
                dominant_secondary = _resolve_secondary(primary, label, '', all_secondaries)
        item['secondary_domain'] = dominant_secondary
        tax = _lookup_taxonomy(label)
        if tax and tax[2] and not item.get('tertiary_domain'):
            item['tertiary_domain'] = tax[2]
        item['domain_path'] = _build_path(primary, item['secondary_domain'], item.get('tertiary_domain'))
    return items


def _enforce_minimum_depth(items: List[Dict[str, Any]], paper_title: str) -> List[Dict[str, Any]]:
    """强制每条记录必须存在 secondary_domain。"""
    peer_secondaries = [s for item in items if (s := item.get('secondary_domain'))]
    for item in items:
        if item.get('secondary_domain'):
            continue
        primary = item['primary_domain']
        label = item['subject_label']
        item['secondary_domain'] = _resolve_secondary(primary, label, paper_title, peer_secondaries)
        item['domain_path'] = _build_path(primary, item['secondary_domain'], item.get('tertiary_domain'))
        peer_secondaries.append(item['secondary_domain'])
    return items


def _force_secondary_required(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """最终校验：绝不允许 secondary_domain 为空。"""
    for item in items:
        if item.get('secondary_domain'):
            continue
        primary = item['primary_domain']
        label = item['subject_label']
        fallback = BROAD_DEFAULT_SECONDARY.get(primary) or (label if label != primary else _UNKNOWN_SECONDARY)
        logger.warning(
            'subject hierarchy missing secondary: label=%s primary=%s, forced=%s',
            label, primary, fallback,
        )
        item['secondary_domain'] = fallback
        item['domain_path'] = _build_path(primary, fallback, item.get('tertiary_domain'))
    return items


def _enrich_from_title(items: List[Dict[str, Any]], paper_title: str) -> List[Dict[str, Any]]:
    if not paper_title:
        return items
    for item in items:
        if item.get('secondary_domain'):
            continue
        primary = item['primary_domain']
        if primary not in _BROAD_PRIMARIES:
            continue
        inferred = _infer_secondary_from_title(primary, paper_title)
        if inferred:
            item['secondary_domain'] = inferred
            if item['subject_label'] == primary and _lookup_taxonomy(inferred):
                tax = _lookup_taxonomy(inferred)
                if tax and tax[2]:
                    item['tertiary_domain'] = tax[2]
            item['domain_path'] = _build_path(primary, item.get('secondary_domain'), item.get('tertiary_domain'))
    return items


class SubjectHierarchyAnalyzer:
    def __init__(self):
        self.llm = OpenAICompatibleLLM(scenario='parse') if settings.enable_llm_extract else None

    def analyze_hierarchy(self, subject_labels: List[str], paper_title: str = "") -> List[Dict[str, Any]]:
        """以 taxonomy 规则为主构建层级；LLM 仅辅助 is_core，不再决定 primary/secondary。"""
        if not subject_labels:
            return []

        base_items = self._build_authoritative_hierarchy(subject_labels)
        core_map = self._fetch_llm_core_flags(subject_labels, paper_title)
        if core_map:
            for item in base_items:
                label = item['subject_label']
                if label in core_map:
                    item['is_core'] = core_map[label]

        return self._finalize_hierarchy(base_items, paper_title)

    def _build_authoritative_hierarchy(self, subject_labels: List[str]) -> List[Dict[str, Any]]:
        """仅依据标签名 + taxonomy 构建层级（不依赖 LLM 结构输出）。"""
        return self._fallback_hierarchy(subject_labels)

    def _fetch_llm_core_flags(self, subject_labels: List[str], paper_title: str) -> dict[str, bool]:
        if not self.llm or not subject_labels:
            return {}

        labels_str = json.dumps(subject_labels, ensure_ascii=False)
        prompt = """判断下列学科标签对该文献是否为核心标签（is_core）。
论文标题：{title}
标签：{labels}

规则：与主题高度相关为核心(true)，弱相关/背景引用为非核心(false)。
只输出 JSON 数组，每项含 subject_label 与 is_core，不要输出层级字段。

示例：[{{"subject_label":"深度学习","is_core":true}},{{"subject_label":"哲学","is_core":false}}]""".format(
            title=paper_title or '无', labels=labels_str,
        )

        try:
            text = self.llm.chat(
                [{'role': 'system', 'content': '你只输出可解析JSON。'},
                 {'role': 'user', 'content': prompt}],
                temperature=0.0,
                max_tokens=800,
            )
        except Exception as e:
            logger.error(f'LLM is_core 分析失败: {e}')
            return {}

        clean = text.strip()
        if clean.startswith('```json'):
            clean = clean[7:]
        if clean.endswith('```'):
            clean = clean[:-3]

        data = None
        try:
            data = json.loads(clean)
        except Exception:
            match = re.search(r'\[.*\]', clean, flags=re.S)
            if match:
                try:
                    data = json.loads(match.group(0))
                except Exception:
                    pass

        if not isinstance(data, list):
            return {}

        core_map: dict[str, bool] = {}
        for item in data:
            if isinstance(item, dict) and item.get('subject_label') is not None:
                core_map[_normalize_label(item['subject_label'])] = bool(item.get('is_core', True))
        return core_map

    def _finalize_hierarchy(
        self,
        items: List[Dict[str, Any]],
        paper_title: str,
    ) -> List[Dict[str, Any]]:
        enriched = [_apply_taxonomy_to_item(dict(item)) for item in items]
        enriched = _enrich_from_batch_peers(enriched)
        enriched = _enrich_from_title(enriched, paper_title)
        enriched = _enforce_minimum_depth(enriched, paper_title)
        enriched = _force_secondary_required(enriched)
        return enriched

    def _fallback_hierarchy(self, subject_labels: List[str]) -> List[Dict[str, Any]]:
        """降级：基于内置 taxonomy 构建多级路径。"""
        result = []
        for label in subject_labels:
            label = _normalize_label(label)
            if not label:
                continue
            tax = _lookup_taxonomy(label)
            if tax:
                primary, secondary, tertiary = tax
            else:
                primary, secondary, tertiary = label, None, None
            result.append({
                'subject_label': label,
                'primary_domain': primary,
                'secondary_domain': secondary,
                'tertiary_domain': tertiary,
                'domain_path': _build_path(primary, secondary, tertiary),
                'is_core': True,
            })
        return result
