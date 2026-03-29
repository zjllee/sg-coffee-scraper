#!/usr/bin/env python3
"""
Scrape Singapore coffee roaster websites and extract bean offerings using Claude API.

1. Fetch each roaster's collection page (+ pagination).
2. For Shopify sites, also try /products.json for richer data.
3. Pass scraped text to Claude API to extract structured coffee data.
4. Save results to roaster_data.json and generate coffee_report.html.
"""

import argparse
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from llm_providers import LLMError, LLMProvider, get_provider

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


# ---------- LLM extraction ----------

def extract_coffees(
    provider: LLMProvider,
    roaster_name: str,
    scraped_text: str,
) -> tuple[list[dict], str | None, str | None]:
    """
    Send scraped text to an LLM provider for coffee extraction.
    Returns (coffees_list, summary_string, error_string).
    """
    if not scraped_text or len(scraped_text.strip()) < 50:
        return [], None, "Input text too short for extraction."

    prompt = EXTRACTION_PROMPT + f"Roaster: {roaster_name}\n\n{scraped_text}"

    try:
        raw = provider.generate(prompt)

        # Strip thinking tags (qwen3, deepseek-r1, etc.)
        raw = re.sub(r'<think>.*?</think>\s*', '', raw, flags=re.DOTALL)

        # Strip markdown fences if LLM added them despite instructions
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
    except LLMError as e:
        err = str(e)
        print(f"    {err}")
        return [], None, err


# ---------- HTML report generation ----------

def generate_report(data: dict, provider_name: str = "anthropic"):
    """Generate coffee_report.html with dynamic JS rendering and archive support."""
    inline_json = json.dumps(data, ensure_ascii=False)

    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Singapore Coffee Report</title>
