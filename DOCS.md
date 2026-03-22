# Documentation

Detailed reference for the sg-coffee-scraper project.

## Project structure

```
sg-coffee-scraper/
  scrape.py             # Regex-based scraper (no API key needed)
  coffee_agent.py       # Claude API scraper (requires ANTHROPIC_API_KEY)
  sg_roasters.md        # Master list of roaster bookmarks
  requirements.txt      # Python dependencies
  .env.example          # Template for API key config
  .gitignore            # Ignores .env, __pycache__, .venv
  README.md             # Quick-start guide
  DOCS.md               # This file
  coffees.json          # Output: flat coffee list (scrape.py)
  coffees.md            # Output: markdown tables (scrape.py)
  index.html            # Output: interactive HTML catalog (scrape.py)
  roaster_data.json     # Output: grouped coffee data (coffee_agent.py)
  coffee_report.html    # Output: HTML report (coffee_agent.py)
```

---

## scrape.py

Async scraper using `httpx` and `BeautifulSoup`. Extracts coffee data using regex heuristics — no API key needed.

### How it works

1. For each roaster, tries the Shopify `/products.json` endpoint first (most SG roasters use Shopify).
2. Falls back to HTML scraping with pagination (`?page=2`, `?page=3`, etc.) for non-Shopify sites.
3. Extracts fields using regex pattern matching.
4. Outputs `coffees.json`, generates `index.html` and `coffees.md`.

### Constants

| Constant | Value | Description |
|----------|-------|-------------|
| `TOTAL_LIMIT` | 500,000 | Max total scraped text chars across all roasters |
| `TIMEOUT` | 20 | HTTP request timeout in seconds |
| `HEADERS` | Browser UA | User-Agent and Accept headers to avoid blocks |

### Functions

#### Web fetching

| Function | Description |
|----------|-------------|
| `get_base_url(url)` | Extracts `scheme://host` from a full URL |
| `try_shopify_json(client, base_url)` | Fetches all products via Shopify's `/products.json?limit=250&page=N`. Returns list of product dicts, or `None` if not a Shopify site. Paginates up to 10 pages. |
| `fetch_pages(client, start_url, max_pages=5)` | HTML fallback. Fetches the start URL and probes `?page=2..5`. Stops early if a page is empty or identical to the previous. Returns concatenated text. |

#### Extraction (regex-based)

| Function | Description |
|----------|-------------|
| `extract_shopify_coffees(products, roaster_name)` | Filters Shopify product JSON to coffee-only items using keyword matching. Extracts name, price, weight from the first variant, then uses regex helpers for origin/process/notes. |
| `extract_coffees_from_html(html_text, roaster_name, url)` | Fallback extractor for non-Shopify HTML. Scans for lines containing price patterns (`$XX.XX`) and extracts what it can. Less accurate. |
| `parse_price(text)` | Regex for `$XX.XX` patterns. Returns formatted price string or `None`. |
| `parse_weight(text)` | Regex for weight patterns like `200g`, `1kg`. Returns normalized string or `None`. |
| `compute_price_per_100g(price, weight)` | Calculates price per 100g from price and weight strings. Handles g, kg, oz, lb. Returns `$X.XX` or `None`. |
| `guess_origin(text)` | Matches against a list of ~40 coffee-producing countries/regions. Returns first match or `"Blend"` if blend keyword found. |
| `guess_process(text)` | Matches against common processing methods (natural, washed, honey, anaerobic, etc.). Ordered longest-first to prefer "natural anaerobic" over "natural". |
| `guess_roast_level(text)` | Matches compound levels first (light-medium), then simple levels (light, medium, dark, espresso, filter, omni). |
| `extract_tasting_notes(text)` | Regex for patterns like "Tasting notes: X, Y, Z". Cuts off at common stop words (Roast Profile, Region, etc.) to avoid capturing non-note text. |

#### Orchestration

| Function | Description |
|----------|-------------|
| `scrape_roaster(client, bookmark, semaphore)` | Scrapes one roaster: tries Shopify JSON, falls back to HTML. Returns a dict with roaster name, URL, coffees list, method used, and timestamp. |
| `main()` | Runs all roasters concurrently (semaphore limits to 5 at a time). Collects results, saves `coffees.json`, generates `index.html`. |
| `generate_html(data)` | Builds a static HTML page with CSS-styled cards, stats bar, and JS-powered search/filter by origin and roast level. |

---

## coffee_agent.py

Synchronous scraper that uses the Claude API (Sonnet) for extraction. More accurate than regex, especially for tasting notes and non-Shopify sites.

### How it works

1. For each roaster, tries Shopify `/products.json` first.
2. Pre-filters products to remove non-coffee items (merchandise, tea, equipment, etc.) before sending to Claude.
3. Caps at 30 products and 30K chars to stay within Claude's output token budget.
4. Falls back to HTML scraping with pagination for non-Shopify sites.
5. Sends the scraped text to Claude Sonnet with a structured extraction prompt.
6. Claude returns JSON with coffees array and a one-sentence summary.
7. Outputs `roaster_data.json` and generates `coffee_report.html`.

### Constants

| Constant | Value | Description |
|----------|-------|-------------|
| `TIMEOUT` | 20 | HTTP request timeout in seconds |
| `PAGE_CHAR_LIMIT` | 15,000 | Max chars per HTML page sent to Claude |
| `TOTAL_CHAR_LIMIT` | 50,000 | Max total chars per roaster (HTML fallback) |
| `CLAUDE_MODEL` | `claude-sonnet-4-20250514` | Model used for extraction |
| `EXTRACTION_PROMPT` | (see source) | System prompt instructing Claude to return structured JSON |

