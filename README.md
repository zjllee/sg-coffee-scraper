# sg-coffee-scraper

Scrapes specialty coffee bean listings from 40+ Singapore roasters and generates browsable reports.

Two scrapers are available:

| Script | Extraction method | API key needed? | Speed | Accuracy |
|--------|------------------|-----------------|-------|----------|
| `scrape.py` | Regex/heuristics | No | Fast (~30s, async) | Good for Shopify sites |
| `coffee_agent.py` | LLM-powered (multiple providers) | Depends on provider | Varies | Best overall |

`coffee_agent.py` supports three LLM backends:

| Provider | Cost | Speed | Setup |
|----------|------|-------|-------|
| `anthropic` (default) | ~$3-5/run | ~10 min | `ANTHROPIC_API_KEY` in .env |
| `gemini` | Free (15 RPM) | ~3 min | `GOOGLE_GEMINI_API_KEY` in .env ([get key](https://aistudio.google.com/apikey)) |
| `ollama` | Free (local) | Varies | Install [Ollama](https://ollama.com), pull a model, run `ollama serve` |

## What it extracts

- Coffee name, roaster, origin, process, roast level
- Tasting notes
- Price, weight, price per 100g

## Setup

```bash
pip install -r requirements.txt
```

Requires Python 3.10+.

For `coffee_agent.py`, create a `.env` file:

```bash
cp .env.example .env
# edit .env and add your API key(s)
```

Set `LLM_PROVIDER` in `.env` to choose your default provider, or use the `--provider` flag at runtime.

## Usage

### Option 1: Regex scraper (no API key)

```bash
python scrape.py
```

Outputs `coffees.json`, `coffees.md`, and `index.html`.

### Option 2: LLM-powered scraper (better extraction)

```bash
# Default provider (Anthropic Claude)
python coffee_agent.py

# Use Google Gemini (free tier)
python coffee_agent.py --provider gemini

# Use a local model via Ollama
python coffee_agent.py --provider ollama
```

Outputs `roaster_data.json`, `coffee_report.html`, and `index.html`.

Uses an LLM to extract coffee data from scraped page content. Produces richer tasting notes and more accurate field extraction, especially for non-Shopify sites. Pre-filters non-coffee products (equipment, merchandise, tea, etc.) before sending to the LLM to reduce cost and avoid truncation.

## Output files

| File | Source | Description |
|------|--------|-------------|
| `coffees.json` | `scrape.py` | Flat list of all coffees with roaster metadata |
| `coffees.md` | `scrape.py` | Markdown tables grouped by roaster |
| `index.html` | `coffee_agent.py` | Interactive HTML report with search, filters, and archive picker |
| `roaster_data.json` | `coffee_agent.py` | Coffees grouped by roaster, with summaries and error logging |
| `coffee_report.html` | `coffee_agent.py` | Same as `index.html` |
| `archives/` | `coffee_agent.py` | Archived previous runs (git-ignored) |

## Roasters

The full list of 43 roasters and their URLs is in `sg_roasters.md`. To add a roaster, add an entry to `sg_roasters.md` and the `BOOKMARKS` list in both `scrape.py` and `coffee_agent.py`.

## Archives

Each run of `coffee_agent.py` automatically archives the previous `roaster_data.json` to `archives/`. The HTML report includes an archive picker to browse previous runs.

To browse archives, serve the project directory (needed for CORS):

```bash
python -m http.server 8000
# Then open http://localhost:8000
```

## Documentation

See [DOCS.md](DOCS.md) for detailed documentation of the project architecture, functions, and data formats.
