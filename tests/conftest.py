import hashlib
import re
import tempfile

import pytest
from langchain_core.embeddings import Embeddings

from world_insight.config import ROOT, Settings
from world_insight.data import load_countries
from world_insight.indexing import CountryStore

# Keep pytest and Streamlit AppTest temporary files inside this workspace on Windows.
(ROOT / "tmp").mkdir(exist_ok=True)
tempfile.tempdir = str(ROOT / "tmp")


class TestEmbeddings(Embeddings):
    """Deterministic local test double; never used in production."""

    def embed_documents(self, texts):
        return [self.embed_query(t) for t in texts]

    def embed_query(self, text):
        vector = [0.0] * 32
        for word in re.findall(r"\w+", text.lower()):
            vector[int(hashlib.sha256(word.encode()).hexdigest()[:8], 16) % 32] += 1
        return vector if any(vector) else [1.0] + [0.0] * 31


@pytest.fixture
def countries():
    return load_countries()


@pytest.fixture
def cfg(tmp_path):
    return Settings(
        chroma_dir=str(tmp_path / "chroma"),
        embedding_model="offline-test-only",
        wiki_contact="owner@real-domain.kr",
        wiki_interval=0,
    )


@pytest.fixture
def store(cfg):
    return CountryStore(cfg, TestEmbeddings())


@pytest.fixture
def record():
    return {
        "id": "KOR:wikipedia:100",
        "item_id": "KOR",
        "document_id": "wikipedia:100",
        "title": "대한민국",
        "source_type": "external_document",
        "source_name": "한국어 위키백과",
        "source_url": "https://ko.wikipedia.org/wiki/대한민국",
        "wiki_pageid": 100,
        "collected_at": "2026-10-21T00:00:00+00:00",
        "license_notice": "CC BY-SA 4.0",
        "content": "서울은 대한민국의 수도이다. " * 200,
    }


class StubLLM:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = 0

    def json(self, system, data):
        self.calls += 1
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result
