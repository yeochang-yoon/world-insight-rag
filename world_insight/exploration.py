from .errors import ServiceError
from .prompts import CONDITION_PROMPT

FIELDS = {
    "region_en",
    "subregion_en",
    "languages",
    "currencies",
    "capital_en",
    "name_ko",
    "name_en",
    "area_km2",
}


def validate_filters(value):
    filters = value.get("filters")
    if (
        value.get("unsupported") is not False
        or not isinstance(filters, list)
        or not filters
        or len(filters) > 8
    ):
        raise ServiceError(
            "이 조건은 현재 메타데이터로 검증할 수 없습니다. 대륙·언어·통화·면적 조건을 사용해 주세요."
        )
    for f in filters:
        if (
            not isinstance(f, dict)
            or f.get("field") not in FIELDS
            or f.get("op") not in {"eq", "contains", "gte", "lte"}
        ):
            raise ServiceError("지원하지 않는 국가 검색 조건입니다.")
        numeric = f["field"] == "area_km2"
        if numeric and (
            f["op"] not in {"gte", "lte", "eq"}
            or type(f.get("value")) not in (int, float)
            or f["value"] < 0
        ):
            raise ServiceError("면적 조건이 올바르지 않습니다.")
        if not numeric and (
            not isinstance(f.get("value"), str)
            or not f["value"].strip()
            or f["op"] not in {"eq", "contains"}
        ):
            raise ServiceError("문자 조건이 올바르지 않습니다.")
    return filters


def matches(country, filters):
    unknown = False
    for f in filters:
        actual, expected = country.get(f["field"]), f["value"]
        if actual is None or actual == [] or actual == "":
            unknown = True
            continue
        if f["op"] in ("gte", "lte"):
            ok = actual >= expected if f["op"] == "gte" else actual <= expected
        elif isinstance(actual, list):
            ok = str(expected).casefold() in [str(x).casefold() for x in actual]
        elif f["op"] == "contains" and f["field"] in {
            "name_ko",
            "name_en",
            "capital_en",
        }:
            ok = str(expected).casefold() in str(actual).casefold()
        else:
            # Categorical values are checked for exact equality, never substring similarity.
            ok = str(actual).casefold() == str(expected).casefold()
        if not ok:
            return False
    return None if unknown else True


def explore(store, llm, countries, question):
    filters = validate_filters(llm.json(CONDITION_PROMPT, {"condition": question}))
    count = store.collections["country_meta"].count()
    if not count:
        raise ServiceError("메타데이터 색인이 없습니다. 먼저 색인해 주세요.")
    try:
        # All 249 are cheap: rank vector candidates then apply exact structured predicates,
        # avoiding loss of matching low-similarity countries at an arbitrary vector cutoff.
        ranked = store.meta.similarity_search(question, k=count)
    except Exception:
        raise ServiceError("조건 검색의 임베딩 API 연결에 실패했습니다.") from None
    lookup = {c["id"]: c for c in countries}
    found, unknown = [], []
    for d in ranked:
        c = lookup.get(d.metadata.get("item_id"))
        if c:
            verdict = matches(c, filters)
            if verdict is True:
                found.append(c)
            elif verdict is None:
                unknown.append(c["id"])
    return {"countries": found, "unknown_ids": unknown, "filters": filters}
