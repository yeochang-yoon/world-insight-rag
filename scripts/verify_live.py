"""Opt-in, real-network end-to-end verification. No mock embeddings/LLM permitted."""

import itertools
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from world_insight.config import ROOT, Settings
from world_insight.data import atomic_json, fingerprint, load_countries, read_jsonl
from world_insight.errors import UNAVAILABLE, ServiceError
from world_insight.exploration import explore
from world_insight.generation import validate_citations
from world_insight.graph import build_graph
from world_insight.indexing import CountryStore
from world_insight.llm import ResponsesLLM
from world_insight.retrieval import retrieve

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
cfg = Settings.load()
countries = load_countries()
store = CountryStore(cfg)
llm = ResponsesLLM(cfg)
report = {
    "kind": "real GMS Responses, OpenAI embeddings, persisted Chroma and actually collected Wikipedia",
    "steps": [],
}


def step(name, fn):
    start = time.perf_counter()
    try:
        detail = fn()
        record = {
            "name": name,
            "status": "passed",
            "seconds": round(time.perf_counter() - start, 3),
            "detail": detail,
        }
    except ServiceError as exc:
        record = {"name": name, "status": "failed", "message": str(exc)}
    except Exception as exc:
        record = {"name": name, "status": "failed", "error_type": type(exc).__name__}
    report["steps"].append(record)
    atomic_json(ROOT / "docs/evidence/live_verification.json", report)
    print(name, record["status"], record.get("seconds", ""), flush=True)


def metadata():
    a = store.index_metadata(countries)
    b = store.index_metadata(countries)
    assert a["count"] == b["count"] == 249 and b["created"] == b["updated"] == 0
    return {"first": a, "second": b}


def docs():
    records = read_jsonl(ROOT / "data/wikipedia_articles.jsonl")
    assert records and all(r["source_type"] == "external_document" for r in records)
    a = store.index_documents(records)
    b = store.index_documents(records)
    assert a["count"] == b["count"] and b["created"] == b["updated"] == 0
    return {
        "actual_documents": len(records),
        "countries": len({r["item_id"] for r in records}),
        "first": a,
        "second": b,
    }


def ask(item_id, question, compare_id=None):
    result = build_graph(store, countries, llm).invoke(
        {"item_id": item_id, "question": question, "compare_id": compare_id}
    )
    assert (
        result["answer"]
        and validate_citations(result["answer"], result["evidence"])
        == result["citations"]
    )
    atomic_json(
        ROOT
        / f"docs/evidence/answer_{item_id}_{compare_id or 'single'}_{fingerprint(question)[:8]}.json",
        result,
    )
    return result


def external():
    r = ask("GHA", "가나의 지리와 역사에서 문서로 확인되는 특징을 설명해 주세요")
    if not any(c["source_type"] == "external_document" for c in r["citations"]):
        raise ServiceError(
            "외부 문서 답변 보류: " + r.get("grounding_status", "unknown")
        )
    return {"answer": r["answer"], "sources": [c["source_url"] for c in r["citations"]]}


def comparison():
    r = ask(
        "GHA", "가나와 그리스의 수도, 대륙, 언어의 공통점과 차이를 비교해 주세요", "GRC"
    )
    assert {e["item_id"] for e in r["citations"]} == {"GHA", "GRC"}
    return {
        "answer": r["answer"],
        "sources": [
            {"country": e["item_id"], "url": e["source_url"]} for e in r["citations"]
        ],
    }


def conditions():
    r = explore(store, llm, countries, "유럽에서 독일어를 사용하는 국가")
    assert r["countries"] and all(
        c["region_en"] == "Europe" and "de" in c["languages"] for c in r["countries"]
    )
    return {
        "matched_ids": [c["id"] for c in r["countries"]],
        "unknown_ids": r["unknown_ids"],
        "filters": r["filters"],
    }


def uncertainty():
    r = ask("GHA", "가나가 2100년에 월드컵에서 우승할지 확정해서 말해줘")
    assert UNAVAILABLE in r["answer"] and not r["citations"]
    return {"answer": r["answer"]}


def mmr():
    results = {}
    for method in ("similarity", "mmr"):
        ev = retrieve(
            store,
            "GRC",
            "그리스의 지리적 특징과 역사",
            method=method,
            k=4,
            fetch_k=20,
            lambda_mult=0.3,
        )
        assert all(e["item_id"] == "GRC" for e in ev)
        results[method] = [
            {
                "id": e["id"],
                "title": e["title"],
                "content": e["content"],
                "url": e["source_url"],
            }
            for e in ev
        ]
        ids = [e["id"] for e in ev if e["source_type"] == "external_document"]
        vectors = np.asarray(
            store.collections["country_docs"].get(ids=ids, include=["embeddings"])[
                "embeddings"
            ]
        )
        if len(vectors) > 1:
            vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
            results[method + "_mean_pair_cosine"] = float(
                np.mean(
                    [
                        float(vectors[i] @ vectors[j])
                        for i, j in itertools.combinations(range(len(vectors)), 2)
                    ]
                )
            )
    results["same_ids"] = [e["id"] for e in results["similarity"]] == [
        e["id"] for e in results["mmr"]
    ]
    atomic_json(ROOT / "docs/evidence/mmr_live.json", results)
    return results


for name, fn in [
    ("metadata_idempotence", metadata),
    ("external_index_idempotence", docs),
    ("external_grounded_answer", external),
    ("two_country_comparison", comparison),
    ("natural_language_conditions", conditions),
    ("unanswerable_question", uncertainty),
    ("mmr_comparison", mmr),
]:
    step(name, fn)
raise SystemExit(any(r["status"] == "failed" for r in report["steps"]))
