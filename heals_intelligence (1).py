"""
╔══════════════════════════════════════════════════════════════════╗
║  Barker & Stonehouse — Heals Intelligence Scraper               ║
║  Full site coverage · no PDP fetching                           ║
╠══════════════════════════════════════════════════════════════════╣
║  Usage:  py heals_intelligence.py                               ║
║  Output: heals_intelligence.json  →  upload to GitHub           ║
╚══════════════════════════════════════════════════════════════════╝
"""

import requests, json, re, os, time
from bs4 import BeautifulSoup
from datetime import datetime

SCRAPERAPI_KEY = "d3200b71ef63fb84b501a308f91fb1a4"
OUTPUT_FILE    = "heals_intelligence.json"
HISTORY_FILE   = "heals_history.json"

# ── Full Heals site coverage ───────────────────────────────────────────────────
# Every major category + brand page.  The scraper paginates each one automatically.
# label = how the product appears in the dashboard Category column
HEALS_PAGES = [
    # ── Furniture ────────────────────────────────────────────────────────────
    {"label": "Sofas",              "url": "https://www.heals.com/sofas.html"},
    {"label": "Armchairs",          "url": "https://www.heals.com/armchairs.html"},
    {"label": "Dining Tables",      "url": "https://www.heals.com/dining/dining-tables.html"},
    {"label": "Dining Chairs",      "url": "https://www.heals.com/dining/dining-chairs.html"},
    {"label": "Coffee Tables",      "url": "https://www.heals.com/coffee-side-tables.html"},
    {"label": "Sideboards",         "url": "https://www.heals.com/sideboards-storage.html"},
    {"label": "Shelving",           "url": "https://www.heals.com/shelving-bookcases.html"},
    {"label": "TV Units",           "url": "https://www.heals.com/tv-units.html"},
    {"label": "Office Desks",       "url": "https://www.heals.com/home-office/desks.html"},
    {"label": "Office Chairs",      "url": "https://www.heals.com/home-office/office-chairs.html"},
    # ── Bedroom ───────────────────────────────────────────────────────────────
    {"label": "Beds",               "url": "https://www.heals.com/beds.html"},
    {"label": "Wardrobes",          "url": "https://www.heals.com/wardrobes.html"},
    {"label": "Chest of Drawers",   "url": "https://www.heals.com/chest-of-drawers.html"},
    {"label": "Bedside Tables",     "url": "https://www.heals.com/bedside-tables.html"},
    {"label": "Mattresses",         "url": "https://www.heals.com/mattresses.html"},
    # ── Lighting ──────────────────────────────────────────────────────────────
    {"label": "Pendant Lighting",   "url": "https://www.heals.com/lighting/pendant-lights.html"},
    {"label": "Floor Lamps",        "url": "https://www.heals.com/lighting/floor-lamps.html"},
    {"label": "Table Lamps",        "url": "https://www.heals.com/lighting/table-lamps.html"},
    {"label": "Wall Lights",        "url": "https://www.heals.com/lighting/wall-lights.html"},
    # ── Rugs & Soft Furnishings ───────────────────────────────────────────────
    {"label": "Rugs",               "url": "https://www.heals.com/rugs.html"},
    {"label": "Cushions",           "url": "https://www.heals.com/cushions.html"},
    {"label": "Throws",             "url": "https://www.heals.com/throws.html"},
    # ── Brands ────────────────────────────────────────────────────────────────
    {"label": "Ercol",              "url": "https://www.heals.com/brand/ercol.html"},
    {"label": "Vitra",              "url": "https://www.heals.com/brand/vitra.html"},
    {"label": "Tom Dixon",          "url": "https://www.heals.com/brand/tom-dixon.html"},
    {"label": "HAY",                "url": "https://www.heals.com/brand/hay.html"},
    {"label": "Muuto",              "url": "https://www.heals.com/brand/muuto.html"},
    {"label": "Fritz Hansen",       "url": "https://www.heals.com/brand/fritz-hansen.html"},
    {"label": "Carl Hansen",        "url": "https://www.heals.com/brand/carl-hansen-son.html"},
    {"label": "Moooi",              "url": "https://www.heals.com/brand/moooi.html"},
    {"label": "Flos",               "url": "https://www.heals.com/brand/flos.html"},
    # ── Sale & New In ─────────────────────────────────────────────────────────
    {"label": "New In",             "url": "https://www.heals.com/new-in.html"},
    {"label": "Sale",               "url": "https://www.heals.com/sale.html"},
]

