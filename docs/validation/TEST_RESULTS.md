# 검증 결과

## 로컬 재검증 · 2026-11-25

Windows / Python 3.12.10의 새 가상환경에 `requirements.txt`를 설치한 뒤 확인했습니다.

| 검사 | 결과 |
| --- | --- |
| `pip check` | 의존성 충돌 없음 |
| `pytest -q` | **36 passed** |
| 데이터 검사 | 고유 국가·지역 249건, 메타데이터 색인 입력 249건, 시험 노트 232건 |
| 원문 집계 | 11개 국가·지역의 위키백과 문서 26건 |
| 데이터 무결성 | 기준 데이터 세 파일의 SHA256 일치 |

실제 API로 실행한 결과는 아래 2026-10-21 실험 기록을 참고하세요.

## 오프라인 테스트 · 2026-11-04

환경: Windows / Python 3.12.10, `requirements.txt` 기반 가상환경.

| 검사 | 결과 | 근거 |
|---|---|---|
| 의존성 무결성 | `No broken requirements found` | `pip --python .venv check` |
| 오프라인 pytest | **36 passed in 25.14s** | [2026-11-04_pytest.xml](../evidence/2026-11-04_pytest.xml) |
| 데이터 검증 | 국가 249건, 고유 ISO3 249개, 인덱스 249건, 시험 노트 232건 | `scripts/validate_dataset.py`, `cli validate` |
| 현재 수집 원문 | **26건, 11개 국가·지역** | `data/wikipedia_articles.jsonl` 집계 |
| 데이터 무결성 | 기준 데이터 3개의 SHA256 일치 | [기준 해시](../evidence_data_hashes.json) |

테스트는 실제 Chroma 영속 DB·LangGraph·Streamlit AppTest를 실행하고, LLM과 임베딩은 로컬 대역을 사용합니다. API 연결과 모델 응답을 확인하는 실연동 검사와 구분합니다.

검증 명령:

```powershell
python -m pip --python .venv check
.\.venv\Scripts\python.exe scripts/validate_dataset.py
.\.venv\Scripts\python.exe -m world_insight.cli validate
.\.venv\Scripts\python.exe -m pytest -q
```

## 테스트 범위

| 영역 | 확인한 동작 |
|---|---|
| 데이터·색인 | ISO3·필수 필드, 재색인 불변, 청킹 변경·잔여 청크 정리, 공유 문서 ID 충돌 방지 |
| 수집 | 검색 캐시, 원문 URL/pageid 검사, 요청 한도, 429 재시도, 원문 병합 |
| 검색 | 국가 필터, 중복 제거, Top-k, 실제 Chroma의 통제된 MMR 선택 |
| 생성 | JSON 파싱, 근거 번호, 원문 발췌·감사 실패 거부, 비교 양국 근거 |
| 조건·화면 | 실제 속성 판정·결측 구분, 국가 전환 기록, 탐색 카드 이동 |
| 오류 | 키 누락, 외부 오류 상세·인증정보의 화면 비노출 |

## API 연동 실험 · 2026-10-21

GMS Responses API, 실제 임베딩과 수집한 위키백과 원문을 사용했습니다. 원문 23건·295청크 기준으로 측정했습니다.

| 항목 | 결과 | 증빙 |
|---|---|---|
| Responses·임베딩·검색·비교·조건·거절·MMR | 통합 스크립트 7개 항목 passed | [live_verification.json](../evidence/live_verification.json) |
| 메타데이터 재색인 | 249건 unchanged | 같은 JSON |
| 원문 재색인 | 당시 23건 / 295청크 unchanged | 같은 JSON |
| 가나 원문 근거 답변 | 40.256초 | 같은 JSON |
| 그리스 유사도/MMR | 평균 청크 코사인 `0.5488 → 0.4269` | [MMR 비교](MMR_COMPARISON.md) |
| 발췌 불일치 | `quote_mismatch`로 보류 | [실패 사례](../evidence/initial_quote_mismatch.json) |
| 브라우저 | 국가 채팅·인용·조건·비교 화면 | [스크린샷 폴더](../screenshots/) |

실험 데이터 23건과 현재 데이터 26건은 수집 시점이 다릅니다. 295청크는 이 실험의 색인 수이며, 이후 수집한 문서를 포함한 색인 수는 `cli status`로 확인할 수 있습니다. 지연 수치는 단일 실행 기록이며 평균·백분위 응답 시간은 측정하지 않았습니다.

## 남은 검증

전체 국가의 원문 품질·최신성, 다른 OS/Python 환경, 다중 사용자 부하, 검색 정답 세트 평가, 임의 질문의 답변 정확도는 추가 검증이 필요합니다. [실제 API 연동 재검증 절차](../GETTING_STARTED.md#실제-api-연동-검사)
