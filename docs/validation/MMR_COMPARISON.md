# 유사도 검색과 MMR 비교

2026-10-21에 GMS의 `text-embedding-3-small` 임베딩과 수집한 그리스 원문으로 비교했다. [실험 원본 JSON](../evidence/mmr_live.json)

질문: **그리스의 지리적 특징과 역사**. item_id=GRC, k=4, fetch_k=20, MMR lambda_mult=.3. 메타데이터 GRC는 두 경우 모두 항상 포함하므로 아래 표는 외부 청크만 비교한다.

| 순서 | 유사도 검색 | MMR |
|---|---|---|
| 1 | GRC:wikipedia:1458:2 | GRC:wikipedia:1458:2 |
| 2 | GRC:wikipedia:323874:0 | GRC:wikipedia:1458:27 |
| 3 | GRC:wikipedia:1458:12 | GRC:wikipedia:1458:11 |
| 4 | GRC:wikipedia:324730:0 | GRC:wikipedia:1458:14 |

선택된 외부 청크 사이의 평균 코사인 유사도는 기본 검색 **0.5488**, MMR **0.4269**였다. MMR은 그리스 문서 한 편의 서로 다른 부분 네 곳을 선택했다. 평균 코사인 유사도가 낮을수록 선택된 청크가 임베딩 공간에서 서로 덜 비슷하다. 답변 정확도는 질문과 정답 근거를 갖춘 별도의 평가가 필요하다.

통제된 오프라인 pytest에서는 query=[1,0], 거의 같은 near1/near2와 다른 방향의 diverse 벡터를 실제 Chroma에 넣었다. 유사도 검색은 near1·near2, lambda=.1의 MMR은 near1·diverse를 골랐다. 이는 알고리즘 동작 검증이며 실제 LLM·웹 검색 성공과 구분한다.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_mmr.py -q
.\.venv\Scripts\python.exe scripts/verify_live.py
```

CLI `benchmark`는 선택된 청크와 검색 시간을 출력한다. 질문·청크 설정·수집 원문·lambda가 바뀌면 결과가 달라진다. 위 명령의 `verify_live.py`와 CLI `benchmark`는 실험 JSON을 갱신하므로 기록을 보존하려면 실행 전에 복사한다. [CLI 실행 예시](../GETTING_STARTED.md#cli-예제)