# ── Competitor review ratings — via Google search snippets ────────────────────
# Searching "{site} trustpilot rating" returns a rich snippet with the score.
# This avoids Trustpilot's heavy bot-blocking entirely.
REVIEW_SEARCHES = [
    {"site": "Heals",         "query": "heals.com trustpilot rating site:trustpilot.com"},
    {"site": "John Lewis",    "query": "johnlewis.com trustpilot rating site:trustpilot.com"},
    {"site": "Lee Longlands", "query": "leelonglands.co.uk trustpilot rating site:trustpilot.com"},
    {"site": "Smiths",        "query": "smithstherink.com trustpilot rating site:trustpilot.com"},
]


# ── Fetch ──────────────────────────────────────────────────────────────────────

def fetch(url, premium=False):
    params = {"api_key": SCRAPERAPI_KEY, "url": url}
    if premium:
        params["premium"] = "true"
    try:
        r = requests.get("http://api.scraperapi.com/", params=params, timeout=120)
        if r.status_code == 200 and len(r.text) > 500:
            return r.text
        print(f"    Bad response {r.status_code}: {r.text[:80]}")
    except requests.RequestException as e:
        print(f"    Fetch error: {e}")
    return None


# ── Heals product extractor ────────────────────────────────────────────────────

def to_float(text):
    if not text: return None
    m = re.search(r"[\d,]+\.?\d*", str(text).replace(",", ""))
    return float(m.group()) if m else None

def _norm(s):
    return re.sub(r'[^a-z0-9]', '', s.lower())

def extract_heals_products(html, label="Unknown"):
    """
    Uses the GA datalayer JSON blobs — same proven method as scraper.py.
    Also pulls URL, was-price, and stock status from the listing HTML.
    """
    soup = BeautifulSoup(html, "html.parser")

    # ── URL lookup from listing <a> tags ──────────────────────────────────────
    url_lookup = {}
    for a in soup.select("a.product-item-link, li.product-item a[href*='.html']"):
        href = a.get("href", "")
        text = a.get_text(strip=True)
        if href and text:
            url_lookup[_norm(text)] = href

    # ── Was-price lookup ──────────────────────────────────────────────────────
    was_lookup = {}
    for item in soup.select("li.product-item, .product-item-info"):
        name_el = item.select_one("a.product-item-link")
        if not name_el:
            continue
        was_el = item.select_one(
            ".old-price .price, [data-price-type='oldPrice'] .price, "
            ".price-box .old-price, .special-price ~ .old-price .price"
        )
        if was_el:
            val = to_float(was_el.get_text())
            if val:
                was_lookup[_norm(name_el.get_text(strip=True))] = val

    # ── Stock status lookup ───────────────────────────────────────────────────
    stock_lookup = {}
    for item in soup.select("li.product-item, .product-item-info"):
        name_el = item.select_one("a.product-item-link")
        if not name_el:
            continue
        oos = item.select_one(
            ".out-of-stock, .stock.unavailable, [class*='out-of-stock'], "
            "[class*='soldout'], .action.tocart[disabled]"
        )
        stock_lookup[_norm(name_el.get_text(strip=True))] = (
            "out_of_stock" if oos else "in_stock"
        )

    # ── Pull from GA datalayer JSON blobs ─────────────────────────────────────
    pattern = r'\{"item_name":[^}]+\}'
    seen, products = set(), []
    for m in re.findall(pattern, html):
        try:    p = json.loads(m + "}")
        except:
            try: p = json.loads(m)
            except: continue

        item_id = p.get("item_id", "")
        if item_id in seen:
            continue
        seen.add(item_id)

        name  = p.get("item_name", "Unknown")
        price = float(p.get("price", 0)) or None
        key   = _norm(name)

        url = url_lookup.get(key)
        if not url:
            slug = re.sub(r'[^a-z0-9\s-]', '', name.lower())
            slug = re.sub(r'\s+', '-', slug.strip())
            url  = f"https://www.heals.com/{slug}.html"

        was_price    = was_lookup.get(key)
        is_on_sale   = bool(was_price and price and was_price > price)
        discount_pct = round((1 - price/was_price)*100, 1) if is_on_sale else None
        stock_status = stock_lookup.get(key, "in_stock")

        # GA category fields give us the Heals taxonomy
        ga_cat = (p.get("item_category4") or p.get("item_category3") or
                  p.get("item_category2") or p.get("item_category") or "")

        products.append({
            "sku":          item_id,
            "name":         name,
            "page_label":   label,          # which page it came from
            "ga_category":  ga_cat,         # Heals' own category name from GA
            "price":        price,
            "was_price":    was_price,
            "is_on_sale":   is_on_sale,
            "discount_pct": discount_pct,
            "stock_status": stock_status,
            "url":          url,
            "scraped_at":   datetime.now().isoformat(),
        })

    return products

