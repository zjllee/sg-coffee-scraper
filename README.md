# sg-coffee-scraper

Scrapes specialty coffee bean listings from 40+ Singapore roasters and generates browsable reports.

Two scrapers are available:

| Script | Extraction method | API key needed? |
|--------|------------------|-----------------|
| `scrape.py` | Regex/heuristics (fast, free) | No |
| `coffee_agent.py` | Claude API (more accurate) | Yes |

## What it extracts

- Coffee name, roaster, origin, process, roast level
- Tasting notes
- Price, weight, price per 100g

## Setup

```bash
pip install -r requirements.txt
```

Requires Python 3.10+.

For `coffee_agent.py`, create a `.env` file with your Anthropic API key:

```bash
cp .env.example .env
# edit .env and add your key
```

## Usage

### Option 1: Regex scraper (no API key)

```bash
python scrape.py
```

Outputs `coffees.json`, `coffees.md`, and `index.html`.

### Option 2: Claude API scraper (better extraction)

```bash
python coffee_agent.py
```

Outputs `roaster_data.json` and `coffee_report.html`.

Uses Claude Sonnet to extract coffee data from scraped page content. Produces richer tasting notes and more accurate field extraction, especially for non-Shopify sites.

## Output

- `coffees.json` — all coffees in structured JSON (from `scrape.py`)
- `coffees.md` — readable markdown with tables per roaster
- `index.html` — static HTML page with origin/roast filters and text search
- `roaster_data.json` — all coffees in structured JSON (from `coffee_agent.py`)
- `coffee_report.html` — HTML report with tables per roaster, highlights best value

## Roasters

The full list of roasters and their URLs is in `sg_roasters.md`. To add a roaster, add an entry to `sg_roasters.md` and the `BOOKMARKS` list in both `scrape.py` and `coffee_agent.py`.
