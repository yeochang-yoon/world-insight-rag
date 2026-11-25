from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from .errors import ServiceError
from .generation import generate
from .retrieval import number_evidence, retrieve


class RAGState(TypedDict, total=False):
    question: str
    item_id: str
    compare_id: str
    method: str
    k: int
    evidence: list[dict]
    answer: str
    citations: list[dict]
    grounding_status: str
    notices: list[str]


def build_graph(store, countries, llm, collector=None, progress=None):
    lookup = {c["id"]: c for c in countries}
    progress = progress or (lambda message: None)

    def retrieve_node(state):
        evidence, notices = [], []
        for item_id in dict.fromkeys([state["item_id"], state.get("compare_id")]):
            if not item_id:
                continue
            if item_id not in lookup:
                raise ServiceError("선택한 국가 코드가 없습니다.")
            if collector:
                progress("위키백과 문서 수집 중")
                try:
                    records, report = collector.collect(
                        lookup[item_id], state["question"]
                    )
                    if not records:
                        notices.append("관련 위키백과 원문을 찾지 못했습니다.")
                    progress("외부 문서 색인 중")
                    store.index_documents(records)
                except ServiceError as exc:
                    notices.append(str(exc))
            progress("국가별 근거 검색 중")
            evidence.extend(
                retrieve(
                    store,
                    item_id,
                    state["question"],
                    method=state.get("method", "similarity"),
                    k=state.get("k"),
                )
            )
        return {"evidence": number_evidence(evidence), "notices": notices}

    def generate_node(state):
        progress("근거 기반 답변 생성 및 인용 검증 중")
        return generate(llm, state["question"], state["evidence"])

    builder = StateGraph(RAGState)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("generate", generate_node)
    builder.add_edge(START, "retrieve")
    builder.add_edge("retrieve", "generate")
    builder.add_edge("generate", END)
    return builder.compile()