<style>
  :root {
    --bg: #0f1114; --surface: #1a1d23; --surface2: #22262e;
    --border: #2d3139; --text: #e4e4e7; --muted: #9ca3af;
    --accent: #c8a97e; --accent2: #a67c52; --green: #6ee7b7;
    --blue: #93c5fd; --red: #fca5a5; --gold: #fbbf24;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.6;
  }
  .container { max-width: 1400px; margin: 0 auto; padding: 2rem 1rem; }
  header {
    text-align: center; padding: 3rem 1rem;
    border-bottom: 1px solid var(--border); margin-bottom: 2rem;
  }
  header h1 { font-size: 2.5rem; color: var(--accent); margin-bottom: 0.5rem; }
  header p { color: var(--muted); }
  .stats {
    display: flex; gap: 1rem; justify-content: center; flex-wrap: wrap; margin-bottom: 2rem;
  }
  .stat { background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
    padding: 1.25rem 2rem; text-align: center; }
  .stat .num { font-size: 2rem; font-weight: 700; color: var(--accent); }
  .stat .lbl { color: var(--muted); font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; }
  .highlight-card {
    background: linear-gradient(135deg, rgba(251,191,36,0.1), rgba(200,169,126,0.1));
    border: 1px solid var(--gold); border-radius: 12px;
    padding: 1.5rem; text-align: center; margin-bottom: 2rem;
  }
  .highlight-label { color: var(--gold); font-size: 0.8rem; text-transform: uppercase;
    letter-spacing: 0.1em; font-weight: 600; }
  .highlight-name { font-size: 1.3rem; font-weight: 700; margin: 0.25rem 0; }
  .highlight-detail { color: var(--muted); }
  .filter-bar {
    background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
    padding: 1rem 1.25rem; margin-bottom: 2rem; display: flex; gap: 1rem; flex-wrap: wrap;
    align-items: center;
  }
  .filter-bar input {
    flex: 1; min-width: 200px; padding: 0.6rem 1rem; border-radius: 8px;
    border: 1px solid var(--border); background: var(--surface2); color: var(--text);
    font-size: 0.95rem; outline: none;
  }
  .filter-bar input:focus { border-color: var(--accent); }
  .filter-group { display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap; }
  .filter-label { color: var(--muted); font-size: 0.8rem; text-transform: uppercase;
    letter-spacing: 0.05em; white-space: nowrap; }
  .filter-btn {
    padding: 0.4rem 0.85rem; border-radius: 6px; border: 1px solid var(--border);
    background: var(--surface2); color: var(--muted); font-size: 0.82rem;
    cursor: pointer; transition: all 0.15s;
  }
  .filter-btn:hover { border-color: var(--accent); color: var(--accent); }
  .filter-btn.active { background: var(--accent); color: #000; border-color: var(--accent); font-weight: 600; }
  tr.hidden-row { display: none; }
  .roaster-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 12px; padding: 1.5rem; margin-bottom: 1.5rem;
  }
  .roaster-header {
    display: flex; justify-content: space-between; align-items: baseline;
    margin-bottom: 0.75rem;
  }
  .roaster-header h2 { font-size: 1.3rem; }
  .roaster-header a { color: var(--accent); text-decoration: none; font-size: 0.85rem; }
  .roaster-header a:hover { text-decoration: underline; }
  .count { color: var(--muted); font-weight: 400; font-size: 0.95rem; }
  .roaster-summary { color: var(--muted); font-style: italic; margin-bottom: 0.75rem; font-size: 0.9rem; }
  .error-msg { color: var(--red); font-size: 0.9rem; }
  .table-wrap { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
  th { text-align: left; padding: 0.6rem 0.75rem; border-bottom: 2px solid var(--border);
    color: var(--muted); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; }
  td { padding: 0.5rem 0.75rem; border-bottom: 1px solid var(--border); vertical-align: top; }
  tr:hover { background: var(--surface2); }
  .best-value { background: rgba(251,191,36,0.06); }
  .best-tag {
    display: inline-block; background: var(--gold); color: #000; font-size: 0.65rem;
    padding: 0.1rem 0.4rem; border-radius: 4px; font-weight: 700; margin-left: 0.5rem;
    vertical-align: middle;
  }
  .notes { max-width: 200px; font-style: italic; color: var(--muted); }
  footer {
    text-align: center; padding: 2rem; border-top: 1px solid var(--border);
    color: var(--muted); font-size: 0.85rem; margin-top: 2rem;
  }
  /* Roaster dropdown */
  .roaster-dropdown-wrap { position: relative; }
  .roaster-dropdown-btn {
    padding: 0.4rem 0.85rem; border-radius: 6px; border: 1px solid var(--border);
    background: var(--surface2); color: var(--text); font-size: 0.82rem;
    cursor: pointer; display: flex; align-items: center; gap: 0.4rem; white-space: nowrap;
    transition: border-color 0.15s;
  }
  .roaster-dropdown-btn:hover { border-color: var(--accent); }
  .roaster-dropdown-btn.has-filter { border-color: var(--accent); color: var(--accent); }
  .roaster-dropdown-panel {
    display: none; position: absolute; top: calc(100% + 6px); left: 0; z-index: 100;
    background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
    padding: 0.5rem; min-width: 260px; max-height: 320px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.4);
  }
  .roaster-dropdown-panel.open { display: flex; flex-direction: column; gap: 0.25rem; }
  .roaster-dropdown-search {
    padding: 0.45rem 0.75rem; border-radius: 6px; border: 1px solid var(--border);
    background: var(--surface2); color: var(--text); font-size: 0.82rem; outline: none;
    margin-bottom: 0.25rem;
  }
  .roaster-dropdown-search:focus { border-color: var(--accent); }
  .roaster-list {
    overflow-y: auto; max-height: 210px; display: flex; flex-direction: column; gap: 1px;
  }
  .roaster-list label {
    display: flex; align-items: center; gap: 0.5rem; padding: 0.35rem 0.5rem;
    border-radius: 5px; cursor: pointer; font-size: 0.82rem; color: var(--text);
    transition: background 0.1s;
  }
  .roaster-list label:hover { background: var(--surface2); }
  .roaster-list input[type=checkbox] { accent-color: var(--accent); width: 14px; height: 14px; flex-shrink: 0; }
  .dropdown-actions {
    display: flex; gap: 0.4rem; padding-top: 0.4rem;
    border-top: 1px solid var(--border); margin-top: 0.25rem;
  }
  .dropdown-action-btn {
    flex: 1; padding: 0.35rem; border-radius: 5px; border: 1px solid var(--border);
    background: var(--surface2); color: var(--muted); font-size: 0.78rem;
    cursor: pointer; text-align: center; transition: all 0.15s;
  }
  .dropdown-action-btn:hover { border-color: var(--accent); color: var(--accent); }
  /* Archive select */
  .archive-select {
    padding: 0.4rem 0.85rem; border-radius: 6px; border: 1px solid var(--border);
    background: var(--surface2); color: var(--text); font-size: 0.82rem;
    cursor: pointer; outline: none;
  }
  .archive-select:focus { border-color: var(--accent); }
  .archive-msg {
    color: var(--muted); font-size: 0.8rem; font-style: italic;
    text-align: center; padding: 0.5rem; display: none;
  }
  @media (max-width: 768px) {
    header h1 { font-size: 1.8rem; }
    .stats { flex-direction: column; align-items: center; }
    th, td { padding: 0.4rem 0.5rem; font-size: 0.8rem; }
  }
