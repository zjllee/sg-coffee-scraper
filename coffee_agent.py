#!/usr/bin/env python3
"""
Scrape Singapore coffee roaster websites and extract bean offerings using Claude API.

1. Fetch each roaster's collection page (+ pagination).
2. For Shopify sites, also try /products.json for richer data.
3. Pass scraped text to Claude API to extract structured coffee data.
4. Save results to roaster_data.json and generate coffee_report.html.
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import anthropic
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

BOOKMARKS = [
    {"name": "20grams Coffee Roastery", "url": "https://20gramscoffeeroastery.com/collections/all"},
    {"name": "Alchemist", "url": "https://alchemist.global/collections/all"},
    {"name": "Autumn Brews", "url": "https://autumnbrews.coffee/shop-all/"},
    {"name": "Cata Coffee", "url": "https://catacoffee.com/collections/coffee-beans"},
    {"name": "Compound Coffee Co.", "url": "https://www.compoundcoffee.com/shop-3?Category=ESPRESSO"},
    {"name": "Dutch Colony Coffee Co.", "url": "https://www.dutchcolony.sg/collections/coffee-2"},
    {"name": "Five Oars Coffee Roasters", "url": "https://www.focr.sg/shop/coffeebeans"},
    {"name": "Flip Coffee Roasters", "url": "https://flipcoffeeroasters.com/collections/beans"},
    {"name": "Fluid", "url": "https://fluidcollective.co/collections/all"},
    {"name": "Generation Coffee", "url": "https://www.generationcoffee.sg/collections/coffee-beans"},
    {"name": "Glyph Supply Co", "url": "https://www.glyphsupply.co/coffee"},
    {"name": "Homeground", "url": "https://homegroundcoffeeroasters.com/collections/coffees"},
    {"name": "Kyuukei Coffee", "url": "https://kyuukeicoffee.com/collections/all"},
    {"name": "LazyBean", "url": "https://lazybean.sg/collections/frontpage"},
    {"name": "Little Big Coffee Roasters", "url": "https://littlebigcoffee.com/collections/bundle"},
    {"name": "luli roasts.", "url": "https://luliroasts.com/collections/coffee"},
    {"name": "Maxi Coffee Bar", "url": "https://maxicoffeebar.com/shop"},
    {"name": "Narrative Coffee Stand", "url": "https://narrativecoffeestand.com/collections/coffee-beans"},
    {"name": "Nylon Coffee Roasters", "url": "https://nylon.coffee/collections/coffee"},
    {"name": "Bearded Bella", "url": "https://beardedbella.com/collections/coffee-store"},
    {"name": "Paradise Coffee Roasters", "url": "https://paradisecoffeeroasters.sg/collections/all"},
    {"name": "Parchmen & Co", "url": "https://www.parchmen.co/collections/roasted-coffee-beans"},
    {"name": "Percolate Coffee & Goods", "url": "https://www.percolate.sg/shop"},
    {"name": "PPP Coffee", "url": "https://pppcoffee.com/collections/beans"},
    {"name": "Prodigal Roasters", "url": "https://prodigalroasters.com/collections/all"},
    {"name": "Roundboy", "url": "https://roundboyroasters.com/collections/coffee-beans"},
    {"name": "Small Waves Coffee Roasters", "url": "https://smallwaves.coffee/collections/coffee"},
    {"name": "Smitten Coffee Roasters", "url": "https://www.smittencoffee.com/shop/coffee"},
    {"name": "State Of Affairs", "url": "https://www.stateofaffairs.sg/coffee/"},
    {"name": "Tad Coffee", "url": "https://tadcoffee.com/shop/"},
    {"name": "The Community Coffee", "url": "https://thecommunitycoffee.com/collections/coffee-beans"},
    {"name": "Tiong Hoe", "url": "https://tionghoe.com/collections/roasted-beans"},
    {"name": "Zerah Coffee Roasters", "url": "https://zerahcoffeeroasters.com/"},
    {"name": "Cumulo Coffee", "url": "https://www.cumulocoffee.com/"},
    {"name": "Common Man Coffee Roasters", "url": "https://commonmancoffeeroasters.com/collections/all-coffee-blends"},
    {"name": "Bettr Coffee", "url": "https://bettr.coffee/collections/coffee-beans"},
    {"name": "Tanamera Coffee & Roastery", "url": "https://www.tanameracoffee.com.sg/collections/beans-single-origin"},
    {"name": "Foreword Coffee", "url": "https://forewordcoffee.com/product-category/coffee-beans/"},
    {"name": "Fortune Coffee Club", "url": "https://fortunecoffee.club/collections/coffee-1"},
    {"name": "Quarter Life Coffee", "url": "https://quarterlifecoffee.com/collections/all"},
    {"name": "Agora Coffee", "url": "https://agoracoffeecs.com/shop"},
    {"name": "Fables Specialty Coffee", "url": "https://fablescoffee.com/collections/coffee"},
    {"name": "Brawn & Brains Coffee", "url": "https://www.brawnandbrains.sg/pages/collections-coffee"},
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

TIMEOUT = 20
PAGE_CHAR_LIMIT = 15_000  # per-page text cap sent to Claude
TOTAL_CHAR_LIMIT = 50_000  # total text cap per roaster sent to Claude

CLAUDE_MODEL = "claude-sonnet-4-20250514"

EXTRACTION_PROMPT = """You are extracting coffee bean product listings from a roaster's website content.

