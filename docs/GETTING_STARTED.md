# 상세 실행 가이드

프로젝트 루트에서 명령을 실행합니다. 가상환경 설치와 기본 실행은 [README의 실행 방법](../README.md#실행-방법)을 따르세요. `requirements.txt`는 주요 패키지 버전을 지정하고, `requirements-lock.txt`는 최초 검증에 사용한 Windows / Python 3.12 환경의 전체 버전을 기록합니다.

## API 연결과 로컬 색인

`.env`는 `.env.example`을 복사해 만듭니다. 기본 설정은 SSAFY GMS이며, Responses API와 임베딩 API는 같은 키와 주소를 사용합니다. `probe`에서 두 API의 연결을 확인할 수 있습니다. 호출은 제공자의 사용량에 반영됩니다.

```powershell
.\.venv\Scripts\python.exe -m world_insight.cli probe
.\.venv\Scripts\python.exe -m world_insight.cli index-meta
.\.venv\Scripts\python.exe -m world_insight.cli index-docs
.\.venv\Scripts\python.exe -m world_insight.cli status
.\run.ps1
```

Chroma 데이터베이스는 기본 `storage/chroma`에 생성됩니다. [로컬 앱](http://127.0.0.1:8502)에서 추가 수집 옵션을 해제하면 동봉된 원문과 메타데이터를 사용할 수 있습니다. 외부 원문이 없는 국가의 답변은 메타데이터 범위로 제한됩니다.

## CLI 예제

```powershell
.\.venv\Scripts\python.exe -m world_insight.cli ask GHA '가나의 지리와 역사를 설명해 주세요' --no-collect
.\.venv\Scripts\python.exe -m world_insight.cli ask GHA '두 나라의 수도와 언어를 비교해 주세요' --compare GRC --no-collect
.\.venv\Scripts\python.exe -m world_insight.cli explore '유럽에서 독일어를 사용하는 국가'
.\.venv\Scripts\python.exe -m world_insight.cli benchmark --item GRC --question '그리스의 지리와 역사'
```

`ask`는 `docs/evidence/last_ask.json`, `benchmark`는 `docs/evidence/mmr_live.json`을 갱신합니다. 기존 실험 기록을 보존하려면 실행 전에 복사해 두세요. `benchmark` 출력에는 검색 시간과 선택 청크가 포함됩니다.

## 새 원문 수집

`.env`의 `WIKI_CONTACT`에 연락 가능한 이메일을 설정합니다. 이 값은 MediaWiki 요청의 User-Agent에 포함됩니다. UI에서는 **질문에 맞는 위키백과 문서 수집**을 켜고 질문합니다. CLI에서는 수집 뒤 원문 색인을 실행합니다.

```powershell
.\.venv\Scripts\python.exe scripts/collect_wikipedia.py --item KOR,JPN --limit 0
.\.venv\Scripts\python.exe -m world_insight.cli index-docs
```

수집 결과는 기존 `data/wikipedia_articles.jsonl`에 병합됩니다. 수집한 원문과 성공한 검색 결과는 캐시하며, 자동 갱신 주기는 구현되어 있지 않습니다.

## 환경 변수

| 변수 | 기본값 또는 역할 |
| --- | --- |
| `OPENAI_API_KEY` | 답변 생성·임베딩에 사용할 키. `GMS_KEY`도 지원 |
| `OPENAI_BASE_URL` | `https://gms.ssafy.io/gmsapi/api.openai.com/v1` |
| `OPENAI_MODEL` | `gpt-6-luna` |
| `EMBEDDING_MODEL` | `text-embedding-3-small` |
| `WIKI_CONTACT` | 새 원문 수집 시 사용하는 연락처 |
| `CHROMA_DIR` | `storage/chroma` |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `1000` / `200`, 문자 단위 |
| `TOP_K` / `FETCH_K` / `MMR_LAMBDA` | `4` / `20` / `0.5` |
| `WIKI_INTERVAL` / `WIKI_MAX_REQUESTS` | 요청 간격 `0.7`초 / 실행당 `200`회 |
| `API_TIMEOUT` | LLM 요청 `60`초, 위키 요청 최대 `30`초 |

임베딩 모델을 변경할 때는 새 `CHROMA_DIR`에 메타데이터와 원문을 색인합니다. 청킹 설정 변경 후에는 `index-docs`를 다시 실행합니다. `.env`, `.venv/`, `storage/`와 수집 캐시는 Git에서 제외됩니다.

## 설치·실행 문제 해결

| 상황 | 확인할 항목 |
| --- | --- |
| `probe` 실패 | 키, API 주소, Responses API와 임베딩 API 지원 여부 |
| 메타데이터 색인이 비어 있음 | `index-meta` 실행 결과와 `CHROMA_DIR` |
| 위키백과 원문을 찾을 수 없음 | `index-docs` 실행 여부와 선택 국가의 수집 원문 |
| 추가 수집 실패 | `WIKI_CONTACT`, 네트워크, 현재 실행의 요청 한도 |
| PowerShell이 `run.ps1` 실행을 막음 | README의 `python.exe -m streamlit run` 명령 사용 |

가상환경의 Python은 생성됐지만 Windows에서 `ensurepip`가 실패했다면 전역 pip로 대상 가상환경을 지정할 수 있습니다.

```powershell
python -m pip --python .venv install pip
python -m pip --python .venv install -r requirements.txt
```

## 실제 API 연동 검사

색인과 API 설정을 완료한 후 통합 검사를 실행합니다. 실제 API를 호출하며 `docs/evidence/`의 실험 기록을 갱신합니다.

```powershell
.\.venv\Scripts\python.exe scripts/verify_live.py
```

[자동 테스트와 API 연동 검증 결과](validation/TEST_RESULTS.md)