def next_page_url(html, base="https://www.heals.com"):
    soup = BeautifulSoup(html, "html.parser")
    nxt = (soup.select_one("a[rel='next']") or
           soup.select_one(".pages-item-next a") or
           soup.select_one("a.next") or
           soup.select_one("li.next a"))
    if not nxt:
        return None
    href = nxt.get("href", "")
    return href if href.startswith("http") else base + href


# ── Reviews via Google search snippet ─────────────────────────────────────────

def fetch_review_via_google(site_name, query):
    """
    Uses ScraperAPI's Google search endpoint to pull the Trustpilot
    rich snippet that appears in search results — star rating + count.
    Much more reliable than scraping Trustpilot directly.
    """
    # ScraperAPI structured Google endpoint
    params = {
        "api_key":    SCRAPERAPI_KEY,
        "engine":     "google",
        "query":      query,
        "country":    "gb",
        "num":        "5",
    }
    try:
        r = requests.get("https://api.scraperapi.com/structured/google/search",
                         params=params, timeout=60)
        if r.status_code != 200:
            return _review_fallback(site_name, query)
        data = r.json()
    except Exception as e:
        print(f"    Google search error: {e}")
        return _review_fallback(site_name, query)

    result = {
        "site":           site_name,
        "overall_rating": None,
        "review_count":   None,
        "source":         "google_snippet",
        "scraped_at":     datetime.now().isoformat(),
    }

    # Look through organic results and rich snippets for rating data
    all_items = (data.get("organic_results") or []) + (data.get("answer_box") and [data["answer_box"]] or [])
    for item in all_items:
        # Rich snippet rating
        rating_val = item.get("rating") or item.get("review_rating")
        if rating_val:
            try:
                result["overall_rating"] = float(str(rating_val).split("/")[0].strip())
            except:
                pass
        # Review count
        reviews_val = item.get("reviews") or item.get("review_count")
        if reviews_val:
            try:
                result["review_count"] = int(str(reviews_val).replace(",", "").split()[0])
            except:
                pass
        if result["overall_rating"]:
            break

    # Fallback: parse the snippet text for "X out of 5" or "X/5"
    if not result["overall_rating"]:
        for item in all_items:
            snippet = item.get("snippet", "") or item.get("description", "")
            m = re.search(r'(\d+\.?\d*)\s*/\s*5|(\d+\.?\d*)\s+out\s+of\s+5', snippet, re.I)
            if m:
                result["overall_rating"] = float(m.group(1) or m.group(2))
            m2 = re.search(r'([\d,]+)\s+reviews?', snippet, re.I)
            if m2:
                result["review_count"] = int(m2.group(1).replace(",",""))
            if result["overall_rating"]:
                break

    return result

