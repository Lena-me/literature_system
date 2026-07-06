from app.services.qa.protocols import QAMessagePort, QARetrievalPort
from app.services.qa.rag_adapter import RAGMessageAdapter, RAGRetrievalAdapter

__all__ = [
    'QAMessagePort',
    'QARetrievalPort',
    'RAGMessageAdapter',
    'RAGRetrievalAdapter',
    'build_qa_ports',
]


def build_qa_ports(rag=None) -> tuple[RAGRetrievalAdapter, RAGMessageAdapter]:
    from app.services.rag_service import get_rag_service

    svc = rag or get_rag_service()
    return RAGRetrievalAdapter(svc), RAGMessageAdapter(svc)
