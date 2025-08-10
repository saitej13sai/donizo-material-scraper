import json
import os
from pathlib import Path

IN = Path("data/materials.json")
OUT = Path("data/materials.jsonl")
OUT.parent.mkdir(parents=True, exist_ok=True)

def build_text(r: dict) -> str:
    price_raw = (r.get("price") or {}).get("raw") or ""
    brand = r.get("brand") or ""
    unit = r.get("unit") or ""
    parts = [
        r.get("site",""),
        r.get("category",""),
        brand,
        r.get("name",""),
        price_raw,
        unit,
        r.get("url","")
    ]
    return " | ".join([p for p in parts if p])

def main():
    if not IN.exists():
        raise SystemExit(f"Input not found: {IN}. Run scraper first.")
    rows = json.load(open(IN, "r", encoding="utf-8"))
    with open(OUT, "w", encoding="utf-8") as out:
        for r in rows:
            rec = {
                "id": r["id"],
                "text": build_text(r),
                "meta": {
                    "site": r.get("site"),
                    "category": r.get("category"),
                    "brand": r.get("brand"),
                    "price_value": (r.get("price") or {}).get("value"),
                    "currency": (r.get("price") or {}).get("currency"),
                    "url": r.get("url"),
                }
            }
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"Wrote {OUT} ({sum(1 for _ in open(OUT,'r',encoding='utf-8'))} lines)")

if __name__ == "__main__":
    main()
