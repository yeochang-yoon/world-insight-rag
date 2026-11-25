#!/usr/bin/env python3
"""Build a reproducible ISO country/region metadata seed for World Insight AI.
Sources: pycountry (ISO codes), Babel (Korean translations), countryinfo (geography).
No live web connection required. Population intentionally excluded (source is stale).
Run: python scripts/build_dataset.py --output data
"""

import argparse
import csv
import json
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import quote

import babel
import pycountry
from babel import Locale
from countryinfo import CountryInfo

REGION_KO = {
    "Africa": "아프리카",
    "Americas": "아메리카",
    "Asia": "아시아",
    "Europe": "유럽",
    "Oceania": "오세아니아",
    "Polar": "극지방",
    "Antarctic": "남극",
    "Antarctica": "남극",
}


def normalize(value):
    return " ".join(str(value).split()) if value is not None else ""


def make_search_text(row):
    vals = [
        ("국가·지역 이름", row["name_ko"]),
        ("영문 이름", row["name_en"]),
        ("영문 정식 이름", row["official_name_en"]),
        ("ISO 국가 코드", row["id"] + ", " + row["iso2"]),
        ("대륙", row["region_ko"]),
        ("세부 지역", row["subregion_en"]),
        ("수도", row["capital_en"]),
        ("사용 언어", ", ".join(row["languages_ko"]) if row["languages_ko"] else ""),
        ("통화 코드", ", ".join(row["currencies"])),
        ("접경 국가 ISO 코드", ", ".join(row["borders"])),
        ("면적(km²)", str(row["area_km2"]) if row["area_km2"] is not None else ""),
    ]
    return "\n".join(f"{key}: {value}" for key, value in vals if value)


def _geographic_completeness(entry):
    fields = ("region", "capital", "languages", "currencies", "area", "subregion")
    return sum(bool(entry.get(field)) for field in fields)


