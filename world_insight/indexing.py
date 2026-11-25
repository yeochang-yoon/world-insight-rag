from pathlib import Path
from urllib.parse import urlparse

import chromadb
from chromadb.config import Settings as ChromaSettings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .data import fingerprint, search_text
from .errors import ServiceError


def build_embeddings(settings):
    if not settings.api_key:
        raise ServiceError("API 키가 없습니다. OPENAI_API_KEY를 설정해 주세요.")
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.api_key,
        base_url=settings.base_url,
        check_embedding_ctx_length=False,
        chunk_size=32,
        request_timeout=settings.timeout,
        max_retries=1,
    )


class CountryStore:
    def __init__(self, settings, embeddings=None):
        self.settings = settings
        self.embeddings = (
            embeddings if embeddings is not None else build_embeddings(settings)
        )
        self.client = chromadb.PersistentClient(
            path=str(Path(settings.chroma_dir)),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self.collections = {}
        for name in ("country_meta", "country_docs"):
            collection = self.client.get_or_create_collection(
                name,
                metadata={
                    "embedding_model": settings.embedding_model,
                    "hnsw:space": "cosine",
                },
            )
            if collection.metadata.get("embedding_model") != settings.embedding_model:
                raise ServiceError(
                    "임베딩 모델이 기존 색인과 다릅니다. 별도 CHROMA_DIR로 새로 색인해 주세요."
                )
            self.collections[name] = collection
        self.meta = Chroma(
            client=self.client,
            collection_name="country_meta",
            embedding_function=self.embeddings,
        )
        self.docs = Chroma(
            client=self.client,
            collection_name="country_docs",
            embedding_function=self.embeddings,
        )

    def counts(self):
        return {name: c.count() for name, c in self.collections.items()}

    def _upsert(self, name, docs):
        collection = self.collections[name]
        existing = (
            collection.get(ids=[d.id for d in docs], include=["metadatas"])
            if docs
            else {"ids": [], "metadatas": []}
        )
        old = dict(zip(existing["ids"], existing["metadatas"]))
        changed = [
            d
            for d in docs
            if old.get(d.id, {}).get("fingerprint") != d.metadata["fingerprint"]
        ]
        created = sum(d.id not in old for d in changed)
        wrapper = self.meta if name == "country_meta" else self.docs
        try:
            for start in range(0, len(changed), 32):
                batch = changed[start : start + 32]
                wrapper.add_documents(batch, ids=[d.id for d in batch])
        except Exception:
            raise ServiceError(
                "임베딩 색인에 실패했습니다. API 인증·임베딩 모델·네트워크 상태를 확인해 주세요."
            ) from None
        return {
            "created": created,
            "updated": len(changed) - created,
            "unchanged": len(docs) - len(changed),
            "count": collection.count(),
        }

    def index_metadata(self, countries):
        docs = []
        for c in countries:
            text = search_text(c)
            meta = {
                "item_id": c["id"],
                "title": c["name_ko"] + " 국가·지역 메타데이터",
                "source_type": "metadata",
                "source_name": "pycountry / Babel CLDR / CountryInfo",
                "source_url": "https://github.com/porimol/countryinfo",
                "name_ko": c["name_ko"],
                "region_en": c.get("region_en") or "정보 없음",
                "fingerprint": fingerprint(c),
            }
            docs.append(Document(id=c["id"], page_content=text, metadata=meta))
        return self._upsert("country_meta", docs)

    def index_documents(self, records):
        result = {"created": 0, "updated": 0, "unchanged": 0, "removed_stale": 0}
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.settings.chunk_size,
            chunk_overlap=self.settings.chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
        for record in records:
            url = urlparse(record.get("source_url", ""))
            if (
                record.get("source_type") != "external_document"
                or not record.get("wiki_pageid")
                or url.hostname != "ko.wikipedia.org"
                or not url.path.startswith("/wiki/")
            ):
                raise ServiceError(
                    "실제 수집한 위키백과 원문만 외부 문서로 색인할 수 있습니다."
                )
            if not record.get("content", "").strip():
                continue
            item_id, document_id = record["item_id"], record["document_id"]
            scope = {"$and": [{"item_id": item_id}, {"document_id": document_id}]}
            previous = self.collections["country_docs"].get(where=scope, include=[])[
                "ids"
            ]
            chunks = []
            for i, text in enumerate(splitter.split_text(record["content"])):
                meta = {
                    key: record[key]
                    for key in (
                        "item_id",
                        "title",
                        "source_type",
                        "source_name",
                        "source_url",
                        "document_id",
                        "collected_at",
                        "license_notice",
                        "wiki_pageid",
                    )
                }
                meta.update(
                    chunk_index=i,
                    fingerprint=fingerprint(
                        {
                            "text": text,
                            "record": record,
                            "size": self.settings.chunk_size,
                            "overlap": self.settings.chunk_overlap,
                        }
                    ),
                )
                chunks.append(
                    Document(
                        id=f"{item_id}:{document_id}:{i}",
                        page_content=text,
                        metadata=meta,
                    )
                )
            report = self._upsert("country_docs", chunks)
            for key in ("created", "updated", "unchanged"):
                result[key] += report[key]
            # Upsert first: failed embedding leaves previous evidence intact.
            stale = sorted(set(previous) - {d.id for d in chunks})
            if stale:
                self.collections["country_docs"].delete(ids=stale)
                result["removed_stale"] += len(stale)
        return {**result, "count": self.collections["country_docs"].count()}
