#!/usr/bin/env python3
"""
Scrape Singapore coffee roasters' sites for coffee bean listings.

Strategy:
1. Try Shopify /products.json endpoint first (most roasters use Shopify).
2. Fall back to HTML scraping with BeautifulSoup.
3. Follow pagination.
4. Output structured JSON + generate an HTML display page.
"""

import asyncio
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

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

TOTAL_LIMIT = 500_000  # cap total scraped text
TIMEOUT = 20


def get_base_url(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def parse_price(text: str) -> str | None:
    if not text:
        return None
    m = re.search(r'\$?\s*([\d,]+\.?\d*)', str(text))
    return f"${m.group(1)}" if m else None


def parse_weight(text: str) -> str | None:
    if not text:
        return None
    m = re.search(r'(\d+)\s*(g|kg|oz|lb)\b', str(text), re.I)
    if m:
        return f"{m.group(1)}{m.group(2).lower()}"
    return None


def compute_price_per_100g(price: str | None, weight: str | None) -> str | None:
    if not price or not weight:
        return None
    try:
        p = float(re.search(r'([\d.]+)', price).group(1))
        wm = re.match(r'(\d+)(g|kg|oz|lb)', weight, re.I)
        if not wm:
            return None
        w = float(wm.group(1))
        unit = wm.group(2).lower()
        if unit == 'kg':
            w *= 1000
        elif unit == 'oz':
            w *= 28.3495
        elif unit == 'lb':
            w *= 453.592
        if w == 0:
            return None
        per100 = (p / w) * 100
        return f"${per100:.2f}"
    except Exception:
        return None


def guess_roast_level(text: str) -> str | None:
    text_lower = text.lower()
    for level in ["light-medium", "medium-dark", "medium-light"]:
        if level in text_lower:
            return level.replace("-", " ").title()
    for level in ["light", "medium", "dark", "espresso", "filter", "omni"]:
        if level in text_lower:
            return level.title()
    return None


def guess_process(text: str) -> str | None:
    text_lower = text.lower()
    processes = [
        "natural anaerobic", "washed anaerobic", "honey anaerobic",
        "double washed", "fully washed", "semi washed",
        "natural", "washed", "honey", "wet hulled", "anaerobic",
        "carbonic maceration", "lactic", "thermal shock",
    ]
    for p in processes:
        if p in text_lower:
            return p.title()
    return None


def guess_origin(text: str) -> str | None:
    origins = [
        "Ethiopia", "Kenya", "Colombia", "Brazil", "Guatemala", "Costa Rica",
        "Honduras", "El Salvador", "Panama", "Peru", "Mexico", "Rwanda",
        "Burundi", "Tanzania", "Uganda", "DRC", "Congo", "Indonesia",
        "Sumatra", "Java", "Sulawesi", "Papua New Guinea", "India",
        "Vietnam", "Myanmar", "Laos", "Thailand", "China", "Yunnan",
        "Yemen", "Nepal", "Bolivia", "Ecuador", "Nicaragua", "Haiti",
        "Jamaica", "Hawaii", "Malawi", "Zambia", "Zimbabwe",
        "Geisha", "Gesha",
    ]
    for o in origins:
        if o.lower() in text.lower():
            return o
    # Check for blends
    if re.search(r'\bblend\b', text, re.I):
        return "Blend"
    return None


# ---------- Shopify products.json scraping ----------

async def try_shopify_json(client: httpx.AsyncClient, base_url: str) -> list[dict] | None:
    """Try fetching products via Shopify's /products.json endpoint."""
    products = []
    page = 1
    while page <= 10:  # safety cap
        url = f"{base_url}/products.json?limit=250&page={page}"
        try:
            resp = await client.get(url, timeout=TIMEOUT)
            if resp.status_code != 200:
                return None if page == 1 else products
            data = resp.json()
            batch = data.get("products", [])
            if not batch:
                break
            products.extend(batch)
            page += 1
        except Exception:
            return None if page == 1 else products
    return products if products else None


def extract_shopify_coffees(products: list[dict], roaster_name: str) -> list[dict]:
    """Extract coffee info from Shopify product JSON."""
    coffees = []
    coffee_keywords = ["coffee", "bean", "roast", "espresso", "filter", "blend",
                       "single origin", "decaf", "drip", "pour over"]
    skip_keywords = ["grinder", "brewer", "mug", "cup", "tumbler", "filter paper",
                     "dripper", "kettle", "scale", "subscription", "gift card",
                     "merchandise", "merch", "tote", "shirt", "cap", "hat",
                     "sticker", "poster"]

    for prod in products:
        title = prod.get("title", "")
        product_type = prod.get("product_type", "").lower()
        tags = " ".join(prod.get("tags", [])).lower() if isinstance(prod.get("tags"), list) else str(prod.get("tags", "")).lower()
        body = prod.get("body_html", "") or ""
        full_text = f"{title} {product_type} {tags} {body}".lower()

        # Skip non-coffee products
        if any(kw in full_text for kw in skip_keywords):
            if not any(kw in full_text for kw in coffee_keywords):
                continue

        # Must have some coffee indicator
        is_coffee = (
            any(kw in full_text for kw in coffee_keywords)
            or product_type in ["coffee", "beans", "coffee beans"]
            or not product_type  # if no type, might still be coffee on a coffee-only store
        )
        if not is_coffee:
            continue

        # Get variants for price/weight
        variants = prod.get("variants", [])
        price = None
        weight = None

        if variants:
            v = variants[0]
            price = parse_price(str(v.get("price", "")))
            # Try weight from variant title or grams field
            weight_grams = v.get("grams", 0)
            if weight_grams and weight_grams > 0:
                weight = f"{weight_grams}g"
            else:
                weight = parse_weight(v.get("title", "")) or parse_weight(title) or parse_weight(body)

        if not price:
            price = parse_price(title)

        # Clean body HTML for text extraction
        body_text = BeautifulSoup(body, "lxml").get_text(" ", strip=True) if body else ""
        search_text = f"{title} {body_text} {tags}"

        coffee = {
            "name": title.strip(),
            "roaster": roaster_name,
            "origin": guess_origin(search_text),
            "process": guess_process(search_text),
            "tasting_notes": extract_tasting_notes(search_text),
            "price": price,
            "weight": weight,
            "price_per_100g": compute_price_per_100g(price, weight),
            "roast_level": guess_roast_level(search_text),
        }
        coffees.append(coffee)

    return coffees


def extract_tasting_notes(text: str) -> str | None:
    """Try to find tasting notes from text."""
    patterns = [
        r'(?:tasting\s*notes?|flavou?r\s*notes?|cup\s*profile|taste\s*notes?)[:\s]*([^\n]{5,120})',
        r'(?:notes?)[:\s]*([A-Z][a-z]+(?:\s*[,&/]\s*[A-Z][a-z]+){1,8})',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            notes = m.group(1).strip()
            # Clean up HTML artifacts
            notes = re.sub(r'<[^>]+>', '', notes).strip()
            # Cut off at common stop words/patterns
            notes = re.split(r'\s*(?:Roast\s*Profile|Agtron|Region|Origin|Process|Elevation|Altitude|Varietal|Variety|Weight|SCA|Score|ABout|Description)\b', notes, flags=re.I)[0]
            notes = notes.strip().strip(".,;: ")
            if len(notes) > 5 and len(notes) < 120:
                return notes
    return None


# ---------- HTML scraping fallback ----------

async def fetch_pages(client: httpx.AsyncClient, start_url: str, max_pages: int = 5) -> str:
    """Fetch the start URL and follow pagination."""
    all_text = []
    visited = set()

    for page_num in range(1, max_pages + 1):
        if page_num == 1:
            url = start_url
        else:
            sep = "&" if "?" in start_url else "?"
            url = f"{start_url}{sep}page={page_num}"

        if url in visited:
            break
        visited.add(url)

        try:
            resp = await client.get(url, timeout=TIMEOUT, follow_redirects=True)
            if resp.status_code != 200:
                break
            html = resp.text
            soup = BeautifulSoup(html, "lxml")

            # Remove scripts, styles
            for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
                tag.decompose()

            text = soup.get_text(" ", strip=True)
            all_text.append(f"--- PAGE {page_num}: {url} ---\n{text[:20000]}")

            # Check if there's a next page
            if page_num > 1 and len(text) < 200:
                break  # likely empty page

        except Exception as e:
            print(f"  Error fetching {url}: {e}")
            break

    return "\n\n".join(all_text)


def extract_coffees_from_html(html_text: str, roaster_name: str, url: str) -> list[dict]:
    """Best-effort extraction from raw HTML text. Returns minimal records."""
    # This is a fallback - we'll just create a single record indicating we found the page
    # but couldn't parse structured data
    coffees = []

    # Try to find product-like patterns
    lines = html_text.split("\n")
    for line in lines:
        # Look for price patterns near product names
        prices = re.findall(r'\$\s*\d+\.?\d*', line)
        if prices and len(line) < 500:
            coffee = {
                "name": line[:100].strip(),
                "roaster": roaster_name,
                "origin": guess_origin(line),
                "process": guess_process(line),
                "tasting_notes": extract_tasting_notes(line),
                "price": prices[0] if prices else None,
                "weight": parse_weight(line),
                "price_per_100g": None,
                "roast_level": guess_roast_level(line),
            }
            coffee["price_per_100g"] = compute_price_per_100g(coffee["price"], coffee["weight"])
            coffees.append(coffee)

    return coffees


# ---------- Main scraping logic ----------

async def scrape_roaster(client: httpx.AsyncClient, bookmark: dict, semaphore: asyncio.Semaphore) -> dict:
    """Scrape a single roaster and return structured data."""
    name = bookmark["name"]
    url = bookmark["url"]
    base_url = get_base_url(url)

    async with semaphore:
        print(f"  Scraping {name}...", flush=True)

        # Strategy 1: Try Shopify JSON
        products = await try_shopify_json(client, base_url)
        if products:
            coffees = extract_shopify_coffees(products, name)
            method = "shopify_json"
            print(f"  OK {name}: {len(coffees)} coffees (Shopify JSON, {len(products)} total products)")
        else:
            # Strategy 2: HTML scraping
            page_text = await fetch_pages(client, url)
            coffees = extract_coffees_from_html(page_text, name, url)
            method = "html_scrape"
            print(f"  OK {name}: {len(coffees)} coffees (HTML scrape)")

        return {
            "roaster": name,
            "url": url,
            "coffees": coffees,
            "method": method,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        }


async def main():
    print(f"Starting scrape of {len(BOOKMARKS)} roasters...\n", flush=True)

    semaphore = asyncio.Semaphore(5)  # max 5 concurrent requests

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        tasks = [scrape_roaster(client, bm, semaphore) for bm in BOOKMARKS]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    all_coffees = []
    roaster_summaries = []
    errors = []

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            errors.append(f"{BOOKMARKS[i]['name']}: {result}")
            continue
        all_coffees.extend(result["coffees"])
        roaster_summaries.append({
            "name": result["roaster"],
            "url": result["url"],
            "coffee_count": len(result["coffees"]),
            "method": result["method"],
        })

    # Build output JSON
    output = {
        "coffees": all_coffees,
        "summary": f"Found {len(all_coffees)} coffees from {len(roaster_summaries)} roasters "
                   f"({sum(1 for r in roaster_summaries if r['method'] == 'shopify_json')} via Shopify JSON, "
                   f"{sum(1 for r in roaster_summaries if r['method'] == 'html_scrape')} via HTML scrape). "
                   f"{len(errors)} errors.",
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "roasters": roaster_summaries,
        "errors": errors,
    }

    # Save JSON
    out_path = Path(__file__).parent / "coffees.json"
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved {len(all_coffees)} coffees to {out_path}")

    # Generate HTML
    generate_html(output)

    print(f"Generated index.html")
    print(f"\nSummary: {output['summary']}")
    if errors:
        print(f"\nErrors:")
        for e in errors:
            print(f"  - {e}")


def generate_html(data: dict):
    """Generate a static HTML page displaying the coffee data."""
    coffees = data["coffees"]
    summary = data["summary"]
    last_updated = data["last_updated"]
    roasters = data.get("roasters", [])

    # Group coffees by roaster
    by_roaster = {}
    for c in coffees:
        r = c.get("roaster", "Unknown")
        by_roaster.setdefault(r, []).append(c)

    # Build roaster cards
    roaster_sections = []
    for roaster_info in sorted(roasters, key=lambda x: x["name"]):
        name = roaster_info["name"]
        url = roaster_info["url"]
        rcoffees = by_roaster.get(name, [])
        if not rcoffees:
            continue

        cards = []
        for c in rcoffees:
            badges = []
            if c.get("roast_level"):
                badges.append(f'<span class="badge badge-roast">{c["roast_level"]}</span>')
            if c.get("process"):
                badges.append(f'<span class="badge badge-process">{c["process"]}</span>')
            if c.get("origin"):
                badges.append(f'<span class="badge badge-origin">{c["origin"]}</span>')

            price_html = ""
            if c.get("price"):
                price_html = f'<div class="price">{c["price"]}'
                if c.get("weight"):
                    price_html += f' <small>/ {c["weight"]}</small>'
                if c.get("price_per_100g"):
                    price_html += f' <small class="per100g">({c["price_per_100g"]}/100g)</small>'
                price_html += '</div>'

            notes_html = ""
            if c.get("tasting_notes"):
                notes_html = f'<div class="tasting-notes">{c["tasting_notes"]}</div>'

            cards.append(f"""
            <div class="coffee-card">
                <div class="coffee-name">{c.get("name", "Unknown")}</div>
                <div class="badges">{"".join(badges)}</div>
                {notes_html}
                {price_html}
            </div>""")

        roaster_sections.append(f"""
        <div class="roaster-section">
            <div class="roaster-header">
                <h2>{name} <span class="coffee-count">({len(rcoffees)} coffees)</span></h2>
                <a href="{url}" target="_blank" rel="noopener">Visit Shop</a>
            </div>
            <div class="coffee-grid">
                {"".join(cards)}
            </div>
        </div>""")

    # Stats
    total = len(coffees)
    origins = {}
    for c in coffees:
        o = c.get("origin")
        if o:
            origins[o] = origins.get(o, 0) + 1
    top_origins = sorted(origins.items(), key=lambda x: -x[1])[:10]
    origin_stats = ", ".join(f"{o} ({n})" for o, n in top_origins)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Singapore Coffee Roasters</title>
<style>
  :root {{
    --bg: #0f1114;
    --surface: #1a1d23;
    --surface2: #22262e;
    --border: #2d3139;
    --text: #e4e4e7;
    --text-muted: #9ca3af;
    --accent: #c8a97e;
    --accent2: #a67c52;
    --green: #6ee7b7;
    --blue: #93c5fd;
    --pink: #f9a8d4;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
  }}
  .container {{ max-width: 1200px; margin: 0 auto; padding: 2rem 1rem; }}
  header {{
    text-align: center;
    padding: 3rem 1rem;
    border-bottom: 1px solid var(--border);
    margin-bottom: 2rem;
  }}
  header h1 {{
    font-size: 2.5rem;
    color: var(--accent);
    margin-bottom: 0.5rem;
    letter-spacing: -0.02em;
  }}
  header p {{ color: var(--text-muted); font-size: 1.1rem; }}
  .stats {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 1rem;
    margin-bottom: 2rem;
  }}
  .stat-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.25rem;
    text-align: center;
  }}
  .stat-card .number {{
    font-size: 2rem;
    font-weight: 700;
    color: var(--accent);
  }}
  .stat-card .label {{
    color: var(--text-muted);
    font-size: 0.85rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }}
  .filter-bar {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1rem 1.25rem;
    margin-bottom: 2rem;
    display: flex;
    gap: 1rem;
    flex-wrap: wrap;
    align-items: center;
  }}
  .filter-bar input {{
    flex: 1;
    min-width: 200px;
    padding: 0.6rem 1rem;
    border-radius: 8px;
    border: 1px solid var(--border);
    background: var(--surface2);
    color: var(--text);
    font-size: 0.95rem;
    outline: none;
  }}
  .filter-bar input:focus {{ border-color: var(--accent); }}
  .filter-bar select {{
    padding: 0.6rem 1rem;
    border-radius: 8px;
    border: 1px solid var(--border);
    background: var(--surface2);
    color: var(--text);
    font-size: 0.95rem;
    outline: none;
    cursor: pointer;
  }}
  .roaster-section {{
    margin-bottom: 2.5rem;
  }}
  .roaster-header {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid var(--border);
  }}
  .roaster-header h2 {{
    font-size: 1.4rem;
    color: var(--text);
  }}
  .roaster-header a {{
    color: var(--accent);
    text-decoration: none;
    font-size: 0.85rem;
  }}
  .roaster-header a:hover {{ text-decoration: underline; }}
  .coffee-count {{ color: var(--text-muted); font-weight: 400; font-size: 1rem; }}
  .coffee-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 1rem;
  }}
  .coffee-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.25rem;
    transition: border-color 0.2s;
  }}
  .coffee-card:hover {{ border-color: var(--accent2); }}
  .coffee-name {{
    font-weight: 600;
    font-size: 1.05rem;
    margin-bottom: 0.5rem;
    line-height: 1.3;
  }}
  .badges {{ display: flex; flex-wrap: wrap; gap: 0.35rem; margin-bottom: 0.5rem; }}
  .badge {{
    display: inline-block;
    padding: 0.15rem 0.55rem;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 500;
  }}
  .badge-roast {{ background: rgba(200,169,126,0.15); color: var(--accent); }}
  .badge-process {{ background: rgba(110,231,183,0.12); color: var(--green); }}
  .badge-origin {{ background: rgba(147,197,253,0.12); color: var(--blue); }}
  .tasting-notes {{
    font-size: 0.88rem;
    color: var(--text-muted);
    font-style: italic;
    margin-bottom: 0.5rem;
  }}
  .price {{
    font-size: 1.1rem;
    font-weight: 600;
    color: var(--accent);
  }}
  .price small {{ font-weight: 400; color: var(--text-muted); font-size: 0.8rem; }}
  .per100g {{ opacity: 0.7; }}
  footer {{
    text-align: center;
    padding: 2rem 1rem;
    border-top: 1px solid var(--border);
    color: var(--text-muted);
    font-size: 0.85rem;
    margin-top: 2rem;
  }}
  @media (max-width: 600px) {{
    header h1 {{ font-size: 1.8rem; }}
    .coffee-grid {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>
<header>
  <h1>Singapore Coffee Roasters</h1>
  <p>A curated directory of specialty coffee beans from {len(roasters)} local roasters</p>
  <p style="margin-top: 0.5rem; font-size: 0.85rem;">Last updated: {last_updated}</p>
</header>

<div class="container">
  <div class="stats">
    <div class="stat-card">
      <div class="number">{total}</div>
      <div class="label">Total Coffees</div>
    </div>
    <div class="stat-card">
      <div class="number">{len(roasters)}</div>
      <div class="label">Roasters</div>
    </div>
    <div class="stat-card">
      <div class="number">{len(origins)}</div>
      <div class="label">Origins</div>
    </div>
  </div>

  <div class="filter-bar">
    <input type="text" id="search" placeholder="Search coffees, roasters, origins..." oninput="filterCoffees()">
    <select id="originFilter" onchange="filterCoffees()">
      <option value="">All Origins</option>
    </select>
    <select id="roastFilter" onchange="filterCoffees()">
      <option value="">All Roasts</option>
    </select>
  </div>

  <div id="roasters">
    {"".join(roaster_sections)}
  </div>
</div>

<footer>
  <p>{summary}</p>
  <p style="margin-top: 0.5rem;">Top origins: {origin_stats}</p>
</footer>

<script>
const coffeeData = {json.dumps(coffees, ensure_ascii=False)};

// Populate filter dropdowns
const origins = [...new Set(coffeeData.map(c => c.origin).filter(Boolean))].sort();
const roasts = [...new Set(coffeeData.map(c => c.roast_level).filter(Boolean))].sort();
const originSelect = document.getElementById('originFilter');
const roastSelect = document.getElementById('roastFilter');
origins.forEach(o => {{ const opt = document.createElement('option'); opt.value = o; opt.textContent = o; originSelect.appendChild(opt); }});
roasts.forEach(r => {{ const opt = document.createElement('option'); opt.value = r; opt.textContent = r; roastSelect.appendChild(opt); }});

function filterCoffees() {{
  const q = document.getElementById('search').value.toLowerCase();
  const origin = originSelect.value;
  const roast = roastSelect.value;

  document.querySelectorAll('.roaster-section').forEach(section => {{
    let visibleCards = 0;
    section.querySelectorAll('.coffee-card').forEach(card => {{
      const text = card.textContent.toLowerCase();
      const roasterName = section.querySelector('h2').textContent.toLowerCase();
      const matchSearch = !q || text.includes(q) || roasterName.includes(q);
      const matchOrigin = !origin || card.querySelector('.badge-origin')?.textContent === origin;
      const matchRoast = !roast || card.querySelector('.badge-roast')?.textContent === roast;
      const show = matchSearch && matchOrigin && matchRoast;
      card.style.display = show ? '' : 'none';
      if (show) visibleCards++;
    }});
    section.style.display = visibleCards > 0 ? '' : 'none';
  }});
}}
</script>
</body>
</html>"""

    out_path = Path(__file__).parent / "index.html"
    out_path.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
