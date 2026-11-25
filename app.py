import time

import streamlit as st

from world_insight.config import Settings
from world_insight.data import load_countries
from world_insight.errors import ServiceError
from world_insight.history import country_history

st.set_page_config(page_title="World Insight AI", page_icon="🌍", layout="wide")


@st.cache_resource
def resources():
    from world_insight.indexing import CountryStore
    from world_insight.llm import ResponsesLLM

    cfg = Settings.load()
    return cfg, CountryStore(cfg), ResponsesLLM(cfg)


def show_result(result):
    st.markdown(result["answer"])
    for notice in result.get("notices", []):
        st.info(notice)

    if result.get("citations"):
        with st.expander("답변에 사용한 근거와 원문", expanded=True):
            for citation in result["citations"]:
                st.write(
                    f"[근거 {citation['number']}] {citation['item_id']} · "
                    f"{citation['source_name']} · {citation['title']}"
                )
                st.link_button("원문 보기", citation["source_url"])
                if citation.get("collected_at"):
                    st.caption(
                        f"수집: {citation['collected_at']} · "
                        f"{citation.get('license_notice', '')}"
                    )
                st.caption(citation["content"][:500])
    else:
        st.caption("답변에 인용된 근거가 없습니다.")

    if result.get("elapsed_seconds") is not None:
        st.caption(f"처리 시간 {result['elapsed_seconds']:.2f}초")


def select_country(item_id):
    st.session_state.selected_country = item_id
    st.session_state.active_tab = "국가 채팅"


def run_question(
    cfg,
    store,
    llm,
    countries,
    item_id,
    question,
    method,
    k,
    auto_collect,
    compare_id=None,
):
    from world_insight.graph import build_graph
    from world_insight.wiki import Collector, WikiClient

    started = time.perf_counter()
    with st.status("질문 처리 중", expanded=True) as status:
        try:
            collector = Collector(WikiClient(cfg), llm) if auto_collect else None
            result = build_graph(
                store, countries, llm, collector, progress=status.write
            ).invoke(
                {
                    "item_id": item_id,
                    "question": question,
                    "method": method,
                    "k": k,
                    "compare_id": compare_id,
                }
            )
            result["elapsed_seconds"] = time.perf_counter() - started
            status.update(label="답변 완료", state="complete")
            return result
        except ServiceError as exc:
            st.warning(str(exc))
        except Exception:
            st.error("질문을 처리하지 못했습니다. 설정과 API 연결을 확인해 주세요.")
        status.update(label="처리 실패", state="error")
    return None


