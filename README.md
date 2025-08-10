# Donizo – Material Price Scraper

Scrapes **Leroy Merlin** (Playwright), **Castorama** (requests), and **ManoMano** (Playwright) across multiple categories (tiles, sinks, toilets, paint, vanities, showers).  
Handles pagination, anti-bot (browser fallback), product fields, and outputs JSON ready for Donizo’s pricing engine. Includes tests and optional API and vector-ready export.

---

## Project structure
/donizo-material-scraper/
├── scraper.py
├── config/
│   └── scraper_config.yaml
├── data/
│   └── materials.json
├── tests/
│   └── test_scraper.py
└── README.md


---

## Install (local or Codespaces)
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium

Run scrapers

# All sites → one file
python scraper.py --site all --limit-per-category 200 --out data/materials.json

# Individual sites
python scraper.py --site castorama   --limit-per-category 200 --out data/materials_castorama.json
python scraper.py --site manomano    --limit-per-category 200 --out data/materials_manomano.json
python scraper.py --site leroymerlin --limit-per-category 150 --out data/materials_leroymerlin.json

Output format (JSON array):

{
    "id": "cdc8aa5ac57a86e2",
    "site": "castorama",
    "category": "tiles",
    "name": "PromotionCarrelage sol et mur aspect bois naturel 20 x 120 cm Rustic Wood ColoursNote avis produits: 5 étoiles sur 5 sur 7 avis produits(7)Prix d’origine34,95 €/ M234,95 €/ M229,71€/ M2Vous économisez5,24 €/ M2soit35,65 €/ cartonPrix valable jusqu'au 01/09/2025",
    "brand": null,
    "price": {
      "value": 34.95,
      "currency": "€",
      "raw": "34,95 €"
    },
    "unit": null,
    "url": "https://www.castorama.fr/carrelage-sol-et-mur-aspect-bois-naturel-20-x-120-cm-rustic-wood-colours/5059340460307_CAFR.prd",
    "image_url": "https://media.castorama.fr/is/image/Castorama/carrelage-sol-et-mur-aspect-bois-naturel-20-x-120-cm-rustic-wood-colours~5059340460307_32i?$MOB_PREV$&$width=96&$height=96",
    "availability": null,
    "scraped_at": "2025-08-10T06:41:59.228683+00:00"
  },
  {
    "id": "d7f3e0085ba650df",
    "site": "castorama",
    "category": "tiles",
    "name": "PromotionCarrelage sol et mur District gris clair 60x60cm EcoceramicPrix d’origine23,95 €/ M223,95 €/ M219,95€/ M2Vous économisez4 €/ M2soit21,55 €/ CartonPrix valable jusqu'au 01/09/2025",
    "brand": null,
    "price": {
      "value": 23.95,
      "currency": "€",
      "raw": "23,95 €"
    },
    "unit": null,
    "url": "https://www.castorama.fr/carrelage-sol-et-mur-district-gris-clair-60x60cm-ecoceramic/8429991979072_CAFR.prd",
    "image_url": "https://media.castorama.fr/is/image/Castorama/carrelage-sol-et-mur-district-gris-clair-60x60cm-ecoceramic~8429991979072_01i_FR_CF?$MOB_PREV$&$width=96&$height=96",
    "availability": null,
    "scraped_at": "2025-08-10T06:41:59.233006+00:00"
  }

Tests
pytest -q

Vector-ready export (bonus)
Create data/materials.jsonl with {id, text, meta} lines suitable for any vector DB:

python scripts/make_jsonl.py
API (bonus)
Start a review API with TF-IDF search:
uvicorn api:app --reload --port 8000
CI – Monthly auto-scrape (bonus)
This repo includes .github/workflows/monthly.yml:

Runs monthly at 03:00 UTC

Installs deps + Chromium

Scrapes all sites → data/materials.json

Saves timestamped snapshot in data/snaps/

Uploads artifacts + commits changes

Assumptions & notes
Anti-bot/JS: LM & ManoMano render via Playwright to bypass 403/JS; Castorama uses requests.

Pagination: ?page=N by config; scraper retries base URL when page 1 listing is unpaged.

Variations: current version is listing-level. For SKU variations, extend to product detail pages per site.

Versioning: all rows have scraped_at (UTC ISO-8601). Snapshots can be diffed and versioned.


