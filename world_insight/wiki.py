import json
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

from .config import ROOT
from .data import atomic_json, fingerprint, read_jsonl
from .errors import ServiceError
from .query_extractor import extract_queries
from .selector import is_self, select_candidates

API = "https://ko.wikipedia.org/w/api.php"
LICENSE = "CC BY-SA 4.0; original authors: article history; extracted plain text and split for RAG"
_LOCK = threading.RLock()


class WikiClient:
    def __init__(self, settings, cache_dir=None, session=None):
        contact = settings.wiki_contact
        if (
            not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", contact or "")
            or "example." in contact
        ):
            raise ServiceError(
                "위키백과 수집에는 실제 WIKI_CONTACT 이메일이 필요합니다."
            )
        self.settings = settings
        self.cache_dir = Path(cache_dir or ROOT / "data/wiki_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": f"WorldInsightEducationalRAG/1.0 (mailto:{contact})",
                "Accept": "application/json",
            }
        )
        self.calls = 0
        self.cache_hits = 0
        self.last_call = 0.0

    def api(self, params):
        params = {**params, "format": "json", "formatversion": 2, "maxlag": 5}
        path = self.cache_dir / (fingerprint(params) + ".json")
        with _LOCK:
            if path.exists():
                self.cache_hits += 1
                return json.loads(path.read_text(encoding="utf-8"))

            for attempt in range(3):
                if self.calls >= self.settings.wiki_max_requests:
                    raise ServiceError(
                        "위키백과 요청 한도에 도달했습니다. 잠시 후 다시 수집해 주세요."
                    )
                time.sleep(
                    max(
                        0,
                        self.settings.wiki_interval
                        - (time.monotonic() - self.last_call),
                    )
                )
                self.calls += 1
                self.last_call = time.monotonic()
                try:
                    response = self.session.get(
                        API, params=params, timeout=min(self.settings.timeout, 30)
                    )
                    if response.status_code in (429, 500, 502, 503, 504):
                        retry = response.headers.get("Retry-After", "")
                        time.sleep(
                            min(float(retry), 30) if retry.isdigit() else 2**attempt
                        )
                        continue
                    response.raise_for_status()
                    data = response.json()
                    if "error" in data:
                        if data["error"].get("code") in ("maxlag", "ratelimited"):
                            time.sleep(2**attempt)
                            continue
                        raise ServiceError("위키백과 API가 요청을 처리하지 못했습니다.")
                    atomic_json(path, data)
                    return data
                except (requests.RequestException, ValueError):
                    if attempt < 2:
                        time.sleep(2**attempt)
            raise ServiceError(
                "위키백과 연결에 실패했습니다. 네트워크 상태를 확인해 주세요."
            )

    def pages(self, **params):
        data = self.api(
            {
                "action": "query",
                "prop": "extracts|info|pageprops|revisions",
                "inprop": "url",
                "explaintext": 1,
                "exsectionformat": "plain",
                "rvprop": "ids|timestamp",
                **params,
            }
        )
        return [
            dict(p, disambiguation="disambiguation" in p.get("pageprops", {}))
            for p in data.get("query", {}).get("pages", [])
            if "missing" not in p and p.get("pageid")
        ]

    def search(self, term):
        hits = self.api(
            {
                "action": "query",
                "list": "search",
                "srsearch": term,
                "srnamespace": 0,
                "srlimit": 5,
            }
        )
        ids = [str(p["pageid"]) for p in hits.get("query", {}).get("search", [])]
        # Summary only at selection time. Full articles fetched only after selection.
        return self.pages(pageids="|".join(ids), exintro=1) if ids else []

    def article(self, pageid):
        pages = self.pages(pageids=str(pageid))
        if not pages or pages[0]["pageid"] != pageid:
            raise ServiceError(
                "선택한 위키백과 문서와 원문 식별자가 일치하지 않습니다."
            )

        page = pages[0]
        url = urlparse(page.get("fullurl", ""))
        if (
            page.get("disambiguation")
            or not page.get("extract", "").strip()
            or url.scheme != "https"
            or url.hostname != "ko.wikipedia.org"
            or not url.path.startswith("/wiki/")
        ):
            raise ServiceError("검증 가능한 위키백과 원문이 없어 문서를 보류했습니다.")
        return page


