"""QA 意图分类 prompt。"""

from __future__ import annotations

INTENT_LABELS = (
    'literature_qa',
    'compare',
    'general',
    'summarize_history',
    'report',
    'graph',
)

INTENT_CLASSIFY_SYSTEM = """你是科研 Notebook 的意图分类器。根据用户问题、挂载文献数量与对话上下文，选择唯一意图。

可选意图：
- literature_qa：基于挂载文献的问答、解释、总结论文内容（默认）
- compare：对比/比较 2 篇及以上文献（需 paper_count>=2）
- report：生成/撰写/输出研读报告、阅读报告（需 paper_count>=1）
- graph：构建/生成知识图谱、关系图谱（需 paper_count>=1）
- summarize_history：总结当前对话/聊天历史（非文献摘要）
- general：无挂载文献时的通用知识问答

只输出 JSON：{"intent":"..."}，不要 Markdown 或解释。"""


def build_intent_user_prompt(
    question: str,
    paper_count: int,
    *,
    rule_hint: str | None = None,
    history_snippet: str | None = None,
) -> str:
    lines = [
        f'用户问题：{question}',
        f'挂载文献数：{paper_count}',
    ]
    if history_snippet:
        lines.append(f'最近对话：\n{history_snippet}')
    if rule_hint:
        lines.append(f'规则预判（可参考）：{rule_hint}')
    lines.append('输出 JSON：')
    return '\n'.join(lines)