### Functions

#### Web fetching

| Function | Description |
|----------|-------------|
| `get_base_url(url)` | Extracts `scheme://host` from a full URL. |
| `fetch_page(url, session)` | Fetches a single URL, strips scripts/styles, returns cleaned text. Returns `None` on any HTTP error. |
| `fetch_shopify_json(base_url, session)` | Fetches Shopify `/products.json`, pre-filters with `_is_likely_coffee()`, caps at 30 products, formats as text via `_format_shopify_products()`. Returns `None` if not Shopify. |
| `_is_likely_coffee(product)` | Pre-filter for Shopify products. Rejects known non-coffee product types (merchandise, tea, wine, pastry, equipment, etc.) and title keywords (grinder, mug, tote, etc.). Keeps items that mention coffee beans even if they match a skip keyword. |
| `_format_shopify_products(products)` | Converts Shopify product dicts into a plain-text format suitable for Claude. Includes title, type, tags, description (truncated to 300 chars), and all variant prices/weights. |
| `scrape_roaster_pages(url, session)` | Main fetch function. Tries Shopify JSON first (capped at 30K chars), falls back to HTML with pagination (up to 5 pages). Returns `(text, pages_fetched)`. |

#### Claude API extraction

| Function | Description |
|----------|-------------|
| `extract_coffees_with_claude(client, roaster_name, scraped_text)` | Sends scraped text + extraction prompt to Claude Sonnet. Parses the JSON response. Returns `(coffees_list, summary, error)`. Handles JSON parse errors and API errors gracefully, returning the specific error string. |

The extraction prompt instructs Claude to:
- Extract only coffee beans (ignore equipment, merch, accessories)
- Create one entry per size variant (e.g. 200g and 1kg = 2 entries)
- Calculate `price_per_100g` when price and weight are available
- Return raw JSON with no markdown fences

#### HTML report generation

| Function | Description |
|----------|-------------|
| `generate_report(data)` | Builds `coffee_report.html` with per-roaster tables, stats summary, best-value highlighting (lowest price/100g), search bar, and error display for failed roasters. |
| `_esc(s)` | HTML-escapes a string (`&`, `<`, `>`, `"`). |

#### Orchestration

| Function | Description |
|----------|-------------|
| `main()` | Iterates through all roasters sequentially. For each: scrapes pages, sends to Claude, collects results. Prints progress to console. Saves `roaster_data.json`, generates `coffee_report.html`, prints summary with failure list. |

### Error handling

Errors are captured at multiple levels and stored in `roaster_data.json`:

| Error type | Stored as | Example |
|------------|-----------|---------|
| HTTP fetch failure | `"No content could be fetched from the site."` | SSL cert error, timeout, 403 |
| Claude JSON parse error | `"JSON parse error: Unterminated string..."` | Response truncated at token limit |
| Claude API error | `"Claude API error: ..."` | Rate limit, auth failure |
| No products found | `"No coffees found on page."` | Empty/JS-rendered page |

### Cost estimate

Claude Sonnet pricing: $3/M input tokens, $15/M output tokens.

| Scenario | Input tokens | Output tokens | Estimated cost |
|----------|-------------|---------------|----------------|
| Single roaster (small) | ~3K | ~1K | ~$0.02 |
| Single roaster (large) | ~15K | ~4K | ~$0.11 |
| Full run (43 roasters) | ~300K | ~130K | ~$3-5 |

---

## Data formats

### coffees.json (from scrape.py)

```json
{
  "coffees": [
    {
      "name": "Ethiopia Yirgacheffe",
      "roaster": "Nylon Coffee Roasters",
      "origin": "Ethiopia",
      "process": "Washed",
      "tasting_notes": "Blueberry, jasmine, lemon",
      "price": "$28.00",
      "weight": "200g",
      "price_per_100g": "$14.00",
      "roast_level": "Light"
    }
  ],
  "summary": "Found 1557 coffees from 43 roasters...",
  "last_updated": "2026-03-22 10:00 UTC",
  "roasters": [
    { "name": "...", "url": "...", "coffee_count": 17, "method": "shopify_json" }
  ],
  "errors": []
}
```

### roaster_data.json (from coffee_agent.py)

```json
{
  "scraped_at": "2026-03-22T10:00:00",
  "roasters": [
    {
      "name": "Nylon Coffee Roasters",
      "url": "https://nylon.coffee/collections/coffee",
      "coffees": [
        {
          "name": "Ethiopia Yirgacheffe",
          "origin": "Ethiopia",
          "process": "Washed",
          "tasting_notes": "Blueberry, jasmine, lemon",
          "roast_level": "Light",
          "price": "$28",
          "weight": "200g",
          "price_per_100g": "$14.00"
        }
      ],
      "summary": "Nylon offers single-origin coffees from...",
      "error": null
    }
  ]
}
```

### Key differences between outputs

| | `coffees.json` | `roaster_data.json` |
|--|----------------|---------------------|
| Structure | Flat list of all coffees | Grouped by roaster |
| `roaster` field | On each coffee | Parent object |
| Summary | One global summary | Per-roaster summaries |
| Error tracking | Global errors list | Per-roaster error field |
| Extraction method | Regex heuristics | Claude API |

---

## Adding a new roaster

1. Add the entry to `sg_roasters.md`
2. Add to `BOOKMARKS` in both `scrape.py` and `coffee_agent.py`
3. The URL should point to the roaster's coffee/beans collection page
4. Shopify stores work best (auto-detected via `/products.json`)
5. Non-Shopify stores rely on HTML text extraction — results vary depending on how the site renders products
