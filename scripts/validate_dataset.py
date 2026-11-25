import json
from pathlib import Path

DIR = Path(__file__).resolve().parent.parent / "data"
items = json.loads((DIR / "countries.json").read_text(encoding="utf-8"))
notes = [
    json.loads(x)
    for x in (DIR / "structured_country_notes.jsonl")
    .read_text(encoding="utf-8")
    .splitlines()
    if x.strip()
]
index = [
    json.loads(x)
    for x in (DIR / "metadata_index.jsonl").read_text(encoding="utf-8").splitlines()
    if x.strip()
]
ids = {i["id"] for i in items}
assert len(items) >= 100
assert len(ids) == len(items)
assert len(index) == len(items)
assert all(x["id"] in ids and x["name_ko"] and x["search_text"] for x in items)
assert all(n["item_id"] in ids for n in notes)
assert len({n["item_id"] for n in notes}) == len(notes)
assert all(
    n["source_type"] == "structured_reference_note"
    and n["is_original_wikipedia_article"] is False
    for n in notes
)
print(
    f"PASS: {len(items)} unique items, {len(index)} index records, {len(notes)} test reference notes"
)
print(f"Korean names: {sum(bool(x['name_ko']) for x in items)}/{len(items)}")
print(f"Capital: {sum(bool(x['capital_en']) for x in items)}/{len(items)}")
print(f"Region: {sum(bool(x['region_ko']) for x in items)}/{len(items)}")
