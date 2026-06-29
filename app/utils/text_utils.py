import re
from collections.abc import Iterable

def normalize_text(text: str) -> str:
    text = re.sub(r'\r\n?', '\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def semantic_chunks(items: Iterable[dict], chunk_size: int, overlap: int) -> list[dict]:
    # 按章节/段落边界优先，超长段落再按固定长度切分；保留页码和段落顺序，符合文档“语义段落+固定长度”策略。
    chunks: list[dict] = []
    buffer = ''
    start_pos = 0
    page_number = None
    section_id = None
    for item in items:
        content = normalize_text(str(item.get('content') or ''))
        if not content:
            continue
        page_number = item.get('page_number') or page_number
        section_id = item.get('section_id') or section_id
        while len(content) > chunk_size:
            part, content = content[:chunk_size], content[max(0, chunk_size-overlap):]
            chunks.append({'text': part, 'page_number': page_number, 'section_id': section_id, 'start_position': start_pos, 'end_position': start_pos+len(part)})
            start_pos += len(part)
        if len(buffer) + len(content) + 1 <= chunk_size:
            buffer = (buffer + '\n' + content).strip()
        else:
            if buffer:
                chunks.append({'text': buffer, 'page_number': page_number, 'section_id': section_id, 'start_position': start_pos, 'end_position': start_pos+len(buffer)})
                start_pos += max(1, len(buffer)-overlap)
            buffer = content
    if buffer:
        chunks.append({'text': buffer, 'page_number': page_number, 'section_id': section_id, 'start_position': start_pos, 'end_position': start_pos+len(buffer)})
    return chunks
