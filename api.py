#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import os
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from pathlib import Path

# simple vectorizer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

DATA_PATH = Path("data/materials.json")

class Price(BaseModel):
    value: float | None = None
    currency: str | None = None
    raw: str | None = None

class MaterialItem(BaseModel):
    id: str
    site: str
    category: str
    name: str
    brand: str | None = None
    price: Price
    unit: str | None = None
    url: str
    image_url: str | None = None
    availability: str | None = None
    scraped_at: str

def build_text(r: dict) -> str:
    # same scheme as JSONL so you can swap in real embeddings later
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

def load_data() -> list[dict]:
    if not DATA_PATH.exists():
        raise RuntimeError(f"{DATA_PATH} not found. Run the scraper first.")
    return json.load(open(DATA_PATH, "r", encoding="utf-8"))

app = FastAPI(title="Donizo Materials Vector API (TF-IDF demo)")

DATA = load_data()
TEXTS = [build_text(r) for r in DATA]
VECTORIZER = TfidfVectorizer(min_df=2, ngram_range=(1,2))
MATRIX = VECTORIZER.fit_transform(TEXTS)

@app.get("/materials/{category}", response_model=List[MaterialItem])
def get_by_category(category: str, site: Optional[str] = None, limit: int = 100):
    rows = [r for r in DATA if r["category"].lower() == category.lower()]
    if site:
        rows = [r for r in rows if r["site"].lower() == site.lower()]
    if not rows:
        raise HTTPException(status_code=404, detail="No data for given filters")
    return rows[:limit]

@app.get("/search")
def search(
    q: str = Query(..., min_length=2),
    site: Optional[str] = None,
    category: Optional[str] = None,
    top_k: int = 20
):
    # optional filters first
    idxs = list(range(len(DATA)))
    if site:
        idxs = [i for i in idxs if DATA[i]["site"].lower() == site.lower()]
    if category:
        idxs = [i for i in idxs if DATA[i]["category"].lower() == category.lower()]
    if not idxs:
        raise HTTPException(status_code=404, detail="No data after filters")

    q_vec = VECTORIZER.transform([q])
    sims = cosine_similarity(q_vec, MATRIX[idxs]).ravel()
    order = sims.argsort()[::-1][:top_k]
    out = []
    for j in order:
        i = idxs[j]
        r = DATA[i]
        out.append({
            "score": float(sims[j]),
            "id": r["id"],
            "site": r["site"],
            "category": r["category"],
            "name": r["name"],
            "brand": r.get("brand"),
            "price": r.get("price"),
            "unit": r.get("unit"),
            "url": r["url"]
        })
    return out
