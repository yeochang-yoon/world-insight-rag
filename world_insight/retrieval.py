from .errors import ServiceError


def number_evidence(evidence):
    return [dict(e, number=i) for i, e in enumerate(evidence, 1)]


def retrieve(
    store,
    item_id,
    question,
    method="similarity",
    k=None,
    fetch_k=None,
    lambda_mult=None,
):
    cfg = store.settings
    k = cfg.top_k if k is None else k
    fetch_k = cfg.fetch_k if fetch_k is None else fetch_k
    lambda_mult = cfg.lambda_mult if lambda_mult is None else lambda_mult
    if (
        not 1 <= k <= fetch_k
        or not 0 <= lambda_mult <= 1
        or method not in ("similarity", "mmr")
    ):
        raise ServiceError("검색 설정이 올바르지 않습니다.")
    metadata = store.collections["country_meta"].get(
        ids=[item_id], include=["documents", "metadatas"]
    )
    if not metadata["ids"]:
        raise ServiceError(
            "선택 국가의 색인이 없습니다. 메타데이터 색인을 먼저 실행해 주세요."
        )
    evidence = [
        {"id": item_id, "content": metadata["documents"][0], **metadata["metadatas"][0]}
    ]
    available = len(
        store.collections["country_docs"].get(where={"item_id": item_id}, include=[])[
            "ids"
        ]
    )
    if available:
        try:
            if method == "mmr":
                docs = store.docs.max_marginal_relevance_search(
                    question,
                    k=min(k, available),
                    fetch_k=min(fetch_k, available),
                    lambda_mult=lambda_mult,
                    filter={"item_id": item_id},
                )
            else:
                docs = store.docs.similarity_search(
                    question, k=min(fetch_k, available), filter={"item_id": item_id}
                )
        except Exception:
            raise ServiceError(
                "근거 검색에 실패했습니다. 임베딩 API 연결을 확인해 주세요."
            ) from None
        seen, accepted = set(), 0
        for d in docs:
            # Defense in depth: collection results must still match the requested country.
            key = (d.metadata.get("document_id"), d.page_content.strip())
            if d.metadata.get("item_id") != item_id or key in seen:
                continue
            seen.add(key)
            evidence.append(
                {
                    "id": d.id
                    or f"{item_id}:{d.metadata['document_id']}:{d.metadata['chunk_index']}",
                    "content": d.page_content,
                    **d.metadata,
                }
            )
            accepted += 1
            if accepted >= k:
                break
    return number_evidence(evidence)
