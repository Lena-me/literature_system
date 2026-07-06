from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List

from app.core.config import get_settings
from app.integrations.llm.openai_compatible import OpenAICompatibleLLM
from app.utils.json_utils import loads

settings = get_settings()
logger = logging.getLogger(__name__)


class SubjectHierarchyAnalyzer:
    def __init__(self):
        self.llm = OpenAICompatibleLLM(scenario='parse') if settings.enable_llm_extract else None

    def analyze_hierarchy(self, subject_labels: List[str], paper_title: str = "") -> List[Dict[str, Any]]:
        """使用LLM分析学科层级关系。
        
        Args:
            subject_labels: 论文的学科标签列表
            paper_title: 论文标题，帮助LLM理解上下文
        
        Returns:
            层级分析结果列表，每个标签对应一条记录，包含：
            - subject_label: 原始标签
            - primary_domain: 顶级学科（如：计算机科学）
            - secondary_domain: 二级学科（如：人工智能）
            - tertiary_domain: 三级学科（如：深度学习）
            - domain_path: 完整路径（如：计算机科学/人工智能/深度学习）
            - is_core: 是否为核心标签（非噪音）
        """
        if self.llm is None:
            return self._fallback_hierarchy(subject_labels)

        if not subject_labels:
            return []

        labels_str = json.dumps(subject_labels, ensure_ascii=False)
        
        prompt = """你是一个学术学科分类专家。请对以下文献的学科标签进行层级分析。
        
论文标题（用于上下文理解）：{title}

待分析标签：{labels}

严格规则：
1. 只输出标准JSON，不要附带解释、问候语或Markdown代码块。
2. 每个标签必须分配到一个合理的学科层级体系中。
3. primary_domain（顶级学科）必须是广泛认可的学术大领域，如：计算机科学、物理学、化学、生物学、医学、数学、经济学、管理学、社会学、教育学、心理学、文学、历史学、哲学、艺术学、体育科学等。
4. secondary_domain（二级学科）是顶级学科下的主要分支领域。
5. tertiary_domain（三级学科）是二级学科下的细分研究方向。
6. 如果标签本身就是顶级学科，则secondary_domain和tertiary_domain为null。
7. 如果标签在某个学科领域内但无法确定更细的分类，则相应层级为null。
8. is_core字段表示该标签是否为论文的核心学科标签。如果标签与论文主题关联度很低（如偶然出现的跨学科引用），则设为false。
9. 注意区分真正的父子关系：
   - 计算机科学 -> 人工智能 -> 深度学习（正确的父子关系）
   - 计算机科学与哲学（并列关系，非父子）
   - 体育科学与社会学（并列关系，非父子）
10. 输出JSON必须包含以下全部字段，不得遗漏。

示例：
输入标签：["计算机科学", "人工智能", "深度学习", "哲学"]
输出：
[
    {{"subject_label": "计算机科学", "primary_domain": "计算机科学", "secondary_domain": null, "tertiary_domain": null, "domain_path": "计算机科学", "is_core": true}},
    {{"subject_label": "人工智能", "primary_domain": "计算机科学", "secondary_domain": "人工智能", "tertiary_domain": null, "domain_path": "计算机科学/人工智能", "is_core": true}},
    {{"subject_label": "深度学习", "primary_domain": "计算机科学", "secondary_domain": "人工智能", "tertiary_domain": "深度学习", "domain_path": "计算机科学/人工智能/深度学习", "is_core": true}},
    {{"subject_label": "哲学", "primary_domain": "哲学", "secondary_domain": null, "tertiary_domain": null, "domain_path": "哲学", "is_core": false}}
]

另一个示例：
输入标签：["体育科学", "健康科学", "社会学"]
输出：
[
    {{"subject_label": "体育科学", "primary_domain": "体育科学", "secondary_domain": null, "tertiary_domain": null, "domain_path": "体育科学", "is_core": true}},
    {{"subject_label": "健康科学", "primary_domain": "医学", "secondary_domain": "健康科学", "tertiary_domain": null, "domain_path": "医学/健康科学", "is_core": true}},
    {{"subject_label": "社会学", "primary_domain": "社会学", "secondary_domain": null, "tertiary_domain": null, "domain_path": "社会学", "is_core": false}}
]

请输出分析结果：""".format(title=paper_title or '无', labels=labels_str)

        try:
            text = self.llm.chat(
                [{'role': 'system', 'content': '你只输出可解析JSON。'},
                 {'role': 'user', 'content': prompt}],
                temperature=0.0,
                max_tokens=2000,
            )
        except Exception as e:
            logger.error(f'LLM学科层级分析失败: {e}')
            return self._fallback_hierarchy(subject_labels)

        clean = text.strip()
        if clean.startswith('```json'):
            clean = clean[7:]
        if clean.endswith('```'):
            clean = clean[:-3]
        
        try:
            data = json.loads(clean)
            if isinstance(data, list):
                return self._validate_hierarchy(data)
        except Exception:
            pass

        match = re.search(r'\[.*\]', clean, flags=re.S)
        if match:
            try:
                data = json.loads(match.group(0))
                if isinstance(data, list):
                    return self._validate_hierarchy(data)
            except Exception:
                pass

        logger.error(f'LLM学科层级分析结果解析失败: {clean[:500]}')
        return self._fallback_hierarchy(subject_labels)

    def _validate_hierarchy(self, data: List[Dict]) -> List[Dict[str, Any]]:
        """验证并清理层级数据"""
        result = []
        for item in data:
            if not isinstance(item, dict) or 'subject_label' not in item:
                continue
            subject_label = str(item['subject_label']).strip()
            if not subject_label:
                continue
            
            primary = str(item.get('primary_domain', '')).strip() or subject_label
            secondary = str(item.get('secondary_domain', '')).strip() or None
            tertiary = str(item.get('tertiary_domain', '')).strip() or None
            is_core = item.get('is_core', True)
            
            path_parts = [primary]
            if secondary:
                path_parts.append(secondary)
            if tertiary:
                path_parts.append(tertiary)
            domain_path = '/'.join(path_parts)
            
            result.append({
                'subject_label': subject_label,
                'primary_domain': primary,
                'secondary_domain': secondary,
                'tertiary_domain': tertiary,
                'domain_path': domain_path,
                'is_core': bool(is_core),
            })
        return result

    def _fallback_hierarchy(self, subject_labels: List[str]) -> List[Dict[str, Any]]:
        """降级方案：当LLM不可用时，每个标签视为独立的顶级学科"""
        result = []
        for label in subject_labels:
            label = str(label).strip()
            if not label:
                continue
            result.append({
                'subject_label': label,
                'primary_domain': label,
                'secondary_domain': None,
                'tertiary_domain': None,
                'domain_path': label,
                'is_core': True,
            })
        return result