RULES:
- Extract ONLY coffee beans / roasted coffee. Ignore equipment, merchandise, accessories, gift cards, subscriptions, brew gear.
- If a product lists multiple sizes/prices (e.g. 200g and 1kg), create one entry per size.
- Calculate price_per_100g from price and weight if both are present: (price / weight_in_grams) * 100, formatted as "$X.XX". Otherwise null.
- All fields except "name" can be null if not found on the page.
- Return raw JSON only. No markdown fences, no explanation, no extra text.

Return a JSON object with this exact shape:
{
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
  "summary": "One sentence about what this roaster offers or what stands out."
}

Here is the website content to extract from:

"""


# ---------- Web fetching ----------

def get_base_url(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def fetch_page(url: str, session: requests.Session) -> str | None:
    """Fetch a single page and return cleaned text, or None on failure."""
    try:
        resp = session.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
            tag.decompose()
        return soup.get_text(" ", strip=True)
    except requests.RequestException as e:
        print(f"    Error fetching {url}: {e}")
        return None


def _is_likely_coffee(product: dict) -> bool:
    """Pre-filter: return True if a Shopify product is likely coffee beans."""
    title = product.get("title", "").lower()
    ptype = (product.get("product_type") or "").lower()
    tags = product.get("tags", [])
    tags_str = " ".join(tags).lower() if isinstance(tags, list) else str(tags).lower()
    combined = f"{title} {ptype} {tags_str}"

    # Definite non-coffee product types
    skip_types = {
        "merchandise", "accessories", "tea", "teapot", "teaware", "tea blend",
        "pastry", "bakery", "bakes", "wines", "wine", "gift cards",
        "education", "service", "birthday candles", "tote bag",
        "coffee maker", "coffee grinder", "coffee lab tools",
        "brewing equipment", "home brewer's accessories", "filter paper",
        "drinking vessel", "composite",
    }
    if ptype in skip_types:
        return False

    # Skip by keywords in title
    skip_kw = [
        "grinder", "brewer", "mug", "cup", "tumbler", "filter paper",
        "dripper", "kettle", "scale", "gift card", "tote", "shirt",
        "cap", "hat", "sticker", "poster", "candle", "wine", "tea ",
        "teapot", "pastry", "cake", "cookie", "merch",
    ]
    if any(kw in combined for kw in skip_kw):
        # Unless it also clearly mentions coffee beans
        if not any(kw in combined for kw in ["coffee bean", "roast", "single origin", "espresso blend"]):
            return False

    return True


def fetch_shopify_json(base_url: str, session: requests.Session) -> str | None:
    """Try Shopify /products.json and return a text summary of products."""
    products = []
    for page in range(1, 6):
        url = f"{base_url}/products.json?limit=250&page={page}"
        try:
            resp = session.get(url, headers=HEADERS, timeout=TIMEOUT)
            if resp.status_code != 200:
                return None if page == 1 else _format_shopify_products(products)
            data = resp.json()
            batch = data.get("products", [])
            if not batch:
                break
            products.extend(batch)
        except Exception:
            return None if page == 1 else _format_shopify_products(products)

    # Pre-filter to likely coffee products before sending to Claude
    filtered = [p for p in products if _is_likely_coffee(p)]
    if products and not filtered:
        # If filtering removed everything, send all (let Claude decide)
        filtered = products
    elif products:
        print(f"    Pre-filtered: {len(products)} -> {len(filtered)} likely coffee products")

    # Cap at 30 products to keep Claude input manageable
    if len(filtered) > 30:
        print(f"    Capped from {len(filtered)} to 30 products")
        filtered = filtered[:30]

    return _format_shopify_products(filtered) if filtered else None


def _format_shopify_products(products: list[dict]) -> str:
    """Convert Shopify product JSON into a text summary suitable for Claude."""
    lines = []
    for p in products:
        title = p.get("title", "")
        product_type = p.get("product_type", "")
        tags = ", ".join(p.get("tags", [])) if isinstance(p.get("tags"), list) else str(p.get("tags", ""))
        body = p.get("body_html", "") or ""
        body_text = BeautifulSoup(body, "lxml").get_text(" ", strip=True) if body else ""
        # Truncate long descriptions
        if len(body_text) > 300:
            body_text = body_text[:300] + "..."

        variants = p.get("variants", [])
        variant_lines = []
        for v in variants:
            vt = v.get("title", "")
            price = v.get("price", "")
            grams = v.get("grams", 0)
            weight_str = f"{grams}g" if grams else ""
            variant_lines.append(f"  Variant: {vt} | Price: ${price} | Weight: {weight_str}")

        lines.append(
            f"PRODUCT: {title}\n"
            f"  Type: {product_type}\n"
            f"  Tags: {tags}\n"
            f"  Description: {body_text}\n"
            + "\n".join(variant_lines)
        )
    return "\n\n".join(lines)


def scrape_roaster_pages(url: str, session: requests.Session) -> tuple[str, int]:
    """
    Fetch a roaster's collection pages with pagination.
    Returns (combined_text, pages_fetched).
    """
    base_url = get_base_url(url)

    # Try Shopify JSON first — much richer data
    shopify_text = fetch_shopify_json(base_url, session)
    if shopify_text:
        # Trim to limit — keep under 30K to avoid Claude output truncation
        char_limit = min(TOTAL_CHAR_LIMIT, 30_000)
        if len(shopify_text) > char_limit:
            shopify_text = shopify_text[:char_limit] + "\n... (truncated)"
        return shopify_text, 1

    # Fallback: HTML scraping with pagination
    all_text = []
    total_len = 0
    pages_fetched = 0
    prev_text = None

    for page_num in range(1, 6):
        if page_num == 1:
            page_url = url
        else:
            sep = "&" if "?" in url else "?"
            page_url = f"{url}{sep}page={page_num}"

        text = fetch_page(page_url, session)
        if text is None:
            break

        # Stop if page is empty or identical to previous
        if len(text.strip()) < 100:
            break
        if prev_text and text.strip() == prev_text.strip():
            break

        # Cap per page
        trimmed = text[:PAGE_CHAR_LIMIT]
        header = f"--- PAGE {page_num}: {page_url} ---\n"
        all_text.append(header + trimmed)
        total_len += len(header) + len(trimmed)
        pages_fetched += 1
        prev_text = text

        if total_len >= TOTAL_CHAR_LIMIT:
            break

    return "\n\n".join(all_text), pages_fetched


# ---------- Claude API extraction ----------

def extract_coffees_with_claude(
    client: anthropic.Anthropic,
    roaster_name: str,
    scraped_text: str,
) -> tuple[list[dict], str | None, str | None]:
    """
    Send scraped text to Claude for coffee extraction.
    Returns (coffees_list, summary_string, error_string).
    """
    if not scraped_text or len(scraped_text.strip()) < 50:
        return [], None, "Input text too short for extraction."

    user_content = EXTRACTION_PROMPT + f"Roaster: {roaster_name}\n\n{scraped_text}"

    try:
        message = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=8192,
            messages=[{"role": "user", "content": user_content}],
        )
        raw = message.content[0].text.strip()

        # Strip markdown fences if Claude added them despite instructions
        if raw.startswith("```"):
            raw = re.sub(r'^```(?:json)?\s*', '', raw)
            raw = re.sub(r'\s*```$', '', raw)

        data = json.loads(raw)
        coffees = data.get("coffees", [])
        summary = data.get("summary")
        return coffees, summary, None

    except json.JSONDecodeError as e:
        err = f"JSON parse error: {e}"
        print(f"    {err}")
        return [], None, err
    except anthropic.APIError as e:
        err = f"Claude API error: {e}"
        print(f"    {err}")
        return [], None, err


# ---------- HTML report generation ----------

def generate_report(data: dict):
    """Generate coffee_report.html from roaster data."""
    roasters = data.get("roasters", [])
    scraped_at = data.get("scraped_at", "")

    # Find best value (lowest price_per_100g)
    best_value = None
    best_value_price = float("inf")
    for r in roasters:
        for c in r.get("coffees", []):
            p100 = c.get("price_per_100g")
            if p100:
                try:
                    val = float(re.search(r'[\d.]+', p100).group())
                    if val > 0 and val < best_value_price:
                        best_value_price = val
                        best_value = (r["name"], c["name"], p100)
                except (ValueError, AttributeError):
                    pass

    total_coffees = sum(len(r.get("coffees", [])) for r in roasters)
    roasters_with_coffees = sum(1 for r in roasters if r.get("coffees"))

    # Build roaster sections
    roaster_html_parts = []
    for r in sorted(roasters, key=lambda x: x["name"]):
        coffees = r.get("coffees", [])
        error = r.get("error")
        name = r["name"]
        url = r["url"]

        if error and not coffees:
            roaster_html_parts.append(f"""
            <div class="roaster-card">
                <div class="roaster-header">
                    <h2>{_esc(name)}</h2>
                    <a href="{_esc(url)}" target="_blank">Visit Shop</a>
                </div>
                <p class="error-msg">Error: {_esc(error)}</p>
            </div>""")
            continue

        if not coffees:
            continue

        rows = []
        for c in coffees:
            is_best = (
                best_value
                and best_value[0] == name
                and best_value[1] == c.get("name")
            )
            row_class = ' class="best-value"' if is_best else ""
            best_tag = ' <span class="best-tag">BEST VALUE</span>' if is_best else ""

            rows.append(f"""
                <tr{row_class}>
                    <td>{_esc(c.get('name', ''))}{best_tag}</td>
                    <td>{_esc(c.get('origin') or '-')}</td>
                    <td>{_esc(c.get('process') or '-')}</td>
                    <td>{_esc(c.get('roast_level') or '-')}</td>
                    <td class="notes">{_esc(c.get('tasting_notes') or '-')}</td>
                    <td>{_esc(c.get('price') or '-')}</td>
                    <td>{_esc(c.get('weight') or '-')}</td>
                    <td>{_esc(c.get('price_per_100g') or '-')}</td>
                </tr>""")

        summary_html = ""
        if r.get("summary"):
            summary_html = f'<p class="roaster-summary">{_esc(r["summary"])}</p>'

        roaster_html_parts.append(f"""
        <div class="roaster-card">
            <div class="roaster-header">
                <h2>{_esc(name)} <span class="count">({len(coffees)} coffees)</span></h2>
                <a href="{_esc(url)}" target="_blank">Visit Shop</a>
            </div>
            {summary_html}
            <div class="table-wrap">
            <table>
                <thead>
                    <tr>
                        <th>Name</th><th>Origin</th><th>Process</th><th>Roast</th>
                        <th>Tasting Notes</th><th>Price</th><th>Weight</th><th>Per 100g</th>
                    </tr>
                </thead>
                <tbody>{"".join(rows)}</tbody>
            </table>
            </div>
        </div>""")

    best_value_html = ""
    if best_value:
        best_value_html = f"""
        <div class="highlight-card">
            <div class="highlight-label">Best Value</div>
            <div class="highlight-name">{_esc(best_value[1])}</div>
            <div class="highlight-detail">{_esc(best_value[0])} &mdash; {_esc(best_value[2])}/100g</div>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Singapore Coffee Report</title>
