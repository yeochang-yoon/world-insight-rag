"""Audit credentials, original data and missing attributes without exposing secrets."""

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from world_insight.config import ROOT, Settings
from world_insight.data import atomic_json, load_countries, read_jsonl


def main():
    rows = load_countries()
    articles = read_jsonl(ROOT / "data/wikipedia_articles.jsonl")
    missing = {
        f: [r["id"] for r in rows if r.get(f) in (None, "", [])]
        for f in ("capital_en", "region_en", "languages", "currencies", "area_km2")
    }
    missing_self = [
        i
        for i in {r["item_id"] for r in articles}
        if not any(r["item_id"] == i and r.get("is_country_article") for r in articles)
    ]
    atomic_json(
        ROOT / "data/quality_audit.json",
        {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "items": len(rows),
            "missing_fields": missing,
            "invalid_area_ids": [
                r["id"]
                for r in rows
                if r.get("area_km2") is not None
                and (not isinstance(r["area_km2"], (int, float)) or r["area_km2"] <= 0)
            ],
            "actual_documents": len(articles),
            "external_country_ids": sorted({r["item_id"] for r in articles}),
            "countries_without_self_article": missing_self,
            "freshness": "CountryInfo update date unavailable; no all-country factual correction performed; originals preserved",
        },
    )
    baseline = json.loads(
        (ROOT / "docs/evidence_data_hashes.json").read_text(encoding="utf-8-sig")
    )
    unchanged = all(
        hashlib.sha256((ROOT / "data" / Path(x["Path"]).name).read_bytes())
        .hexdigest()
        .upper()
        == x["Hash"]
        for x in baseline
    )
    key = Settings.load().api_key
    paths = []
    for folder in ("world_insight", "scripts", "tests", "docs", "logs"):
        directory = ROOT / folder
        if directory.exists():
            paths.extend(
                p
                for p in directory.rglob("*")
                if p.is_file()
                and p.suffix
                in (".py", ".json", ".jsonl", ".md", ".txt", ".log", ".xml")
            )
    paths.extend(
        ROOT / n
        for n in (
            "app.py",
            "README.md",
            "requirements.txt",
            "requirements-lock.txt",
            ".env.example",
            ".gitignore",
            "run.ps1",
        )
    )
    leaked = [
        str(p.relative_to(ROOT))
        for p in paths
        if key and key in p.read_text(encoding="utf-8-sig")
    ]
    report = {
        "scanned_files": len(paths),
        "credential_matches": len(leaked),
        "leaked_file_names": leaked,
        "original_three_data_hashes_unchanged": unchanged,
        "missing_counts": {k: len(v) for k, v in missing.items()},
        "country_self_articles_complete_for_collected_items": not missing_self,
    }
    atomic_json(ROOT / "docs/evidence/security_and_data_audit.json", report)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(bool(leaked) or not unchanged)


if __name__ == "__main__":
    raise SystemExit(main())