def build(output: Path):
    output.mkdir(parents=True, exist_ok=True)
    all_info = CountryInfo().all()
    by_alpha2 = {}
    for entry in all_info.values():
        iso = entry.get("ISO") or {}
        code = (iso.get("alpha2") or "").upper()
        if len(code) == 2:
            # countryinfo includes subdivisions sharing the same country code
            # (e.g. Wales and United Kingdom both use GB). Keep the record
            # with the richest country-level geographic attributes.
            if code not in by_alpha2 or _geographic_completeness(
                entry
            ) > _geographic_completeness(by_alpha2[code]):
                by_alpha2[code] = entry

    ko = Locale.parse("ko")
    rows, notes = [], []
    for country in pycountry.countries:
        code2 = country.alpha_2
        geo = by_alpha2.get(code2, {})
        name_ko = normalize(ko.territories.get(code2) or country.name)
        name_en = normalize(country.name)
        region_en = normalize(geo.get("region"))
        capital = normalize(geo.get("capital"))
        languages = geo.get("languages") or []
        language_names = [
            normalize(ko.languages.get(code) or code) for code in languages
        ]
        area = geo.get("area")
        if not isinstance(area, (int, float)) or area <= 0:
            area = None
        else:
            area = round(float(area), 2)
            if area.is_integer():
                area = int(area)
        wiki_query = name_ko
        record = {
            "id": country.alpha_3,
            "iso2": code2,
            "iso3": country.alpha_3,
            "name_ko": name_ko,
            "name_en": name_en,
            "official_name_en": normalize(
                getattr(country, "official_name", country.name)
            ),
            "region_en": region_en or None,
            "region_ko": REGION_KO.get(region_en),
            "subregion_en": normalize(geo.get("subregion")) or None,
            "capital_en": capital or None,
            "languages": languages,
            "languages_ko": language_names,
            "currencies": geo.get("currencies") or [],
            "borders": geo.get("borders") or [],
            "area_km2": area,
            "data_coverage": "extended_geography" if geo else "iso_name_only",
            "wiki_search_query": wiki_query,
            # Search-page URL, *not* a confirmed individual Wikipedia article.
            "wiki_search_url": "https://ko.wikipedia.org/w/index.php?search="
            + quote(wiki_query),
            "sources": ["pycountry", "Babel/Unicode CLDR"]
            + (["countryinfo"] if geo else []),
        }
        record["search_text"] = make_search_text(record)
        rows.append(record)
        if geo:
            # This is a locally synthesized trial note from countryinfo structured fields,
            # NOT text fetched from Wikipedia. Do not cite as a wiki article.
            statements = [
                f"{name_ko}({name_en})은(는) {REGION_KO.get(region_en, region_en) or '지역 정보 미확인'}에 분류되는 국가 또는 지역입니다."
            ]
            if capital:
                statements.append(f"이 데이터셋에 기록된 수도는 {capital}입니다.")
            if geo.get("subregion"):
                statements.append(f"세부 지역은 {geo['subregion']}입니다.")
            if languages:
                statements.append("언어 정보: " + ", ".join(language_names) + ".")
            if geo.get("currencies"):
                statements.append("통화 코드: " + ", ".join(geo["currencies"]) + ".")
            if area is not None:
                statements.append(f"면적 정보: {area:,} km².")
            notes.append(
                {
                    "id": f"{country.alpha_3}:countryinfo:0",
                    "item_id": country.alpha_3,
                    "title": f"{name_ko} - 기본 지리 정보 (CountryInfo 기반 시험용)",
                    "content": " ".join(statements),
                    "source_type": "structured_reference_note",
                    "source_url": "https://github.com/porimol/countryinfo",
                    "source_data": "countryinfo 0.1.2, local reconstructed summary",
                    "is_original_wikipedia_article": False,
                    "license_notice": "CountryInfo MIT; underlying geographic facts may be compiled from Wikipedia. Verify original material terms for republication.",
                }
            )

    rows.sort(key=lambda r: (r["name_ko"], r["iso2"]))
    notes.sort(key=lambda x: x["item_id"])
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids)), "Duplicate ISO3 keys"
    assert len(rows) >= 100, "Dataset fails 100-item requirement"
    assert all(r["name_ko"] and r["search_text"] for r in rows)

    (output / "countries.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (output / "countries.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "id",
                "iso2",
                "name_ko",
                "name_en",
                "official_name_en",
                "region_ko",
                "region_en",
                "subregion_en",
                "capital_en",
                "languages_ko",
                "currencies",
                "area_km2",
                "data_coverage",
                "wiki_search_query",
                "wiki_search_url",
            ],
        )
        writer.writeheader()
        for r in rows:
            record = {
                k: (", ".join(r[k]) if isinstance(r.get(k), list) else r.get(k))
                for k in writer.fieldnames
            }
            writer.writerow(record)
    with (output / "metadata_index.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(
                json.dumps(
                    {
                        "id": r["id"],
                        "page_content": r["search_text"],
                        "metadata": {
                            "item_id": r["id"],
                            "name_ko": r["name_ko"],
                            "source_type": "item_metadata",
                            "source_url": "https://github.com/flyingcircusio/pycountry",
                            "region_en": r["region_en"] or "",
                        },
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    with (output / "structured_country_notes.jsonl").open("w", encoding="utf-8") as f:
        for n in notes:
            f.write(json.dumps(n, ensure_ascii=False) + "\n")
    result = {
        "generated_at": date.today().isoformat(),
        "domain": "세계 국가·지역 지리 지식 AI",
        "total_items": len(rows),
        "countryinfo_matched_items": len(notes),
        "items_missing_countryinfo": len(rows) - len(notes),
        "items_with_capital": sum(r["capital_en"] is not None for r in rows),
        "items_with_region": sum(r["region_ko"] is not None for r in rows),
        "items_with_languages": sum(bool(r["languages"]) for r in rows),
        "items_with_currency": sum(bool(r["currencies"]) for r in rows),
        "items_with_korean_name": sum(bool(r["name_ko"]) for r in rows),
        "region_counts": dict(Counter(r["region_en"] or "unknown" for r in rows)),
        "source_package_versions": {
            "pycountry": pycountry.__version__,
            "babel": babel.__version__,
            "countryinfo": "0.1.2 (environment installed package)",
        },
        "external_wikipedia_articles_downloaded": 0,
        "notes": "CountryInfo geographic values may be outdated; population deliberately excluded. Wikipedia article URLs are search links until verified by collect_wikipedia.py.",
    }
    (output / "validation_report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("data"))
    args = parser.parse_args()
    build(args.output)
