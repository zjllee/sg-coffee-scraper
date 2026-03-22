You are building a Python script to scrape Singapore coffee roaster websites and extract their bean offerings.

Task: Create coffee_agent.py that scrapes all roaster URLs, extracts coffee product data using the Claude API, and saves results to roaster_data.json.

Dependencies to install: requests, beautifulsoup4, anthropic

Roaster list:


python
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
Scraping requirements:

Use requests + BeautifulSoup to fetch and parse pages
Handle pagination: probe ?page=2, ?page=3 etc. up to page 5, stopping early if the page is empty or identical to the previous one
Set a browser-like User-Agent header to avoid blocks
Gracefully handle failed fetches (timeouts, 403s) — log the error and continue
Extraction requirements:

Pass the scraped text to the Claude API (claude-sonnet-4-20250514) to extract coffee bean listings only — ignore equipment, merchandise, and accessories
Use anthropic Python SDK (not raw HTTP)
Extract each coffee into this exact JSON shape:

json
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
price_per_100g: calculate from price and weight if both are present, otherwise null
All fields except name can be null if not found
If a product lists multiple sizes/prices (e.g. 200g and 1kg), create one entry per size
The prompt to Claude must instruct it to return raw JSON only — no markdown fences, no explanation
Output requirements:

Save to roaster_data.json in this structure:

json
{
  "scraped_at": "2026-03-21T08:00:00",
  "roasters": [
    {
      "name": "Nylon Coffee Roasters",
      "url": "https://...",
      "coffees": [...],
      "summary": "One sentence about what stands out.",
      "error": null
    }
  ]
}
Print progress to console: roaster name, pages fetched, coffees found
At the end, print a summary: total roasters scraped, total coffees found, any failed roasters
  Save the results to roaster_data.json as specified above, and also generate a coffee_report.html file. The HTML report should be well-styled and readable, with one card per roaster showing all their coffees in a table with columns for name, origin, process, roast level, tasting notes, price, weight, and price per 100g. Highlight the best value (lowest price per 100g) across all roasters.