class Collector:
    def __init__(self, wiki, llm, output=None, state_dir=None):
        self.wiki, self.llm = wiki, llm
        self.output = Path(output or ROOT / "data/wikipedia_articles.jsonl")
        self.state_dir = Path(state_dir or ROOT / "storage/collection")
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def collect(self, country, question):
        key = fingerprint({"id": country["id"], "question": question, "version": 2})
        state = self.state_dir / (key + ".json")
        with _LOCK:
            if state.exists():
                result = json.loads(state.read_text(encoding="utf-8"))
                ids = set(result["document_ids"])
                records = [r for r in read_jsonl(self.output) if r["id"] in ids]
                if len(records) == len(ids):
                    return records, {
                        **result,
                        "cache_hit": True,
                        "original_api_calls": result.get("api_calls", 0),
                        "api_calls": 0,
                        "api_cache_hits": 0,
                        "additional_api_calls": 0,
                    }

            queries = extract_queries(self.llm, country, question)
            candidates = {}
            # Resolve redirects first, retaining canonical self identity only for non-disambiguation pages.
            exact = self.wiki.pages(
                titles=country.get("wiki_search_query") or country["name_ko"],
                redirects=1,
                exintro=1,
            )
            self_ids = {p["pageid"] for p in exact if not p.get("disambiguation")}
            for p in exact:
                candidates[p["pageid"]] = p
            for query in queries:
                for p in self.wiki.search(query):
                    candidates[p["pageid"]] = p

            selected, deferred = select_candidates(
                self.llm, country, question, list(candidates.values())
            )
            selected_ids = {p["pageid"] for p in selected}
            for i in self_ids - selected_ids:
                selected.insert(0, candidates[i])

            records = []
            existing = {r["id"]: r for r in read_jsonl(self.output)}
            for candidate in selected:
                record_id = f"{country['id']}:wikipedia:{candidate['pageid']}"
                if record_id in existing:
                    records.append(existing[record_id])
                    continue
                p = self.wiki.article(candidate["pageid"])
                document_id = f"wikipedia:{p['pageid']}"
                now = datetime.now(timezone.utc).isoformat()
                records.append(
                    {
                        "id": f"{country['id']}:{document_id}",
                        "item_id": country["id"],
                        "document_id": document_id,
                        "title": p["title"],
                        "source_type": "external_document",
                        "source_name": "한국어 위키백과",
                        "source_url": p["fullurl"],
                        "wiki_pageid": p["pageid"],
                        "revision_id": (p.get("revisions") or [{}])[0].get("revid"),
                        "collected_at": now,
                        "license_notice": LICENSE,
                        "content": p["extract"].strip(),
                        "history_url": f"https://ko.wikipedia.org/w/index.php?title={requests.utils.quote(p['title'])}&action=history",
                        "is_country_article": p["pageid"] in self_ids
                        or is_self(country, p),
                    }
                )

            existing.update({r["id"]: r for r in records})
            self.output.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.output.with_suffix(".jsonl.tmp")
            tmp.write_text(
                "".join(
                    json.dumps(r, ensure_ascii=False) + "\n" for r in existing.values()
                ),
                encoding="utf-8",
            )
            tmp.replace(self.output)

            result = {
                "item_id": country["id"],
                "queries": queries,
                "document_ids": [r["id"] for r in records],
                "selected": [p["title"] for p in selected],
                "deferred": [
                    p["title"] for p in deferred if p["pageid"] not in self_ids
                ],
                "cache_hit": False,
                "api_calls": self.wiki.calls,
                "api_cache_hits": self.wiki.cache_hits,
            }
            # Negative results are cached to avoid repeated unsuccessful searches; clear this state explicitly to retry.
            atomic_json(state, result)
            return records, result
