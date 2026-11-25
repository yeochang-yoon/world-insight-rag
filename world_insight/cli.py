import argparse
import json
import sys
import time

from .config import ROOT, Settings
from .data import atomic_json, fingerprint, load_countries, read_jsonl
from .errors import ServiceError


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2), flush=True)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="World Insight AI")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "status", "probe", "index-meta", "index-docs"):
        commands.add_parser(name)

    collect_parser = commands.add_parser("collect")
    collect_parser.add_argument(
        "--limit", type=int, default=10, help="0 = all countries"
    )
    collect_parser.add_argument("--item", help="ISO3, optionally comma-separated")
    collect_parser.add_argument("--question", default="지리와 역사에 대해 알려주세요")
    collect_parser.add_argument("--contact")

    ask_parser = commands.add_parser("ask")
    ask_parser.add_argument("item_id")
    ask_parser.add_argument("question")
    ask_parser.add_argument("--compare")
    ask_parser.add_argument(
        "--method", choices=["similarity", "mmr"], default="similarity"
    )
    ask_parser.add_argument("--no-collect", action="store_true")
    ask_parser.add_argument("--k", type=int)

    explore_parser = commands.add_parser("explore")
    explore_parser.add_argument("condition")

    benchmark_parser = commands.add_parser("benchmark")
    benchmark_parser.add_argument("--item", default="KOR")
    benchmark_parser.add_argument(
        "--question", default="지리와 역사적 특징을 설명해 주세요"
    )

    args = parser.parse_args(argv)
    settings = Settings.load()
    if getattr(args, "contact", None):
        settings.wiki_contact = args.contact
    countries = load_countries()
    started = time.perf_counter()

    try:
        if args.command == "validate":
            emit(
                {
                    "items": len(countries),
                    "unique_ids": len({c["id"] for c in countries}),
                    "metadata_records": len(
                        read_jsonl(ROOT / "data/metadata_index.jsonl")
                    ),
                    "test_notes_not_wikipedia": len(
                        read_jsonl(ROOT / "data/structured_country_notes.jsonl")
                    ),
                    "actual_wikipedia_records": len(
                        read_jsonl(ROOT / "data/wikipedia_articles.jsonl")
                    ),
                    "countries_sha256": fingerprint(countries),
                }
            )
            return

        if args.command == "status":
            import chromadb

            client = chromadb.PersistentClient(path=settings.chroma_dir)
            names = [c.name for c in client.list_collections()]
            emit(
                {
                    name: client.get_collection(name).count() if name in names else 0
                    for name in ("country_meta", "country_docs")
                }
            )
            return

        from .llm import ResponsesLLM

        if args.command == "probe":
            from .indexing import build_embeddings

            result = ResponsesLLM(settings).json(
                'Return only JSON {"message":"Hello, World!"}', {"hello": "world"}
            )
            vector = build_embeddings(settings).embed_query("Hello, World!")
            emit(
                {
                    "responses": "passed",
                    "model": settings.model,
                    "result": result,
                    "embeddings": "passed",
                    "embedding_model": settings.embedding_model,
                    "dimensions": len(vector),
                }
            )
            return

        if args.command == "collect":
            from .wiki import Collector, WikiClient

            wiki = WikiClient(settings)
            collector = Collector(wiki, ResponsesLLM(settings))
            selected = (
                [c for c in countries if c["id"] in args.item.split(",")]
                if args.item
                else countries
            )
            selected = selected[: args.limit] if args.limit > 0 else selected
            reports = []
            for i, country in enumerate(selected, 1):
                try:
                    records, report = collector.collect(country, args.question)
                    report["status"] = "passed" if records else "no_results"
                except ServiceError as exc:
                    report = {
                        "item_id": country["id"],
                        "status": "failed",
                        "message": str(exc),
                    }
                reports.append(report)
                emit({"progress": f"{i}/{len(selected)}", **report})
            result = {
                "reports": reports,
                "actual_documents": len(read_jsonl(collector.output)),
                "api_calls": wiki.calls,
                "cache_hits": wiki.cache_hits,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
            }
            atomic_json(ROOT / "data/wikipedia_collection_report.json", result)
            if any(r["status"] == "failed" for r in reports):
                raise ServiceError(
                    "일부 문서 수집에 실패했습니다. data/wikipedia_collection_report.json을 확인해 주세요."
                )
            return

        from .indexing import CountryStore

        store = CountryStore(settings)
        if args.command == "index-meta":
            emit(store.index_metadata(countries))
        elif args.command == "index-docs":
            emit(
                store.index_documents(
                    read_jsonl(ROOT / "data/wikipedia_articles.jsonl")
                )
            )
        elif args.command == "explore":
            from .exploration import explore

            emit(explore(store, ResponsesLLM(settings), countries, args.condition))
        elif args.command == "ask":
            from .graph import build_graph
            from .wiki import Collector, WikiClient

            llm = ResponsesLLM(settings)
            collector = (
                None if args.no_collect else Collector(WikiClient(settings), llm)
            )
            state = {
                "item_id": args.item_id,
                "question": args.question,
                "compare_id": args.compare,
                "method": args.method,
            }
            if args.k:
                state["k"] = args.k
            result = build_graph(store, countries, llm, collector).invoke(state)
            result["elapsed_seconds"] = round(time.perf_counter() - started, 3)
            emit(result)
            atomic_json(ROOT / "docs/evidence/last_ask.json", result)
        elif args.command == "benchmark":
            from .retrieval import retrieve

            report = {
                "kind": "real configured embeddings and persisted documents",
                "item_id": args.item,
                "question": args.question,
                "methods": {},
            }
            for method in ("similarity", "mmr"):
                start = time.perf_counter()
                evidence = retrieve(store, args.item, args.question, method=method)
                report["methods"][method] = {
                    "seconds": round(time.perf_counter() - start, 3),
                    "evidence": [
                        {k: e.get(k) for k in ("id", "title", "source_url", "content")}
                        for e in evidence
                    ],
                }
            atomic_json(ROOT / "docs/evidence/mmr_live.json", report)
            emit(report)
    except ServiceError as exc:
        emit(
            {
                "status": "failed",
                "message": str(exc),
                "elapsed_seconds": round(time.perf_counter() - started, 3),
            }
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
