import hashlib
import json
from pathlib import Path

from .config import ROOT


def load_countries(path=None):
    rows = json.loads(
        Path(path or ROOT / "data/countries.json").read_text(encoding="utf-8")
    )
    ids = [r["iso3"] for r in rows]
    if len(ids) != len(set(ids)) or any(r["id"] != r["iso3"] for r in rows):
        raise ValueError("Country IDs must be unique ISO3 codes")
    if any(
        not r.get("name_ko") or not r.get("name_en") or not r.get("iso2") for r in rows
    ):
        raise ValueError("Required country fields missing")
    return rows


def search_text(country):
    return country.get("search_text") or json.dumps(
        {
            k: country.get(k)
            for k in (
                "name_ko",
                "name_en",
                "iso3",
                "capital_en",
                "region_ko",
                "languages_ko",
                "currencies",
                "area_km2",
            )
        },
        ensure_ascii=False,
    )


def read_jsonl(path):
    p = Path(path)
    return (
        [json.loads(s) for s in p.read_text(encoding="utf-8").splitlines() if s.strip()]
        if p.exists()
        else []
    )


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