</style>
</head>
<body>
<header>
  <h1>Singapore Coffee Report</h1>
  <p id="subtitle"></p>
  <p id="scraped-date" style="margin-top:0.3rem; font-size:0.85rem;"></p>
</header>
<div class="container">
  <div class="stats" id="stats"></div>
  <div id="best-value-container"></div>
  <div class="filter-bar">
    <input type="text" id="search" placeholder="Search coffees, origins, tasting notes..." oninput="applyFilters()">
    <div class="filter-group">
      <span class="filter-label">Weight</span>
      <button class="filter-btn active" data-weight="all" onclick="setWeight(this,'all')">All</button>
      <button class="filter-btn" data-weight="small" onclick="setWeight(this,'small')">&lt; 400g</button>
      <button class="filter-btn" data-weight="large" onclick="setWeight(this,'large')">&gt; 400g</button>
    </div>
    <div class="filter-group">
      <span class="filter-label">Sort rows by</span>
      <button class="filter-btn active" data-sort="default" onclick="setSort(this,'default')">Default</button>
      <button class="filter-btn" data-sort="price" onclick="setSort(this,'price')">Price / 100g &#8593;</button>
      <button class="filter-btn" data-sort="alpha" onclick="setSort(this,'alpha')">A &rarr; Z</button>
    </div>
    <div class="filter-group">
      <span class="filter-label">Roasters</span>
      <div class="roaster-dropdown-wrap" id="roasterDropdownWrap">
        <button class="roaster-dropdown-btn" id="roasterDropdownBtn" onclick="toggleRoasterDropdown(event)">
          <span id="roasterBtnLabel">All roasters</span> &#9660;
        </button>
        <div class="roaster-dropdown-panel" id="roasterDropdownPanel">
          <input class="roaster-dropdown-search" type="text" placeholder="Find roaster..." oninput="filterRoasterList(this)">
          <div class="roaster-list" id="roasterList"></div>
          <div class="dropdown-actions">
            <button class="dropdown-action-btn" onclick="selectAllRoasters()">Select all</button>
            <button class="dropdown-action-btn" onclick="deselectAllRoasters()">Deselect all</button>
          </div>
        </div>
      </div>
    </div>
    <div class="filter-group" id="archive-group">
      <span class="filter-label">Run</span>
      <select class="archive-select" id="archive-select">
        <option value="">Latest</option>
      </select>
    </div>
  </div>
  <p class="archive-msg" id="archive-msg">Archive browsing requires an HTTP server. Run: python -m http.server 8000</p>
  <div id="roasters"></div>
</div>
<footer id="footer"></footer>
<script>
const INLINE_DATA = """ + inline_json + """;

let currentData = null;
let currentWeight = 'all';
let currentSort = 'default';
let hiddenRoasters = new Set();
let originalOrders = new WeakMap();