def _review_fallback(site_name, query):
    """If Google structured endpoint fails, try fetching the Trustpilot page directly."""
    tp_urls = {
        "Heals":         "https://www.trustpilot.com/review/heals.com",
        "John Lewis":    "https://www.trustpilot.com/review/www.johnlewis.com",
        "Lee Longlands": "https://www.trustpilot.com/review/www.leelonglands.co.uk",
        "Smiths":        "https://www.trustpilot.com/review/www.smithstherink.com",
    }
    result = {"site": site_name, "overall_rating": None, "review_count": None,
              "source": "trustpilot_direct", "scraped_at": datetime.now().isoformat()}
    url = tp_urls.get(site_name)
    if not url:
        return result
    html = fetch(url)
    if not html:
        return result
    # JSON-LD structured data is the most reliable thing on Trustpilot
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, list):
                data = next((d for d in data if "aggregateRating" in d), {})
            agg = data.get("aggregateRating", {})
            if agg.get("ratingValue"):
                result["overall_rating"] = float(agg["ratingValue"])
                result["review_count"]   = int(agg.get("reviewCount", 0) or agg.get("ratingCount", 0))
                return result
        except:
            continue
    # Final fallback: regex on raw HTML
    m = re.search(r'"ratingValue"\s*:\s*"?([\d.]+)"?', html)
    if m:
        result["overall_rating"] = float(m.group(1))
    m2 = re.search(r'"reviewCount"\s*:\s*"?([\d]+)"?', html)
    if m2:
        result["review_count"] = int(m2.group(1))
    return result


# ── Change detection ───────────────────────────────────────────────────────────

def detect_changes(current_products, history):
    prev_by_sku  = {p["sku"]: p for p in history.get("all_products", []) if p.get("sku")}
    prev_by_name = {p["name"].lower(): p for p in history.get("all_products", [])}

    price_changes, stock_changes, new_products, new_sales, ended_sales = [], [], [], [], []

    for p in current_products:
        prev = (prev_by_sku.get(p["sku"]) if p.get("sku") else None) or prev_by_name.get(p["name"].lower())

        if not prev:
            new_products.append(p)
            continue

        # Price change (ignore sub-£1 rounding noise)
        if prev.get("price") and p.get("price") and abs(p["price"] - prev["price"]) >= 1:
            pct = round((p["price"] - prev["price"]) / prev["price"] * 100, 1)
            price_changes.append({
                "name":       p["name"],
                "url":        p["url"],
                "page_label": p.get("page_label",""),
                "prev_price": prev["price"],
                "new_price":  p["price"],
                "change_pct": pct,
                "direction":  "up" if pct > 0 else "down",
            })

        # Stock change
        if prev.get("stock_status") and p["stock_status"] != prev["stock_status"]:
            stock_changes.append({
                "name": p["name"], "url": p["url"],
                "from": prev["stock_status"], "to": p["stock_status"],
            })

        # Sale started / ended
        if p["is_on_sale"] and not prev.get("is_on_sale"):
            new_sales.append(p)
        if not p["is_on_sale"] and prev.get("is_on_sale"):
            ended_sales.append({"name": p["name"], "url": p["url"]})

    return {
        "price_changes": price_changes,
        "stock_changes": stock_changes,
        "new_products":  new_products,
        "new_sales":     new_sales,
        "ended_sales":   ended_sales,
    }


# ── Stats helpers ──────────────────────────────────────────────────────────────

