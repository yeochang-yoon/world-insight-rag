import json
from pathlib import Path

import pytest
from conftest import StubLLM
from langchain_core.documents import Document

from world_insight.config import ROOT, Settings
from world_insight.data import read_jsonl, search_text
from world_insight.errors import UNAVAILABLE, ServiceError
from world_insight.exploration import explore, matches, validate_filters
from world_insight.generation import generate, validate_citations
from world_insight.graph import build_graph
from world_insight.history import country_history
from world_insight.llm import ResponsesLLM, parse_object
from world_insight.query_extractor import extract_queries
from world_insight.retrieval import retrieve
from world_insight.selector import select_candidates


def test_249_data_preserved(countries):
    assert len(countries) == len({c["id"] for c in countries}) == 249
    assert len(read_jsonl(ROOT / "data/metadata_index.jsonl")) == 249
    assert all(
        c["id"] == c["iso3"]
        and len(c["iso3"]) == 3
        and c["name_ko"]
        and c["name_en"]
        and search_text(c)
        for c in countries
    )
    assert all(
        n["is_original_wikipedia_article"] is False
        for n in read_jsonl(ROOT / "data/structured_country_notes.jsonl")
    )


def test_index_twice_idempotent(store, countries):
    assert store.index_metadata(countries)["created"] == 249
    result = store.index_metadata(countries)
    assert (
        result["count"] == 249 and result["unchanged"] == 249 and result["created"] == 0
    )


@pytest.mark.parametrize("text", ["no json", "[]", '{"queries":'])
def test_json_parse_rejects(text):
    with pytest.raises(ServiceError):
        parse_object(text)


def test_json_fences():
    assert parse_object('```json\n{"queries":["한국"]}\n```')["queries"] == ["한국"]


def test_query_ensures_country(countries):
    c = next(c for c in countries if c["id"] == "KOR")
    queries = extract_queries(StubLLM({"queries": ["역사"]}), c, "역사를 알려줘")
    assert queries[0] == c["name_ko"] and all(c["name_ko"] in q for q in queries)
    with pytest.raises(ServiceError):
        extract_queries(StubLLM({"queries": "oops"}), c, "?")


def test_selector_self_ambiguity_and_invalid_id():
    c = {"id": "KOR", "name_ko": "대한민국"}
    candidates = [
        {"pageid": 1, "title": "대한민국"},
        {"pageid": 2, "title": "다른 나라"},
        {"pageid": 3, "title": "대한민국", "disambiguation": True},
    ]
    picked, deferred = select_candidates(
        StubLLM({"selected_pageids": []}), c, "?", candidates
    )
    assert [p["pageid"] for p in picked] == [1]
    assert [p["pageid"] for p in deferred] == [2]
    with pytest.raises(ServiceError):
        select_candidates(StubLLM({"selected_pageids": [999]}), c, "?", candidates)


def test_chunk_settings_reindex_and_shared_document(store, record):
    store.settings.chunk_size = 100
    store.settings.chunk_overlap = 20
    first = store.index_documents([record])
    n = first["count"]
    assert n > 1
    assert store.index_documents([record])["unchanged"] == n
    rows = store.collections["country_docs"].get(include=["documents", "metadatas"])
    assert max(map(len, rows["documents"])) <= 100
    store.settings.chunk_overlap = 0
    assert store.index_documents([record])["count"] < n
    store.settings.chunk_size = 400
    smaller = store.index_documents([record])
    assert smaller["removed_stale"] > 0
    other = {**record, "id": "JPN:wikipedia:100", "item_id": "JPN"}
    store.index_documents([other])
    ids = store.collections["country_docs"].get(include=[])["ids"]
    assert any(i.startswith("KOR:") for i in ids) and any(
        i.startswith("JPN:") for i in ids
    )


def test_reject_fake_notes(store, record):
    with pytest.raises(ServiceError):
        store.index_documents([{**record, "source_type": "structured_reference_note"}])


def test_country_filter_topk_dedupe(store, countries, record):
    store.index_metadata(countries)
    # Unique chunk content prevents content dedupe masking Top-k.
    record["content"] = "\n".join(
        f"대한민국 역사 주제 {i}. " + ("자료 " * 50) for i in range(20)
    )
    store.settings.chunk_size = 150
    store.settings.chunk_overlap = 0
    store.index_documents(
        [record, {**record, "item_id": "JPN", "id": "JPN:wikipedia:100"}]
    )
    one = retrieve(store, "KOR", "대한민국 역사", k=1)
    three = retrieve(store, "KOR", "대한민국 역사", k=3)
    assert len(one) == 2 and len(three) == 4
    assert three[0]["source_type"] == "metadata"
    assert all(e["item_id"] == "KOR" for e in three)
    assert len({e["id"] for e in three}) == len(three)
    mmr = retrieve(store, "KOR", "대한민국 역사", method="mmr", k=3)
    assert len(mmr) == 4 and all(e["item_id"] == "KOR" for e in mmr)


def test_defense_against_cross_country_and_duplicates(store, countries, monkeypatch):
    store.index_metadata(countries)
    coll = store.collections["country_docs"]
    coll.upsert(
        ids=["stub"],
        embeddings=[[1.0] * 32],
        documents=["x"],
        metadatas=[{"item_id": "KOR"}],
    )
    docs = [
        Document(
            id="a",
            page_content="same",
            metadata={"item_id": "KOR", "document_id": "d", "chunk_index": 0},
        ),
        Document(
            id="b",
            page_content="same",
            metadata={"item_id": "KOR", "document_id": "d", "chunk_index": 1},
        ),
        Document(
            id="c",
            page_content="foreign",
            metadata={"item_id": "JPN", "document_id": "d", "chunk_index": 0},
        ),
    ]
    monkeypatch.setattr(store.docs, "similarity_search", lambda *a, **kw: docs)
    assert len(retrieve(store, "KOR", "q")) == 2


