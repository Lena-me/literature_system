from __future__ import annotations
from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, connections, utility
from app.core.config import get_settings
settings = get_settings()

class MilvusChunkStore:
    def __init__(self) -> None:
        connections.connect(alias='default', host=settings.milvus_host, port=str(settings.milvus_port))
        self.collection = self._ensure_collection()

    def _ensure_collection(self) -> Collection:
        name = settings.milvus_collection
        if not utility.has_collection(name):
            fields = [
                FieldSchema(name='id', dtype=DataType.INT64, is_primary=True, auto_id=True),
                FieldSchema(name='chunk_id', dtype=DataType.INT64),
                FieldSchema(name='paper_id', dtype=DataType.INT64),
                FieldSchema(name='page_number', dtype=DataType.INT64),
                FieldSchema(name='section_title', dtype=DataType.VARCHAR, max_length=300),
                FieldSchema(name='text', dtype=DataType.VARCHAR, max_length=6000),
                FieldSchema(name='embedding', dtype=DataType.FLOAT_VECTOR, dim=settings.milvus_vector_dim),
            ]
            schema = CollectionSchema(fields, description='paper text chunks with BGE vectors')
            collection = Collection(name, schema=schema, shards_num=2)
            index_params = {'metric_type': settings.milvus_metric_type, 'index_type': settings.milvus_index_type, 'params': {'M': 16, 'efConstruction': 200}}
            collection.create_index('embedding', index_params)
        collection = Collection(name)
        collection.load()
        return collection

    def insert_chunks(self, rows: list[dict]) -> list[str]:
        data = [
            [int(r['chunk_id']) for r in rows],
            [int(r['paper_id']) for r in rows],
            [int(r.get('page_number') or 0) for r in rows],
            [(r.get('section_title') or '')[:300] for r in rows],
            [(r.get('text') or '')[:6000] for r in rows],
            [r['embedding'] for r in rows],
        ]
        result = self.collection.insert(data)
        self.collection.flush()
        return [str(x) for x in result.primary_keys]

    def search(self, vector: list[float], paper_ids: list[int] | None, limit: int) -> list[dict]:
        expr = None
        if paper_ids:
            expr = f"paper_id in {[int(x) for x in paper_ids]}"
        params = {'metric_type': settings.milvus_metric_type, 'params': {'ef': 64}}
        results = self.collection.search([vector], anns_field='embedding', param=params, limit=limit, expr=expr, output_fields=['chunk_id','paper_id','page_number','section_title','text'])
        output = []
        for hit in results[0]:
            ent = hit.entity
            output.append({'chunk_id': ent.get('chunk_id'), 'paper_id': ent.get('paper_id'), 'page_number': ent.get('page_number'), 'section_title': ent.get('section_title'), 'text': ent.get('text'), 'score': float(hit.score)})
        return output

    def flush(self) -> None:
        self.collection.flush()

    def stats(self) -> dict:
        self.collection.flush(); self.collection.load()
        return {'total_vectors': self.collection.num_entities, 'collection': self.collection.name, 'index_count': len(self.collection.indexes or []), 'shard_count': getattr(self.collection, 'num_shards', 1) or 1, 'storage_mb': 0, 'avg_search_latency_ms': 0, 'p95_search_latency_ms': 0, 'search_success_rate': 1, 'recall_rate': 1, 'health_score': 100}
