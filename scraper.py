"""
Donizo - Material Price Scraper
- Sites: Leroy Merlin (Playwright), Castorama (requests), ManoMano (Playwright)
- Config-driven selectors + pagination
- Outputs JSON; optional FastAPI endpoint for review (bonus)
"""

import argparse
import dataclasses
import hashlib
import json
import os
import random
import re
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterable, List, Optional, Tuple
from urllib.parse import urljoin, urlencode, urlparse, parse_qs, urlunparse

import requests
import yaml
from bs4 import BeautifulSoup, Tag
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---------------- Models ----------------
@dataclasses.dataclass
class Price:
    value: Optional[float]
    currency: Optional[str]
    raw: Optional[str]

@dataclasses.dataclass
class MaterialItem:
    id: str
    site: str
    category: str
    name: str
    brand: Optional[str]
    price: Price
    unit: Optional[str]
    url: str
    image_url: Optional[str]
    availability: Optional[str]
    scraped_at: str

# ---------------- Utils ----------------
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
]

PRICE_REGEX = re.compile(
    r"(?P<currency>€|EUR|£)\s*(?P<amount>\d+[.,]?\d*(?:[.,]\d{2})?)|(?P<amount2>\d+[.,]?\d*)\s*(?P<currency2>€|EUR|£)",
    re.I,
)
UNIT_REGEX = re.compile(r"(?:/|par)\s*(m2|m²|m3|L|l|kg|pièce|unité|paquet|boîte|m|ml)\b", re.I)

def stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join([p or "" for p in parts]).encode("utf-8")).hexdigest()[:16]

def parse_price_unit(text: Optional[str]) -> Tuple[Optional[float], Optional[str], Optional[str], Optional[str]]:
    if not text:
        return None, None, None, None
    t = text.replace("\xa0", " ").strip()
    m = PRICE_REGEX.search(t)
    currency = (m.group("currency") or m.group("currency2") or "").strip() if m else None
    amount = (m.group("amount") or m.group("amount2") or "").replace(" ", "").replace(",", ".") if m else None
    val = None
    if amount:
        try:
            val = float(amount)
        except ValueError:
            val = None
    if currency and currency.upper().startswith("E"):
        currency = "€"
    unit = None
    mu = UNIT_REGEX.search(t)
    if mu:
        unit = mu.group(1)
    return val, currency, unit, t

def text_or_none(node: Optional[Tag]) -> Optional[str]:
    return node.get_text(strip=True) if node else None

def make_session() -> requests.Session:
    s = requests.Session()
    retries = Retry(
        total=5, backoff_factor=0.5,
        status_forcelist=[403, 429, 500, 502, 503, 504],
        allowed_methods=["GET", "HEAD"]
    )
    adapter = HTTPAdapter(max_retries=retries, pool_maxsize=10)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    s.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Connection": "keep-alive",
    })
    return s

def paginate(url: str, param: str, start: int, max_pages: int) -> Iterable[str]:
    parsed = urlparse(url)
    q = parse_qs(parsed.query)
    for p in range(start, start + max_pages):
        q[param] = [str(p)]
        new_q = urlencode({k: (v[0] if isinstance(v, list) else v) for k, v in q.items()})
        yield urlunparse(parsed._replace(query=new_q))

# ---------------- Playwright fallback ----------------
def _has_playwright() -> bool:
    try:
        import playwright  # noqa
        return True
    except Exception:
        return False

@contextmanager
def playwright_page(user_agent: Optional[str] = None, locale: str = "fr-FR"):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=user_agent or random.choice(USER_AGENTS),
            locale=locale, viewport={"width": 1366, "height": 900}
        )
        page = ctx.new_page()
        try:
            yield page
        finally:
            ctx.close(); browser.close()

def fetch_with_playwright(url: str, wait_selector: Optional[str] = None, delay_ms: int = 800) -> str:
    if not _has_playwright():
        raise RuntimeError("Playwright not installed. Run: python -m playwright install chromium")
    with playwright_page() as page:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        if wait_selector:
            try:
                page.wait_for_selector(wait_selector, timeout=15000)
            except Exception:
                pass
        page.wait_for_timeout(delay_ms)
        return page.content()