def test_index_missing_and_bad_retrieval(store):
    with pytest.raises(ServiceError, match="색인"):
        retrieve(store, "KOR", "?")
    with pytest.raises(ServiceError):
        retrieve(store, "KOR", "?", k=50, fetch_k=1)


def test_citations_only_used_and_reject_invalid():
    evidence = [{"number": 1}, {"number": 2}]
    assert validate_citations("설명 [근거 2] [근거 2]", evidence) == [evidence[1]]
    with pytest.raises(ServiceError):
        validate_citations("틀림 [근거 9]", evidence)


def test_uncertainty_without_evidence():
    assert generate(StubLLM(), "비밀 역사는?", []) == {
        "answer": UNAVAILABLE,
        "citations": [],
    }
    evidence = [{"number": 1, "source_type": "metadata", "content": "수도 Seoul"}]
    assert not generate(StubLLM(), "현재 대통령", evidence)["citations"]


def test_generate_validated_quotes_and_audit():
    ev = [{"number": 1, "source_type": "metadata", "content": "수도: Seoul"}]
    answer = {
        "answer": "수도는 Seoul입니다. [근거 1]",
        "claims": [
            {"text": "수도 Seoul", "evidence_numbers": [1], "quotes": ["수도: Seoul"]}
        ],
    }
    assert (
        generate(StubLLM(answer, {"supported": True}), "수도는?", ev)["citations"] == ev
    )
    assert (
        generate(StubLLM(answer, {"supported": False}), "수도는?", ev)["answer"]
        == UNAVAILABLE
    )
    bad = {
        **answer,
        "claims": [
            {"text": "거짓", "evidence_numbers": [1], "quotes": ["존재하지 않는 문장"]}
        ],
    }
    assert generate(StubLLM(bad, bad), "수도는?", ev)["answer"] == UNAVAILABLE
    assert (
        generate(StubLLM(bad, answer, {"supported": True}), "수도는?", ev)["citations"]
        == ev
    )


def test_graph_nodes_and_comparison_sources(store, countries):
    store.index_metadata(countries)
    llm = StubLLM({"answer": "제공된 문서에서 확인할 수 없습니다.", "claims": []})
    graph = build_graph(store, countries, llm)
    assert {"retrieve", "generate"} <= set(graph.get_graph().nodes)
    result = graph.invoke({"item_id": "KOR", "compare_id": "JPN", "question": "비교"})
    assert [e["item_id"] for e in result["evidence"]] == ["KOR", "JPN"]
    assert [e["number"] for e in result["evidence"]] == [1, 2]


def test_country_history_isolation():
    state = {}
    country_history(state, "KOR").append({"role": "user", "content": "안녕"})
    assert country_history(state, "JPN") == []
    assert len(country_history(state, "KOR")) == 1


def test_condition_false_and_unknown(countries):
    filters = validate_filters(
        {
            "filters": [
                {"field": "region_en", "op": "eq", "value": "Europe"},
                {"field": "languages", "op": "contains", "value": "de"},
            ],
            "unsupported": False,
        }
    )
    assert matches({"region_en": "Europe", "languages": ["de"]}, filters) is True
    assert matches({"region_en": "Asia", "languages": ["de"]}, filters) is False
    assert matches({"region_en": "Europe", "languages": []}, filters) is None
    assert matches({"region_en": None, "languages": ["fr"]}, filters) is False
    for v in (
        {"filters": [], "unsupported": False},
        {
            "filters": [{"field": "population", "op": "eq", "value": 1}],
            "unsupported": False,
        },
    ):
        with pytest.raises(ServiceError):
            validate_filters(v)


def test_exploration_real_attributes(store, countries):
    store.index_metadata(countries)
    result = explore(
        store,
        StubLLM(
            {
                "filters": [
                    {"field": "region_en", "op": "eq", "value": "Europe"},
                    {"field": "languages", "op": "contains", "value": "de"},
                ],
                "unsupported": False,
            }
        ),
        countries,
        "유럽에서 독일어",
    )
    ids = {c["id"] for c in result["countries"]}
    assert "DEU" in ids and "KOR" not in ids and "FRA" not in ids
    assert all(
        c["region_en"] == "Europe" and "de" in c["languages"]
        for c in result["countries"]
    )


def test_missing_key_and_settings_repr():
    with pytest.raises(ServiceError, match="API 키"):
        ResponsesLLM(Settings())
    assert "secret-key-value" not in repr(Settings(api_key="secret-key-value"))
    with pytest.raises(ValueError):
        Settings(chunk_size=100, chunk_overlap=200)


def test_llm_error_redacts_raw_auth_details(monkeypatch):
    llm = ResponsesLLM(Settings(api_key="not-a-real-secret"))

    def fail(**kw):
        raise RuntimeError("Bearer not-a-real-secret hidden prompt traceback")

    monkeypatch.setattr(llm.client.responses, "create", fail)
    with pytest.raises(ServiceError) as exc:
        llm.json("hidden prompt", {"q": "test"})
    assert "not-a-real-secret" not in str(exc.value) and "hidden prompt" not in str(
        exc.value
    )


def test_source_secret_and_ui_boundary():
    from dotenv import dotenv_values

    key = dotenv_values(ROOT / ".env").get("OPENAI_API_KEY")
    paths = (
        list((ROOT / "world_insight").glob("*.py"))
        + [ROOT / "app.py"]
        + list((ROOT / "docs").glob("*.md"))
    )
    if key:
        assert all(key not in p.read_text(encoding="utf-8") for p in paths)
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "st.exception" not in app and "traceback" not in app
    assert ".env" in (ROOT / ".gitignore").read_text()
