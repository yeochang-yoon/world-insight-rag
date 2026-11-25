import json

from langchain_core.embeddings import Embeddings

from world_insight.indexing import CountryStore
from world_insight.retrieval import retrieve


class MappedEmbeddings(Embeddings):
    def embed_documents(self, texts):
        return [self.embed_query(t) for t in texts]

    def embed_query(self, text):
        return {
            "query": [1.0, 0.0],
            "near1": [1.0, 0.01],
            "near2": [1.0, 0.02],
            "diverse": [0.6, 0.8],
        }.get(text, [1.0, 0.0])


def test_mmr_selects_diverse_evidence(cfg, countries, tmp_path):
    store = CountryStore(cfg, MappedEmbeddings())
    store.index_metadata(countries)
    coll = store.collections["country_docs"]
    for i, text in enumerate(["near1", "near2", "diverse"]):
        coll.upsert(
            ids=[f"KOR:d:{i}"],
            documents=[text],
            embeddings=[MappedEmbeddings().embed_query(text)],
            metadatas=[
                {
                    "item_id": "KOR",
                    "document_id": "d",
                    "chunk_index": i,
                    "source_type": "external_document",
                }
            ],
        )
    similarity = retrieve(store, "KOR", "query", k=2, fetch_k=3)
    mmr = retrieve(store, "KOR", "query", method="mmr", k=2, fetch_k=3, lambda_mult=0.1)
    assert [e["content"] for e in similarity[1:]] == ["near1", "near2"]
    assert [e["content"] for e in mmr[1:]] == ["near1", "diverse"]
