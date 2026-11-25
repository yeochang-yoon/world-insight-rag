from streamlit.testing.v1 import AppTest

from world_insight.config import ROOT, Settings


def test_missing_key_ui(monkeypatch):
    monkeypatch.setattr(Settings, "load", classmethod(lambda cls: Settings()))
    app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=30)
    assert not app.exception
    assert any("API 키" in w.value for w in app.warning)


def test_ui_country_switch_preserves_history(monkeypatch, store, countries, cfg):
    import streamlit as st

    from world_insight.prompts import CONDITION_PROMPT

    st.cache_resource.clear()
    store.index_metadata(countries)

    class OfflineLLM:
        def json(self, system, data):
            if system == CONDITION_PROMPT:
                return {
                    "filters": [{"field": "name_ko", "op": "eq", "value": "독일"}],
                    "unsupported": False,
                }
            return {"answer": "제공된 문서에서 확인할 수 없습니다.", "claims": []}

    monkeypatch.setattr(Settings, "load", classmethod(lambda cls: cfg))
    monkeypatch.setattr("world_insight.indexing.CountryStore", lambda settings: store)
    monkeypatch.setattr("world_insight.llm.ResponsesLLM", lambda settings: OfflineLLM())
    app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=30)
    assert not app.exception
    assert app.selectbox(key="selected_country").value == "KOR"
    app.checkbox[0].uncheck().run()
    app.chat_input[0].set_value("한국 질문 기록").run(timeout=30)
    assert len(app.session_state["histories"]["KOR"]) == 2
    app.selectbox(key="selected_country").set_value("JPN").run()
    assert app.session_state["histories"]["JPN"] == []
    app.selectbox(key="selected_country").set_value("KOR").run()
    assert len(app.session_state["histories"]["KOR"]) == 2
    # Result-card callback must update the sidebar selection on the next run.
    app.text_input[0].set_value("독일")
    next(b for b in app.button if b.label == "국가·지역 찾기").click().run(timeout=30)
    next(b for b in app.button if b.label == "이 국가와 대화").click().run()
    assert app.selectbox(key="selected_country").value == "DEU" and not app.exception
    st.cache_resource.clear()