def main():
    st.title("🌍 World Insight AI")
    st.write("249개 국가·지역을 살펴보고, 원문 근거와 함께 질문하세요.")
    st.caption(
        "ISO 목록에는 해외 영토와 지역이 포함됩니다. 기초 지리 정보는 최신성이 보장되지 않습니다."
    )

    countries = load_countries()
    countries_by_id = {country["id"]: country for country in countries}
    country_ids = list(countries_by_id)

    def country_label(item_id):
        country = countries_by_id[item_id]
        return f"{country['name_ko']} · {country['name_en']} ({item_id})"

    with st.sidebar:
        st.header("탐색 설정")
        if "selected_country" not in st.session_state:
            st.session_state.selected_country = "KOR"
        item_id = st.selectbox(
            "국가·지역 검색 및 선택",
            country_ids,
            format_func=country_label,
            key="selected_country",
        )
        method = st.radio(
            "근거 검색 방식",
            ["similarity", "mmr"],
            format_func=lambda v: "유사도" if v == "similarity" else "MMR · 다양성",
        )
        k = st.slider("외부 문서 Top-k", 1, 10, 4)
        auto_collect = st.checkbox("질문에 맞는 위키백과 문서 수집", True)

    try:
        cfg, store, llm = resources()
    except ServiceError as exc:
        st.warning(str(exc))
        st.code(
            "python -m world_insight.cli index-meta\nstreamlit run app.py",
            language="bash",
        )
        return
    except Exception:
        st.error(
            "서비스 초기화에 실패했습니다. 환경 설정과 의존성 설치 상태를 확인해 주세요."
        )
        return

    counts = store.counts()
    st.sidebar.metric("메타데이터 색인", counts["country_meta"])
    st.sidebar.metric("실제 외부 문서 청크", counts["country_docs"])
    if not counts["country_meta"]:
        st.info("메타데이터 색인이 없습니다. 아래 버튼 또는 CLI로 초기 색인해 주세요.")

    if st.sidebar.button("메타데이터 색인 / 갱신"):
        completed = False
        with st.status("국가 메타데이터 색인 중", expanded=True) as status:
            try:
                report = store.index_metadata(countries)
                status.update(
                    label=f"색인 완료 · {report['count']}건", state="complete"
                )
                completed = True
            except ServiceError as exc:
                st.warning(str(exc))
                status.update(label="색인 실패", state="error")
        if completed:
            st.rerun()

    chat_tab, explore_tab, compare_tab = st.tabs(
        ["국가 채팅", "조건으로 찾기", "두 국가 비교"],
        key="active_tab",
        on_change="rerun",
    )
    with chat_tab:
        st.subheader(country_label(item_id))
        with st.expander("기초 메타데이터"):
            st.text(countries_by_id[item_id]["search_text"])
            st.caption("출처: pycountry / Babel CLDR / CountryInfo · 최신성 미보장")

        messages = country_history(st.session_state, item_id)
        for message in messages:
            with st.chat_message(message["role"]):
                if message["role"] == "assistant":
                    show_result(message["result"])
                else:
                    st.write(message["content"])

        question = st.chat_input(
            "이 국가·지역에 대해 질문하세요", disabled=not counts["country_meta"]
        )
        if question:
            messages.append({"role": "user", "content": question})
            with st.chat_message("user"):
                st.write(question)
            with st.chat_message("assistant"):
                result = run_question(
                    cfg,
                    store,
                    llm,
                    countries,
                    item_id,
                    question,
                    method,
                    k,
                    auto_collect,
                )
                if result:
                    messages.append({"role": "assistant", "result": result})
                    show_result(result)

    with explore_tab:
        condition = st.text_input(
            "자연어 조건", placeholder="유럽에서 독일어를 사용하는 국가"
        )
        if st.button("국가·지역 찾기", disabled=not counts["country_meta"]):
            try:
                from world_insight.exploration import explore

                with st.spinner("후보 검색 및 실제 속성 검증 중"):
                    st.session_state.explore_result = explore(
                        store, llm, countries, condition
                    )
            except ServiceError as exc:
                st.warning(str(exc))
            except Exception:
                st.error(
                    "조건 검색 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
                )

        result = st.session_state.get("explore_result")
        if result:
            st.caption(
                "적용 조건: "
                + ", ".join(
                    f"{f['field']} {f['op']} {f['value']}" for f in result["filters"]
                )
            )
            if not result["countries"]:
                st.info("검증된 일치 항목이 없습니다.")
            if result["unknown_ids"]:
                st.caption(f"정보 부족으로 판정 보류: {len(result['unknown_ids'])}건")
            for country in result["countries"]:
                with st.container(border=True):
                    st.write(country_label(country["id"]))
                    region = country.get("region_ko") or "정보 없음"
                    languages = (
                        ", ".join(country.get("languages_ko", [])) or "정보 없음"
                    )
                    st.caption(f"{region} · {languages}")
                    st.button(
                        "이 국가와 대화",
                        key="go_" + country["id"],
                        on_click=select_country,
                        args=(country["id"],),
                    )

    with compare_tab:
        left_column, right_column = st.columns(2)
        left = left_column.selectbox(
            "국가 A",
            country_ids,
            index=country_ids.index("KOR"),
            format_func=country_label,
        )
        right = right_column.selectbox(
            "국가 B",
            country_ids,
            index=country_ids.index("JPN"),
            format_func=country_label,
        )
        topic = st.text_input(
            "비교 질문", "수도·대륙·언어·면적의 공통점과 차이점을 비교해 주세요"
        )
        if st.button("근거로 비교하기", disabled=not counts["country_meta"]):
            if left == right:
                st.info("서로 다른 두 국가를 선택해 주세요.")
            else:
                result = run_question(
                    cfg,
                    store,
                    llm,
                    countries,
                    left,
                    topic,
                    method,
                    k,
                    auto_collect,
                    right,
                )
                if result:
                    st.session_state.comparison = result
        if st.session_state.get("comparison"):
            show_result(st.session_state.comparison)


main()
