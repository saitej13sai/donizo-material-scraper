import pytest
from bs4 import BeautifulSoup
from scraper import parse_price_unit, SiteScraper, MaterialItem, make_session

def test_parse_price_unit_variants():
    v, c, u, raw = parse_price_unit("19,90 € / m²")
    assert c == "€" and abs(v - 19.90) < 0.01 and u in ("m²", "m2")
    v, c, u, raw = parse_price_unit("Prix: 8.99€ / M2")
    assert c == "€" and abs(v - 8.99) < 0.01 and u.lower() in ("m²", "m2")

def test_parse_card_anchor_minimal():
    html = '''
    <div class="product">
      <a href="/product/D1_CAFR.prd">Carrelage Sol Gris 60x60</a>
      <div class="product__brand">Ecoceramic</div>
      <div class="price__value">19,95 € / m2</div>
      <img src="https://example.com/p.jpg"/>
    </div>
    '''
    soup = BeautifulSoup(html, "lxml")
    card = soup.select_one("div.product > a")
    site_cfg = {
        "selectors": {
            "product_card": "div.product > a",
            "name": ".product__title, .title, h2",
            "price": ".price__value",
            "brand": ".product__brand",
            "url": "a[href]",
            "image": "img",
            "availability": ".availability",
            "unit": ".price__unit",
        },
        "pagination": {"max_pages": 1},
        "throttle_seconds": 0
    }
    sc = SiteScraper("castorama", site_cfg, session=make_session())
    item = sc.parse_card("https://www.castorama.fr/", card, "tiles")
    assert isinstance(item, MaterialItem)
    assert item.name.startswith("Carrelage")
    assert item.brand == "Ecoceramic"
    assert item.price.currency == "€"
    assert item.url.startswith("https://")