<style>
  :root {{
    --bg: #0f1114; --surface: #1a1d23; --surface2: #22262e;
    --border: #2d3139; --text: #e4e4e7; --muted: #9ca3af;
    --accent: #c8a97e; --accent2: #a67c52; --green: #6ee7b7;
    --blue: #93c5fd; --red: #fca5a5; --gold: #fbbf24;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.6;
  }}
  .container {{ max-width: 1400px; margin: 0 auto; padding: 2rem 1rem; }}
  header {{
    text-align: center; padding: 3rem 1rem;
    border-bottom: 1px solid var(--border); margin-bottom: 2rem;
  }}
  header h1 {{ font-size: 2.5rem; color: var(--accent); margin-bottom: 0.5rem; }}
  header p {{ color: var(--muted); }}
  .stats {{
    display: flex; gap: 1rem; justify-content: center; flex-wrap: wrap; margin-bottom: 2rem;
  }}
  .stat {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
    padding: 1.25rem 2rem; text-align: center; }}
  .stat .num {{ font-size: 2rem; font-weight: 700; color: var(--accent); }}
  .stat .lbl {{ color: var(--muted); font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; }}
  .highlight-card {{
    background: linear-gradient(135deg, rgba(251,191,36,0.1), rgba(200,169,126,0.1));
    border: 1px solid var(--gold); border-radius: 12px;
    padding: 1.5rem; text-align: center; margin-bottom: 2rem;
  }}
  .highlight-label {{ color: var(--gold); font-size: 0.8rem; text-transform: uppercase;
    letter-spacing: 0.1em; font-weight: 600; }}
  .highlight-name {{ font-size: 1.3rem; font-weight: 700; margin: 0.25rem 0; }}
  .highlight-detail {{ color: var(--muted); }}
  .filter-bar {{
    background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
    padding: 1rem 1.25rem; margin-bottom: 2rem; display: flex; gap: 1rem; flex-wrap: wrap;
  }}
  .filter-bar input {{
    flex: 1; min-width: 200px; padding: 0.6rem 1rem; border-radius: 8px;
    border: 1px solid var(--border); background: var(--surface2); color: var(--text);
    font-size: 0.95rem; outline: none;
  }}
  .filter-bar input:focus {{ border-color: var(--accent); }}
  .roaster-card {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 12px; padding: 1.5rem; margin-bottom: 1.5rem;
  }}
  .roaster-header {{
    display: flex; justify-content: space-between; align-items: baseline;
    margin-bottom: 0.75rem;
  }}
  .roaster-header h2 {{ font-size: 1.3rem; }}
  .roaster-header a {{ color: var(--accent); text-decoration: none; font-size: 0.85rem; }}
  .roaster-header a:hover {{ text-decoration: underline; }}
  .count {{ color: var(--muted); font-weight: 400; font-size: 0.95rem; }}
  .roaster-summary {{ color: var(--muted); font-style: italic; margin-bottom: 0.75rem; font-size: 0.9rem; }}
  .error-msg {{ color: var(--red); font-size: 0.9rem; }}
  .table-wrap {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; }}
  th {{ text-align: left; padding: 0.6rem 0.75rem; border-bottom: 2px solid var(--border);
    color: var(--muted); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; }}
  td {{ padding: 0.5rem 0.75rem; border-bottom: 1px solid var(--border); vertical-align: top; }}
  tr:hover {{ background: var(--surface2); }}
  .best-value {{ background: rgba(251,191,36,0.06); }}
  .best-tag {{
    display: inline-block; background: var(--gold); color: #000; font-size: 0.65rem;
    padding: 0.1rem 0.4rem; border-radius: 4px; font-weight: 700; margin-left: 0.5rem;
    vertical-align: middle;
  }}
  .notes {{ max-width: 200px; font-style: italic; color: var(--muted); }}
  footer {{
    text-align: center; padding: 2rem; border-top: 1px solid var(--border);
    color: var(--muted); font-size: 0.85rem; margin-top: 2rem;
  }}
  @media (max-width: 768px) {{
    header h1 {{ font-size: 1.8rem; }}
    .stats {{ flex-direction: column; align-items: center; }}
    th, td {{ padding: 0.4rem 0.5rem; font-size: 0.8rem; }}
  }}