def price_stats(prices):
    if not prices:
        return {}
    ps = sorted(prices)
    n  = len(ps)
    return {
        "count":  n,
        "min":    round(ps[0], 2),
        "max":    round(ps[-1], 2),
        "mean":   round(sum(ps)/n, 2),
        "median": round(ps[n//2], 2),
    }


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "═"*62)
    print("  BARKER & STONEHOUSE — HEALS INTELLIGENCE SCRAPER")
    print("═"*62)

    history = {}
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            history = json.load(f)
        print(f"\n  History: {len(history.get('all_products',[]))} products from last run")
    else:
        print("\n  No history file — this is the baseline run (no change detection yet)")

    # ── Scrape all Heals pages ────────────────────────────────────────────────
    print(f"\n── Scraping {len(HEALS_PAGES)} Heals pages ──")
    raw_products = []   # may have duplicates across pages
    pages_summary = {}

    for cfg in HEALS_PAGES:
        label = cfg["label"]
        url   = cfg["url"]
        print(f"\n  {label}")
        page_num  = 0
        page_total = 0

        while url:
            page_num += 1
            html = fetch(url)
            if not html:
                print(f"    ✗ Could not fetch page {page_num}")
                break
            prods = extract_heals_products(html, label=label)
            if not prods:
                print(f"    ✗ No products on page {page_num}")
                break
            raw_products.extend(prods)
            page_total += len(prods)
            print(f"    ✓ Page {page_num}: {len(prods)} products")
            url = next_page_url(html)
            if url:
                time.sleep(0.4)   # polite delay

        pages_summary[label] = page_total

    # De-duplicate by SKU (same product appears on multiple category/brand pages)
    seen_skus, seen_names, deduped = set(), set(), []
    for p in raw_products:
        key = p["sku"] if p["sku"] else None
        name_key = p["name"].lower()
        if key and key in seen_skus:
            continue
        if not key and name_key in seen_names:
            continue
        if key:
            seen_skus.add(key)
        seen_names.add(name_key)
        deduped.append(p)

    all_products = deduped
    print(f"\n  Raw total: {len(raw_products)} | After dedup: {len(all_products)} unique products")

    # ── Reviews ───────────────────────────────────────────────────────────────
    print("\n── Fetching competitor review ratings ──")
    reviews = []
    for rs in REVIEW_SEARCHES:
        print(f"  {rs['site']}...")
        result = fetch_review_via_google(rs["site"], rs["query"])
        reviews.append(result)
        rating = result.get("overall_rating")
        count  = result.get("review_count")
        if rating:
            print(f"    ✓ {rating}/5 ({count or '?'} reviews) via {result['source']}")
        else:
            print(f"    ✗ Could not retrieve rating")
        time.sleep(1)

    # ── Change detection ──────────────────────────────────────────────────────
    print("\n── Detecting changes ──")
    changes = detect_changes(all_products, history)
    print(f"  Price changes:  {len(changes['price_changes'])}")
    print(f"  Stock changes:  {len(changes['stock_changes'])}")
    print(f"  New products:   {len(changes['new_products'])}")
    print(f"  New sales:      {len(changes['new_sales'])}")
    print(f"  Ended sales:    {len(changes['ended_sales'])}")

    # ── Category price stats ──────────────────────────────────────────────────
    # Group by ga_category (Heals' own taxonomy from GA datalayer)
    cat_prices = {}
    for p in all_products:
        cat = p.get("ga_category") or p.get("page_label") or "Other"
        if cat not in cat_prices:
            cat_prices[cat] = []
        if p.get("price"):
            cat_prices[cat].append(p["price"])

    category_stats = {
        cat: price_stats(prices)
        for cat, prices in cat_prices.items()
        if len(prices) >= 2
    }

    # ── Build output ──────────────────────────────────────────────────────────
    on_sale   = [p for p in all_products if p["is_on_sale"]]
    out_stock = [p for p in all_products if p["stock_status"] == "out_of_stock"]

    output = {
        "scraped_at": datetime.now().isoformat(),
        "competitor": "Heals",
        "summary": {
            "total_products": len(all_products),
            "pages_scraped":  len(HEALS_PAGES),
            "on_sale":        len(on_sale),
            "out_of_stock":   len(out_stock),
            "new_products":   len(changes["new_products"]),
            "price_changes":  len(changes["price_changes"]),
            "stock_changes":  len(changes["stock_changes"]),
            "new_sales":      len(changes["new_sales"]),
        },
        "pages_summary":  pages_summary,
        "all_products":   all_products,
        "on_sale":        on_sale,
        "out_of_stock":   out_stock,
        "changes":        changes,
        "reviews":        reviews,
        "category_stats": category_stats,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # Save as new history baseline
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump({"all_products": all_products, "run_at": datetime.now().isoformat()}, f)

    print(f"\n{'='*62}")
    print(f"  DONE — {len(all_products)} products saved to {OUTPUT_FILE}")
    print(f"  On sale: {len(on_sale)}  |  Out of stock: {len(out_stock)}")
    print(f"\n  Upload {OUTPUT_FILE} to GitHub to update the dashboard.")
    print(f"{'='*62}\n")

if __name__ == "__main__":
    main()
