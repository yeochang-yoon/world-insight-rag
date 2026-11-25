from .errors import ServiceError
from .prompts import SELECT_PROMPT


def is_self(country, page):
    aliases = {
        country.get("name_ko"),
        country.get("wiki_search_query"),
        country.get("name_en"),
    }
    return page.get("title") in aliases and not page.get("disambiguation", False)


def select_candidates(llm, country, question, candidates):
    # Exact-title API resolution is independently checked; ambiguous self pages are never forced.
    valid = {p["pageid"]: p for p in candidates if not p.get("disambiguation")}
    if not valid:
        return [], []
    value = llm.json(
        SELECT_PROMPT,
        {
            "country": country["name_ko"],
            "question": question,
            "candidates": [
                {
                    "pageid": p["pageid"],
                    "title": p["title"],
                    "summary": p.get("extract", "")[:1000],
                }
                for p in valid.values()
            ],
        },
    )
    ids = value.get("selected_pageids")
    if not isinstance(ids, list) or any(
        type(i) is not int or i not in valid for i in ids
    ):
        raise ServiceError("후보 선별 결과의 문서 식별자가 올바르지 않습니다.")
    selected = list(
        dict.fromkeys(
            [p["pageid"] for p in valid.values() if is_self(country, p)] + ids[:3]
        )
    )
    return [valid[i] for i in selected], [
        p for i, p in valid.items() if i not in selected
    ]