// ── Helpers ──
function esc(s) {
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function parseGrams(weightStr) {
  if (!weightStr || weightStr === '-') return null;
  const s = weightStr.toLowerCase().replace(/\\s/g, '');
  const kg = s.match(/^([\\d.]+)kg$/);
  if (kg) return parseFloat(kg[1]) * 1000;
  const g = s.match(/^([\\d.]+)g$/);
  if (g) return parseFloat(g[1]);
  return null;
}

function parsePricePer100g(str) {
  if (!str || str === '-') return Infinity;
  const m = str.match(/\\$?([\\d.]+)/);
  return m ? parseFloat(m[1]) : Infinity;
}

// ── Data Loading ──
function loadData(data) {
  currentData = data;
  hiddenRoasters.clear();
  originalOrders = new WeakMap();
  renderAll();
}

async function loadFromUrl(url) {
  try {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error('fetch failed');
    const data = await resp.json();
    document.getElementById('archive-msg').style.display = 'none';
    loadData(data);
  } catch (e) {
    document.getElementById('archive-msg').style.display = 'block';
  }
}

async function loadArchiveList() {
  try {
    const resp = await fetch('archives/manifest.json');
    if (!resp.ok) return;
    const manifest = await resp.json();
    const select = document.getElementById('archive-select');
    (manifest.runs || []).forEach(run => {
      const opt = document.createElement('option');
      opt.value = 'archives/' + run.filename;
      const date = run.scraped_at || run.filename;
      const info = run.coffee_count + ' coffees, ' + (run.provider || '?');
      opt.textContent = date + ' (' + info + ')';
      select.appendChild(opt);
    });
  } catch (e) {
    // No archives yet or file:// — silently ignore
  }
}

document.getElementById('archive-select').addEventListener('change', function() {
  if (this.value) {
    loadFromUrl(this.value);
  } else {
    document.getElementById('archive-msg').style.display = 'none';
    loadData(INLINE_DATA);
  }
});

// ── Rendering ──
function renderAll() {
  const data = currentData;
  const roasters = (data.roasters || []).slice().sort((a, b) => a.name.localeCompare(b.name));

  const totalCoffees = roasters.reduce((s, r) => s + (r.coffees || []).length, 0);
  const roastersWithCoffees = roasters.filter(r => r.coffees && r.coffees.length > 0).length;

  // Find best value
  let bestValue = null;
  let bestPrice = Infinity;
  roasters.forEach(r => {
    (r.coffees || []).forEach(c => {
      if (c.price_per_100g) {
        const m = c.price_per_100g.match(/[\\d.]+/);
        if (m) {
          const val = parseFloat(m[0]);
          if (val > 0 && val < bestPrice) {
            bestPrice = val;
            bestValue = { roaster: r.name, coffee: c.name, per100g: c.price_per_100g };
          }
        }
      }
    });
  });

  // Stats
  document.getElementById('stats').innerHTML =
    '<div class="stat"><div class="num">' + totalCoffees + '</div><div class="lbl">Coffees</div></div>' +
    '<div class="stat"><div class="num">' + roastersWithCoffees + '</div><div class="lbl">Roasters</div></div>' +
    '<div class="stat"><div class="num">' + roasters.length + '</div><div class="lbl">Attempted</div></div>';

  // Best value
  const bvContainer = document.getElementById('best-value-container');
  if (bestValue) {
    bvContainer.innerHTML =
      '<div class="highlight-card">' +
      '<div class="highlight-label">Best Value</div>' +
      '<div class="highlight-name">' + esc(bestValue.coffee) + '</div>' +
      '<div class="highlight-detail">' + esc(bestValue.roaster) + ' &mdash; ' + esc(bestValue.per100g) + '/100g</div>' +
      '</div>';
  } else {
    bvContainer.innerHTML = '';
  }

  // Roaster cards
  const container = document.getElementById('roasters');
  container.innerHTML = roasters.map((r, i) => renderRoasterCard(r, i, bestValue)).join('');

  // Header
  const provider = data.provider || 'Claude API';
  document.getElementById('subtitle').textContent =
    'Extracted via ' + provider + ' from ' + roasters.length + ' roasters';
  document.getElementById('scraped-date').textContent = 'Scraped: ' + (data.scraped_at || '');
  document.getElementById('footer').innerHTML =
    '<p>Generated by coffee_agent.py using ' + esc(provider) + '</p>';

  // Rebuild filters
  buildRoasterDropdown();
  applyFilters();
}

function renderRoasterCard(r, index, bestValue) {
  const coffees = r.coffees || [];
  const error = r.error;
  const name = r.name;
  const url = r.url;

  if (error && !coffees.length) {
    return '<div class="roaster-card">' +
      '<div class="roaster-header"><h2>' + esc(name) + '</h2>' +
      '<a href="' + esc(url) + '" target="_blank">Visit Shop</a></div>' +
      '<p class="error-msg">Error: ' + esc(error) + '</p></div>';
  }

  if (!coffees.length) return '';

  const summaryHtml = r.summary
    ? '<p class="roaster-summary">' + esc(r.summary) + '</p>'
    : '';

  const rows = coffees.map(c => {
    const isBest = bestValue && bestValue.roaster === name && bestValue.coffee === c.name;
    const rowClass = isBest ? ' class="best-value"' : '';
    const bestTag = isBest ? ' <span class="best-tag">BEST VALUE</span>' : '';
    return '<tr' + rowClass + '>' +
      '<td>' + esc(c.name) + bestTag + '</td>' +
      '<td>' + esc(c.origin || '-') + '</td>' +
      '<td>' + esc(c.process || '-') + '</td>' +
      '<td>' + esc(c.roast_level || '-') + '</td>' +
      '<td class="notes">' + esc(c.tasting_notes || '-') + '</td>' +
      '<td>' + esc(c.price || '-') + '</td>' +
      '<td>' + esc(c.weight || '-') + '</td>' +
      '<td>' + esc(c.price_per_100g || '-') + '</td>' +
      '</tr>';
  }).join('');

  return '<div class="roaster-card">' +
    '<div class="roaster-header">' +
    '<h2>' + esc(name) + ' <span class="count">(' + coffees.length + ' coffees)</span></h2>' +
    '<a href="' + esc(url) + '" target="_blank">Visit Shop</a></div>' +
    summaryHtml +
    '<div class="table-wrap"><table><thead><tr>' +
    '<th>Name</th><th>Origin</th><th>Process</th><th>Roast</th>' +
    '<th>Tasting Notes</th><th>Price</th><th>Weight</th><th>Per 100g</th>' +
    '</tr></thead><tbody>' + rows + '</tbody></table></div></div>';
}

// ── Filter buttons ──
function setWeight(btn, val) {
  currentWeight = val;
  document.querySelectorAll('[data-weight]').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  applyFilters();
}

function setSort(btn, val) {
  currentSort = val;
  document.querySelectorAll('[data-sort]').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  applyFilters();
}

// ── Roaster dropdown ──
function buildRoasterDropdown() {
  hiddenRoasters.clear();
  const list = document.getElementById('roasterList');
  list.innerHTML = '';
  document.querySelectorAll('.roaster-card').forEach((card, i) => {
    const id = 'rc-' + i;
    card.dataset.rcid = id;
    const h2 = card.querySelector('h2');
    if (!h2) return;
    const name = h2.childNodes[0].textContent.trim();
    const label = document.createElement('label');
    label.dataset.name = name.toLowerCase();
    label.innerHTML = '<input type="checkbox" checked onchange="toggleRoaster(\\'' + id + '\\', this.checked)"> ' + name;
    list.appendChild(label);
  });
  updateRoasterBtnLabel();
}

function toggleRoasterDropdown(e) {
  e.stopPropagation();
  document.getElementById('roasterDropdownPanel').classList.toggle('open');
}

function filterRoasterList(input) {
  const q = input.value.toLowerCase();
  document.querySelectorAll('#roasterList label').forEach(lbl => {
    lbl.style.display = lbl.dataset.name.includes(q) ? '' : 'none';
  });
}

function toggleRoaster(id, checked) {
  if (checked) hiddenRoasters.delete(id);
  else hiddenRoasters.add(id);
  updateRoasterBtnLabel();
  applyFilters();
}

function selectAllRoasters() {
  hiddenRoasters.clear();
  document.querySelectorAll('#roasterList input').forEach(cb => cb.checked = true);
  updateRoasterBtnLabel();
  applyFilters();
}

function deselectAllRoasters() {
  document.querySelectorAll('.roaster-card').forEach(c => hiddenRoasters.add(c.dataset.rcid));
  document.querySelectorAll('#roasterList input').forEach(cb => cb.checked = false);
  updateRoasterBtnLabel();
  applyFilters();
}

function updateRoasterBtnLabel() {
  const total = document.querySelectorAll('.roaster-card').length;
  const hidden = hiddenRoasters.size;
  const btn = document.getElementById('roasterDropdownBtn');
  const lbl = document.getElementById('roasterBtnLabel');
  if (hidden === 0) {
    lbl.textContent = 'All roasters';
    btn.classList.remove('has-filter');
  } else {
    lbl.textContent = (total - hidden) + ' / ' + total + ' roasters';
    btn.classList.add('has-filter');
  }
}

document.addEventListener('click', e => {
  const wrap = document.getElementById('roasterDropdownWrap');
  if (wrap && !wrap.contains(e.target)) {
    document.getElementById('roasterDropdownPanel').classList.remove('open');
  }
});

// ── Core filter + sort ──
function applyFilters() {
  const q = document.getElementById('search').value.toLowerCase().trim();

  document.querySelectorAll('.roaster-card').forEach(card => {
    if (hiddenRoasters.has(card.dataset.rcid)) {
      card.style.display = 'none';
      return;
    }

    const tbody = card.querySelector('tbody');
    if (!tbody) { card.style.display = ''; return; }

    if (!originalOrders.has(tbody)) {
      originalOrders.set(tbody, Array.from(tbody.rows));
    }

    const rows = Array.from(tbody.rows);
    let visibleCount = 0;

    rows.forEach(row => {
      const cells = Array.from(row.cells).map(c => c.textContent.toLowerCase());
      const weightCell = row.cells[6] ? row.cells[6].textContent.trim() : '';
      const grams = parseGrams(weightCell);

      const matchesSearch = !q || cells.some(c => c.includes(q));
      const matchesWeight =
        currentWeight === 'all' ? true :
        currentWeight === 'small' ? (grams === null || grams < 400) :
        (grams !== null && grams > 400);

      const visible = matchesSearch && matchesWeight;
      row.classList.toggle('hidden-row', !visible);
      if (visible) visibleCount++;
    });

    const visibleRows = rows.filter(r => !r.classList.contains('hidden-row'));
    const hiddenRows = rows.filter(r => r.classList.contains('hidden-row'));

    if (currentSort === 'price') {
      visibleRows.sort((a, b) => {
        const pa = parsePricePer100g(a.cells[7] ? a.cells[7].textContent : '');
        const pb = parsePricePer100g(b.cells[7] ? b.cells[7].textContent : '');
        return pa - pb;
      });
    } else if (currentSort === 'alpha') {
      visibleRows.sort((a, b) =>
        (a.cells[0] ? a.cells[0].textContent : '').localeCompare(
         b.cells[0] ? b.cells[0].textContent : ''));
    } else {
      const orig = originalOrders.get(tbody);
      visibleRows.sort((a, b) => orig.indexOf(a) - orig.indexOf(b));
    }

    [...visibleRows, ...hiddenRows].forEach(r => tbody.appendChild(r));
    card.style.display = (visibleCount === 0 && q) ? 'none' : '';
  });
}

// ── Init ──
loadData(INLINE_DATA);
loadArchiveList();
</script>
</body>
</html>"""

    out_path = Path(__file__).parent / "coffee_report.html"
    out_path.write_text(html, encoding="utf-8")


# ---------- Archive ----------

def archive_previous_run():
    """Archive the current roaster_data.json before overwriting."""
    base = Path(__file__).parent
    data_path = base / "roaster_data.json"
    archive_dir = base / "archives"
    manifest_path = archive_dir / "manifest.json"

    if not data_path.exists():
        return

    try:
        current = json.loads(data_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError):
        return

    scraped_at = current.get("scraped_at", "unknown")
    roasters = current.get("roasters", [])
    total_coffees = sum(len(r.get("coffees", [])) for r in roasters)
    roaster_count = len(roasters)
    provider = current.get("provider", "anthropic")

    safe_ts = scraped_at.replace(":", "-")
    archive_filename = f"{safe_ts}.json"
    archive_dir.mkdir(exist_ok=True)
    archive_path = archive_dir / archive_filename

    if archive_path.exists():
        return

    shutil.copy2(data_path, archive_path)

    manifest = {"runs": []}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            pass

    manifest["runs"].append({
        "filename": archive_filename,
        "scraped_at": scraped_at,
        "coffee_count": total_coffees,
        "roaster_count": roaster_count,
        "provider": provider,
    })
    manifest["runs"].sort(key=lambda r: r["scraped_at"], reverse=True)

    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Archived previous run ({scraped_at}) to archives/{archive_filename}")


# ---------- Main ----------

def main():
    parser = argparse.ArgumentParser(
        description="Scrape SG coffee roasters using LLM extraction"
    )
    parser.add_argument(
        "--provider",
        choices=["anthropic", "gemini", "ollama"],
        default=os.environ.get("LLM_PROVIDER", "anthropic"),
        help="LLM provider for extraction (default: anthropic, or set LLM_PROVIDER env var)",
    )
    args = parser.parse_args()

    try:
        provider = get_provider(args.provider)
    except LLMError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    print(f"Using LLM provider: {args.provider}")

    # Archive previous run before starting new one
    archive_previous_run()

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
            print(f"  No content retrieved, skipping LLM extraction")
            results.append({
                "name": name,
                "url": url,
                "coffees": [],
                "summary": None,
                "error": "No content could be fetched from the site.",
            })
            failed.append(name)
            continue

        # Extract via LLM
        coffees, summary, error = extract_coffees(provider, name, scraped_text)
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
        "provider": args.provider,
        "roasters": results,
    }

    # Save JSON
    out_path = Path(__file__).parent / "roaster_data.json"
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved to {out_path}")

    # Generate HTML report
    generate_report(output, args.provider)
    report_path = Path(__file__).parent / "coffee_report.html"
    index_path = Path(__file__).parent / "index.html"
    shutil.copy2(report_path, index_path)
    print(f"Generated coffee_report.html + index.html")

    # Final summary
    print(f"\n{'='*50}")
    print(f"SUMMARY")
    print(f"  Provider: {args.provider}")
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