# ---------------- Core scraper ----------------
class SiteScraper:
    def __init__(self, site_key: str, site_cfg: dict, session: requests.Session):
        self.site_key = site_key
        self.cfg = site_cfg
        self.S = site_cfg["selectors"]
        self.pag = site_cfg.get("pagination", {})
        self.throttle = float(site_cfg.get("throttle_seconds", 0.5))
        self.session = session
        self.use_playwright = site_cfg.get("driver", "").lower() == "playwright"

    def _fetch_html(self, url: str) -> str:
        time.sleep(self.throttle)
        r = self.session.get(url, timeout=30)
        if r.status_code == 200 and r.text.strip():
            return r.text
        if self.use_playwright or r.status_code in (403, 429):
            try:
                return fetch_with_playwright(url, wait_selector=self.S.get("product_card"))
            except Exception as e:
                print(f"[warn] Playwright failed on {url}: {e}")
        r.raise_for_status()
        return r.text

    def fetch(self, url: str) -> BeautifulSoup:
        return BeautifulSoup(self._fetch_html(url), "lxml")

    def iterate_pages(self, start_url: str) -> Iterable[tuple[str, BeautifulSoup]]:
        param = self.pag.get("param")
        start_page = int(self.pag.get("start_page", 1))
        max_pages = int(self.pag.get("max_pages", 10))
        if param:
            for url in paginate(start_url, param, start_page, max_pages):
                try:
                    yield url, self.fetch(url)
                except Exception as e:
                    print(f"[warn] fetch failed: {e}")
        else:
            try:
                yield start_url, self.fetch(start_url)
            except Exception as e:
                print(f"[warn] fetch failed: {e}")

    def parse_card(self, base_url: str, card: Tag, category: str) -> Optional[MaterialItem]:
        container = card
        if card.name == "a":
            container = card.find_parent(["li", "article", "div"]) or card
            href = card.get("href")
        else:
            url_node = container.select_one(self.S.get("url")) if self.S.get("url") else None
            href = url_node.get("href") if url_node else None
        full_url = urljoin(base_url, href) if href else base_url

        name_node = container.select_one(self.S.get("name")) if self.S.get("name") else None
        name = (text_or_none(name_node) if name_node else None) or (text_or_none(card) if card.name == "a" else None)
        if not name:
            return None

        brand = None
        if self.S.get("brand"):
            b = container.select_one(self.S["brand"])
            if b:
                brand = text_or_none(b) or None

        price_text = None
        if self.S.get("price"):
            p = container.select_one(self.S["price"])
            if p:
                price_text = text_or_none(p)
        if not price_text:
            for t in container.stripped_strings:
                if "€" in t:
                    price_text = t; break

        val, cur, unit, raw = parse_price_unit(price_text)

        img_url = None
        if self.S.get("image"):
            img = container.select_one(self.S["image"])
            if img:
                src = img.get("src") or img.get("data-src")
                if src:
                    img_url = urljoin(base_url, src)

        availability = None
        if self.S.get("availability"):
            a = container.select_one(self.S["availability"])
            if a:
                availability = text_or_none(a) or None

        return MaterialItem(
            id=stable_id(self.site_key, category, name, full_url),
            site=self.site_key,
            category=category,
            name=name,
            brand=brand,
            price=Price(value=val, currency=cur, raw=raw),
            unit=unit,
            url=full_url,
            image_url=img_url,
            availability=availability,
            scraped_at=datetime.now(timezone.utc).isoformat(),
        )

    def scrape_category(self, category_key: str, cat_cfg: dict, limit: int) -> List[MaterialItem]:
        items: List[MaterialItem] = []
        start_url = cat_cfg["url"]
        for page_url, soup in self.iterate_pages(start_url):
            cards = soup.select(self.S["product_card"])
            if not cards and page_url == start_url:
                try:
                    soup = self.fetch(start_url)
                    cards = soup.select(self.S["product_card"])
                except Exception:
                    pass
            for card in cards:
                it = self.parse_card(page_url, card, category_key)
                if it and it.price.value is not None:
                    items.append(it)
                    if len(items) >= limit:
                        return items
        return items

# ---------------- Runner ----------------
def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def to_serializable(items: List[MaterialItem]) -> List[dict]:
    return [
        {
            "id": i.id,
            "site": i.site,
            "category": i.category,
            "name": i.name,
            "brand": i.brand,
            "price": {"value": i.price.value, "currency": i.price.currency, "raw": i.price.raw},
            "unit": i.unit,
            "url": i.url,
            "image_url": i.image_url,
            "availability": i.availability,
            "scraped_at": i.scraped_at,
        }
        for i in items
    ]

def run_scrape(args) -> List[MaterialItem]:
    cfg = load_config(args.config)
    session = make_session()
    all_items: List[MaterialItem] = []

    sites = cfg["sites"]
    target_sites = list(sites.keys()) if args.site == "all" else [args.site]
    categories_filter = set([c.strip() for c in args.categories.split(",") if c.strip()]) if args.categories else None

    for site_key in target_sites:
        site_cfg = sites[site_key]
        scraper = SiteScraper(site_key, site_cfg, session=session)
        for cat_key, cat_cfg in site_cfg["categories"].items():
            if categories_filter and cat_key not in categories_filter:
                continue
            got = scraper.scrape_category(cat_key, cat_cfg, limit=args.limit_per_category)
            all_items.extend(got)
            print(f"[info] {site_key}/{cat_key}: {len(got)} items")

    # dedup
    dedup = {}
    for it in all_items:
        dedup[it.id] = it
    return list(dedup.values())

def write_output(items: List[MaterialItem], out_path: str):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(to_serializable(items), f, ensure_ascii=False, indent=2)

def maybe_start_server(args, items: List[MaterialItem]):
    if not args.serve:
        return
    from fastapi import FastAPI, HTTPException
    import uvicorn

    app = FastAPI(title="Donizo Materials API (Sim)")
    data = to_serializable(items)

    @app.get("/materials/{category}")
    def get_by_category(category: str, site: Optional[str] = None, limit: int = 100):
        rows = [r for r in data if r["category"].lower() == category.lower()]
        if site:
            rows = [r for r in rows if r["site"].lower() == site.lower()]
        if not rows:
            raise HTTPException(status_code=404, detail="No data for given filters")
        return rows[:limit]

    print("Starting FastAPI at http://127.0.0.1:8000 ...")
    uvicorn.run(app, host="0.0.0.0", port=8000)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="config/scraper_config.yaml")
    p.add_argument("--site", default="all", help="all | leroymerlin | castorama | manomano")
    p.add_argument("--categories", default="", help="Comma-separated, e.g., tiles,sinks,paint")
    p.add_argument("--limit-per-category", type=int, default=200)
    p.add_argument("--out", default="data/materials.json")
    p.add_argument("--serve", action="store_true")
    args = p.parse_args()

    items = run_scrape(args)
    write_output(items, args.out)
    print(f"[done] Wrote {len(items)} items -> {args.out}")

    if len(items) < 100:
        print("[warn] < 100 items. Increase max_pages/limits or retry later.")
    maybe_start_server(args, items)

if __name__ == "__main__":
    main()
