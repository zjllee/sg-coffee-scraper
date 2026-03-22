# sg-coffee-scraper

Scrapes specialty coffee bean listings from 40+ Singapore roasters and generates browsable reports.

Two scrapers are available:

| Script | Extraction method | API key needed? | Speed | Accuracy |
|--------|------------------|-----------------|-------|----------|
| `scrape.py` | Regex/heuristics | No | Fast (~30s, async) | Good for Shopify sites |
| `coffee_agent.py` | Claude API (Sonnet) | Yes (~$3-5/run) | Slower (~10min, sequential) | Best overall |

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

Uses Claude Sonnet to extract coffee data from scraped page content. Produces richer tasting notes and more accurate field extraction, especially for non-Shopify sites. Pre-filters non-coffee products (equipment, merchandise, tea, etc.) before sending to the API to reduce cost and avoid truncation.

## Output files

| File | Source | Description |
|------|--------|-------------|
| `coffees.json` | `scrape.py` | Flat list of all coffees with roaster metadata |
| `coffees.md` | `scrape.py` | Markdown tables grouped by roaster |
| `index.html` | `scrape.py` | Interactive HTML catalog with search and origin/roast filters |
| `roaster_data.json` | `coffee_agent.py` | Coffees grouped by roaster, with summaries and error logging |
| `coffee_report.html` | `coffee_agent.py` | HTML report with per-roaster tables and best-value highlighting |

## Roasters

The full list of 43 roasters and their URLs is in `sg_roasters.md`. To add a roaster, add an entry to `sg_roasters.md` and the `BOOKMARKS` list in both `scrape.py` and `coffee_agent.py`.

## Documentation

See [DOCS.md](DOCS.md) for detailed documentation of the project architecture, functions, and data formats.
