# sg-coffee-scraper

Scrapes specialty coffee bean listings from 40+ Singapore roasters and generates a browsable HTML catalog.

Most roasters use Shopify, so the scraper pulls structured data via `/products.json`. Non-Shopify sites fall back to HTML scraping.

## What it extracts

- Coffee name, roaster, origin, process, roast level
- Tasting notes
- Price, weight, price per 100g

## Setup

```bash
pip install -r requirements.txt
```

Requires Python 3.10+. Dependencies: `httpx`, `beautifulsoup4`, `lxml`.

## Usage

```bash
python scrape.py
```

This will:
1. Scrape all roasters listed in `sg_roasters.md`
2. Save structured data to `coffees.json`
3. Generate `index.html` with search and filtering
4. Generate `coffees.md` with readable tables

Open `index.html` in a browser to browse the catalog.

## Output

- `coffees.json` — all coffees in structured JSON
- `coffees.md` — readable markdown with tables per roaster
- `index.html` — static HTML page with origin/roast filters and text search

## Roasters

The full list of roasters and their URLs is in `sg_roasters.md`. To add a roaster, add an entry to both `sg_roasters.md` and the `BOOKMARKS` list in `scrape.py`.
