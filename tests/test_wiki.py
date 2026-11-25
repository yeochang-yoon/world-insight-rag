import pytest
import requests
from conftest import StubLLM

from world_insight.config import Settings
from world_insight.errors import ServiceError
from world_insight.wiki import Collector, WikiClient


class Response:
    status_code = 200
    headers = {}

    def raise_for_status(self):
        pass

    def json(self):
        return {"query": {"search": [{"pageid": 100, "title": "대한민국"}]}}


class Session:
    def __init__(self):
        self.headers = {}
        self.calls = 0

    def get(self, *args, **kwargs):
        self.calls += 1
        return Response()


def test_search_cache_hit(cfg, tmp_path):
    session = Session()
    wiki = WikiClient(cfg, tmp_path / "cache", session)
    assert wiki.api({"action": "query", "list": "search", "srsearch": "대한민국"})
    wiki.api({"action": "query", "list": "search", "srsearch": "대한민국"})
    assert session.calls == 1 and wiki.cache_hits == 1
    assert cfg.wiki_contact in session.headers["User-Agent"]


def test_contact_required():
    with pytest.raises(ServiceError):
        WikiClient(Settings(wiki_contact=""))


def test_network_failure_sanitized(cfg, tmp_path, monkeypatch):
    session = Session()

    def fail(*a, **kw):
        raise requests.ConnectionError("secret internal detail")

    monkeypatch.setattr(session, "get", fail)
    monkeypatch.setattr("world_insight.wiki.time.sleep", lambda _: None)
    with pytest.raises(ServiceError) as exc:
        WikiClient(cfg, tmp_path / "cache", session).api({"action": "query"})
    assert session.calls == 0 and "secret" not in str(exc.value)


def test_request_limit(cfg, tmp_path):
    cfg.wiki_max_requests = 0
    with pytest.raises(ServiceError, match="한도"):
        WikiClient(cfg, tmp_path / "cache", Session()).api({"a": 1})


def test_rate_limit_retry_and_delay(cfg, tmp_path, monkeypatch):
    sleeps = []
    monkeypatch.setattr("world_insight.wiki.time.sleep", lambda n: sleeps.append(n))

    class LimitedSession(Session):
        def get(self, *a, **kw):
            self.calls += 1
            r = Response()
            if self.calls == 1:
                r.status_code = 429
                r.headers = {"Retry-After": "2"}
            return r

    session = LimitedSession()
    wiki = WikiClient(cfg, tmp_path / "cache", session)
    wiki.api({"action": "query"})
    assert session.calls == 2 and 2 in sleeps


@pytest.mark.parametrize(
    "page",
    [
        {"pageid": 999, "extract": "x", "fullurl": "https://ko.wikipedia.org/wiki/x"},
        {
            "pageid": 100,
            "extract": "x",
            "fullurl": "https://ko.wikipedia.org/w/index.php?search=x",
        },
        {"pageid": 100, "extract": "x", "fullurl": "https://evil.com/wiki/x"},
        {
            "pageid": 100,
            "extract": "x",
            "fullurl": "https://ko.wikipedia.org/wiki/x",
            "disambiguation": True,
        },
    ],
)
def test_article_url_pageid_validation(cfg, tmp_path, monkeypatch, page):
    wiki = WikiClient(cfg, tmp_path / "cache", Session())
    monkeypatch.setattr(wiki, "pages", lambda **kw: [page])
    with pytest.raises(ServiceError):
        wiki.article(100)


def test_collector_preserves_self_and_caches(cfg, tmp_path, monkeypatch):
    wiki = WikiClient(cfg, tmp_path / "cache", Session())
    page = {
        "pageid": 100,
        "title": "대한민국",
        "extract": "대한민국의 수도는 서울이다.",
        "fullurl": "https://ko.wikipedia.org/wiki/대한민국",
    }
    monkeypatch.setattr(wiki, "pages", lambda **kw: [page])
    monkeypatch.setattr(wiki, "search", lambda term: [page])
    monkeypatch.setattr(wiki, "article", lambda pageid: page)
    llm = StubLLM({"queries": ["대한민국"]}, {"selected_pageids": []})
    collector = Collector(wiki, llm, tmp_path / "articles.jsonl", tmp_path / "states")
    c = {"id": "KOR", "name_ko": "대한민국", "wiki_search_query": "대한민국"}
    records, report = collector.collect(c, "수도?")
    assert (
        records[0]["source_url"] == page["fullurl"] and records[0]["wiki_pageid"] == 100
    )
    assert records[0]["is_country_article"] is True
    again, report = collector.collect(c, "수도?")
    assert report["cache_hit"] and llm.calls == 2
    assert again == records
    # New country links must retain prior records.
    collector.llm = StubLLM({"queries": ["일본"]}, {"selected_pageids": [100]})
    collector.collect({"id": "JPN", "name_ko": "일본"}, "수도?")
    assert len(collector.output.read_text(encoding="utf-8").splitlines()) == 2