</style>
</head>
<body>
<header>
  <h1>Singapore Coffee Report</h1>
  <p>Extracted via Claude API from {len(roasters)} roasters</p>
  <p style="margin-top:0.3rem; font-size:0.85rem;">Scraped: {_esc(scraped_at)}</p>
</header>
<div class="container">
  <div class="stats">
    <div class="stat"><div class="num">{total_coffees}</div><div class="lbl">Coffees</div></div>
    <div class="stat"><div class="num">{roasters_with_coffees}</div><div class="lbl">Roasters</div></div>
    <div class="stat"><div class="num">{len(roasters)}</div><div class="lbl">Attempted</div></div>
  </div>
  {best_value_html}
  <div class="filter-bar">
    <input type="text" id="search" placeholder="Search coffees, roasters, origins..." oninput="filterCards()">
  </div>
  <div id="roasters">
    {"".join(roaster_html_parts)}
  </div>
</div>
<footer>
  <p>Generated by coffee_agent.py using Claude ({CLAUDE_MODEL})</p>
</footer>
<script>
function filterCards() {{
  const q = document.getElementById('search').value.toLowerCase();
  document.querySelectorAll('.roaster-card').forEach(card => {{
    card.style.display = card.textContent.toLowerCase().includes(q) ? '' : 'none';
  }});
}}
</script>
</body>
</html>"""

    out_path = Path(__file__).parent / "coffee_report.html"
    out_path.write_text(html, encoding="utf-8")


def _esc(s: str) -> str:
    """HTML-escape a string."""
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# ---------- Main ----------

def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set. Create a .env file with your key.")
        print("  cp .env.example .env  # then edit .env")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    session = requests.Session()

    print(f"Starting scrape of {len(BOOKMARKS)} roasters...\n")

    results = []
    total_coffees = 0
    failed = []

    for i, bm in enumerate(BOOKMARKS, 1):
        name = bm["name"]
        url = bm["url"]
        print(f"[{i}/{len(BOOKMARKS)}] {name}")

        # Scrape
        scraped_text, pages = scrape_roaster_pages(url, session)
        print(f"  Fetched {pages} page(s), {len(scraped_text)} chars")

        if not scraped_text or len(scraped_text.strip()) < 50:
            print(f"  No content retrieved, skipping Claude extraction")
            results.append({
                "name": name,
                "url": url,
                "coffees": [],
                "summary": None,
                "error": "No content could be fetched from the site.",
            })
            failed.append(name)
            continue

        # Extract via Claude
        coffees, summary, error = extract_coffees_with_claude(client, name, scraped_text)
        if not coffees and not error:
            error = "No coffees found on page."

        print(f"  Extracted {len(coffees)} coffees")
        if summary:
            print(f"  Summary: {summary}")

        results.append({
            "name": name,
            "url": url,
            "coffees": coffees,
            "summary": summary,
            "error": error,
        })
        total_coffees += len(coffees)

        if not coffees:
            failed.append(name)

        # Small delay to be polite to both sites and API
        time.sleep(0.5)

    # Build output
    output = {
        "scraped_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "roasters": results,
    }

    # Save JSON
    out_path = Path(__file__).parent / "roaster_data.json"
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved to {out_path}")

    # Generate HTML report
    generate_report(output)
    print(f"Generated coffee_report.html")

    # Final summary
    print(f"\n{'='*50}")
    print(f"SUMMARY")
    print(f"  Roasters scraped: {len(BOOKMARKS)}")
    print(f"  Roasters with coffees: {len(BOOKMARKS) - len(failed)}")
    print(f"  Total coffees found: {total_coffees}")
    if failed:
        print(f"  Failed/empty ({len(failed)}):")
        for f in failed:
            print(f"    - {f}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
