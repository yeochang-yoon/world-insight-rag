import re

from .errors import UNAVAILABLE, ServiceError
from .prompts import ANSWER_PROMPT, VERIFY_PROMPT

CITATION = re.compile(r"\[근거\s+(\d+)\]")


def validate_citations(answer, evidence):
    lookup = {e["number"]: e for e in evidence}
    used = list(dict.fromkeys(int(x) for x in CITATION.findall(answer)))
    if any(i not in lookup for i in used):
        raise ServiceError(
            "답변의 근거 번호가 원문과 일치하지 않습니다. 다시 질문해 주세요."
        )
    return [lookup[i] for i in used]


def generate(llm, question, evidence, _quote_retry=False):
    if not evidence:
        return {"answer": UNAVAILABLE, "citations": []}
    # Prevent stale metadata from answering time-sensitive questions without external evidence.
    if re.search(
        r"현재|오늘|최신|비자|대통령|총리|인구|입국|실시간", question
    ) and not any(e["source_type"] == "external_document" for e in evidence):
        return {
            "answer": UNAVAILABLE + " 최신 원문 검증이 필요합니다.",
            "citations": [],
        }
    public = [
        {
            k: e.get(k)
            for k in (
                "number",
                "item_id",
                "source_type",
                "title",
                "source_url",
                "collected_at",
                "content",
            )
        }
        for e in evidence
    ]
    data = {"question": question, "evidence": public}
    if _quote_retry:
        data["validation_feedback"] = (
            "직전 발췌가 원문과 일치하지 않았습니다. 짧고 연속된 원문 문자열만 quotes에 그대로 복사하세요."
        )
    result = llm.json(ANSWER_PROMPT, data)
    answer, claims = result.get("answer"), result.get("claims")
    if not isinstance(answer, str) or not isinstance(claims, list):
        raise ServiceError("답변 JSON 형식이 올바르지 않습니다.")
    citations = validate_citations(answer, evidence)
    if not citations:
        return {
            "answer": UNAVAILABLE,
            "citations": [],
            "grounding_status": "no_citations",
        }
    lookup = {e["number"]: e["content"] for e in evidence}
    if not claims:
        return {"answer": UNAVAILABLE, "citations": [], "grounding_status": "no_claims"}
    for claim in claims:
        if not isinstance(claim, dict):
            return {
                "answer": UNAVAILABLE,
                "citations": [],
                "grounding_status": "invalid_claim",
            }
        nums, quotes = claim.get("evidence_numbers"), claim.get("quotes")
        if (
            not isinstance(nums, list)
            or not nums
            or any(type(n) is not int or n not in lookup for n in nums)
            or not isinstance(quotes, list)
            or not quotes
        ):
            return {
                "answer": UNAVAILABLE,
                "citations": [],
                "grounding_status": "invalid_claim_fields",
            }
        if any(
            not isinstance(q, str)
            or not q.strip()
            or not any(" ".join(q.split()) in " ".join(lookup[n].split()) for n in nums)
            for q in quotes
        ):
            if not _quote_retry:
                return generate(llm, question, evidence, _quote_retry=True)
            return {
                "answer": UNAVAILABLE,
                "citations": [],
                "grounding_status": "quote_mismatch",
            }
    verified = llm.json(
        VERIFY_PROMPT, {"question": question, "answer": answer, "evidence": public}
    )
    if verified.get("supported") is not True:
        return {
            "answer": UNAVAILABLE,
            "citations": [],
            "grounding_status": "audit_rejected",
        }
    return {"answer": answer, "citations": citations, "grounding_status": "verified"}
