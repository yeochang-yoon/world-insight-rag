# 데이터 출처와 이용 조건

## 현재 배포 데이터

| 파일 | 내용 | 기록된 출처 |
|---|---|---|
| `data/countries.json`, `countries.csv` | 국가·지역 249건 | pycountry, Babel/CLDR, CountryInfo |
| `data/metadata_index.jsonl` | 국가별 검색 텍스트 249건 | 위 메타데이터 |
| `data/structured_country_notes.jsonl` | 구조화 데이터로 만든 시험 노트 232건 | CountryInfo 기반, 실제 위키백과 원문 아님 |
| `data/wikipedia_articles.jsonl` | 실제 수집 원문 26건·11개 국가/지역 | 한국어 위키백과 MediaWiki API |

위키백과 원문에는 `source_url`, `wiki_pageid`, `revision_id`, `collected_at`, `history_url`, `license_notice`가 있습니다. 현재 레코드의 고지는 `CC BY-SA 4.0; original authors: article history; extracted plain text and split for RAG`입니다. 원문·리비전·저작자 이력 링크를 함께 보존하며, plain text 추출·청킹 사실을 표시합니다.

`wiki_search_url`은 검색 결과 화면 링크이며 개별 원문의 출처로 사용하지 않습니다. 실제 원문은 API가 반환한 문서 식별자와 URL로 구분합니다. 스크린샷·검증 JSON의 발췌 역시 해당 원문 출처를 따릅니다.

## 출처 링크

- [pycountry](https://github.com/flyingcircusio/pycountry): ISO 국가·지역 코드와 영문 이름
- [Babel](https://babel.pocoo.org/): CLDR 기반 한국어 이름·언어명
- [CountryInfo](https://github.com/porimol/countryinfo): 수도·대륙·언어·면적 등
- [한국어 위키백과](https://ko.wikipedia.org/): 개별 원문 URL·이력은 각 레코드에 기록
- [MediaWiki API 이용 안내](https://www.mediawiki.org/wiki/API:Etiquette): User-Agent·요청 간격·캐시 구현의 참고 자료

## 출처별 라이선스 고지

| 출처 | 고지 |
|---|---|
| pycountry | 패키지 LGPL-2.1-only. ISO 표준 관련 사용 조건은 별도 확인 |
| Babel / CLDR | Babel 프로그램 BSD-3-Clause, CLDR 데이터는 별도 Unicode License. [Babel 라이선스 문서](https://babel.pocoo.org/en/latest/license.html) |
| CountryInfo | 패키지 MIT. 포함 데이터는 위키백과 등을 기반으로 하며 원자료의 출처와 이용 조건도 함께 확인 |
| 한국어 위키백과 | 수집 레코드에 CC BY-SA 4.0 고지·원문·리비전·저작자 이력 링크와 변형 사실 표시 |

패키지와 데이터는 각 출처의 이용 조건을 따릅니다. 위키백과 발췌를 포함한 데이터·검증 결과를 재사용할 때도 해당 출처와 저작자 이력·라이선스 고지를 함께 유지해야 합니다.

## 데이터의 한계

ISO 국가·지역 목록은 독립국만의 목록이 아닙니다. CountryInfo의 갱신일이 불명확하고 결측값도 있으므로 최신 정치·인구·비자 정보를 보장하지 않습니다. 위키백과 수집일은 개별 사실의 최신성을 보장하지 않습니다. 시험 노트·구조화 속성·실제 수집 원문은 구분해 보관합니다.
