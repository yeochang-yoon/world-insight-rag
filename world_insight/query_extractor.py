from .errors import ServiceError
from .prompts import QUERY_PROMPT


def extract_queries(llm, country, question):
    result = llm.json(
        QUERY_PROMPT,
        {"country": country["name_ko"], "iso3": country["id"], "question": question},
    )
    queries = result.get("queries")
    if (
        not isinstance(queries, list)
        or not queries
        or len(queries) > 5
        or any(not isinstance(q, str) or not q.strip() or len(q) > 150 for q in queries)
    ):
        raise ServiceError("검색어 JSON의 queries 형식이 올바르지 않습니다.")
    name = country["name_ko"]
    return list(
        dict.fromkeys(
            [name]
            + [q.strip() if name in q else name + " " + q.strip() for q in queries]
        )
    )[:3]
