"""
╔══════════════════════════════════════════════════════════════════╗
║  Barker & Stonehouse — Heals Intelligence Scraper               ║
║  Tracks: prices, stock, new products, sales, reviews, delivery  ║
╠══════════════════════════════════════════════════════════════════╣
║  Usage:  py heals_intelligence.py                               ║
║  Output: heals_intelligence.json → upload to GitHub             ║
╚══════════════════════════════════════════════════════════════════╝
"""

import requests, json, re, os, time
from bs4 import BeautifulSoup
from datetime import datetime

# ── Config ─────────────────────────────────────────────────────────────────────

SCRAPERAPI_KEY  = "d3200b71ef63fb84b501a308f91fb1a4"
OUTPUT_FILE     = "heals_intelligence.json"
HISTORY_FILE    = "heals_history.json"

HEALS_PAGES = [
    # Each brand/category page to scrape — add more here as needed
    {"brand": "Ercol",      "url": "https://www.heals.com/brand/ercol.html",      "premium": False},
    {"brand": "Vitra",      "url": "https://www.heals.com/brand/vitra.html",       "premium": False},
    {"brand": "Tom Dixon",  "url": "https://www.heals.com/brand/tom-dixon.html",   "premium": False},
    {"brand": "New In",     "url": "https://www.heals.com/new-in.html",            "premium": False},
    {"brand": "Sofas",      "url": "https://www.heals.com/sofas.html",             "premium": False},
    {"brand": "Dining",     "url": "https://www.heals.com/dining.html",            "premium": False},
    {"brand": "Bedroom",    "url": "https://www.heals.com/bedroom.html",           "premium": False},
]

# Trustpilot pages for competitor review ratings
TRUSTPILOT_PAGES = [
    {"site": "Heals",        "url": "https://www.trustpilot.com/review/heals.com",                   "premium": False},
    {"site": "John Lewis",   "url": "https://www.trustpilot.com/review/www.johnlewis.com",            "premium": False},
    {"site": "Lee Longlands","url": "https://www.trustpilot.com/review/www.leelonglands.co.uk",       "premium": False},
    {"site": "Smiths",       "url": "https://www.trustpilot.com/review/www.smithstherink.com",        "premium": False},
]


# ── Fetch (identical to working scraper.py) ────────────────────────────────────

def fetch(url, premium=False):
    params = {"api_key": SCRAPERAPI_KEY, "url": url}
    if premium:
        params["premium"] = "true"
    try:
        r = requests.get("http://api.scraperapi.com/", params=params, timeout=120)
        if r.status_code == 200 and len(r.text) > 1000:
            return r.text
        print(f"    Bad response {r.status_code}: {r.text[:80]}")
    except requests.RequestException as e:
        print(f"    Fetch error: {e}")
    return None


# ── Heals product extractor (identical to working scraper.py) ─────────────────

def to_float(text):
    if not text: return None
    m = re.search(r"[\d,]+\.?\d*", str(text).replace(",", ""))
    return float(m.group()) if m else None

def _norm(s):
    return re.sub(r'[^a-z0-9]', '', s.lower())

def extract_heals_products(html, brand="Unknown"):
    """Extract products from Heals page using GA JSON blobs — the proven method."""
    soup = BeautifulSoup(html, "html.parser")

    # Build name → URL lookup from listing <a> tags
    url_lookup = {}
    for a in soup.select("a.product-item-link, li.product-item a[href*='.html']"):
        href = a.get("href", "")
        text = a.get_text(strip=True)
        if href and text:
            url_lookup[_norm(text)] = href

    # Also detect "was price" from listing HTML
    was_lookup = {}
    for item in soup.select("li.product-item, .product-item-info"):
        name_el = item.select_one("a.product-item-link")
        if not name_el:
            continue
        name = name_el.get_text(strip=True)
        # Magento old/special price selectors
        was_el = item.select_one(
            ".old-price .price, .price-box .old-price, "
            "[data-price-type='oldPrice'] .price, .special-price ~ .old-price .price"
        )
        if was_el:
            was_lookup[_norm(name)] = to_float(was_el.get_text())

    # Stock status from listing
    stock_lookup = {}
    for item in soup.select("li.product-item, .product-item-info"):
        name_el = item.select_one("a.product-item-link")
        if not name_el:
            continue
        name = name_el.get_text(strip=True)
        oos = item.select_one(
            ".out-of-stock, .stock.unavailable, [class*='out-of-stock'], "
            "[class*='soldout'], .action.tocart[disabled]"
        )
        stock_lookup[_norm(name)] = "out_of_stock" if oos else "in_stock"

    # Pull products from GA datalayer JSON blobs
    pattern = r'\{"item_name":[^}]+\}'
    seen, products = set(), []
    for m in re.findall(pattern, html):
        try:    p = json.loads(m + "}")
        except:
            try: p = json.loads(m)
            except: continue

        item_id = p.get("item_id","")
        if item_id in seen:
            continue
        seen.add(item_id)

        name  = p.get("item_name", "Unknown")
        price = float(p.get("price", 0)) or None
        key   = _norm(name)

        # URL
        url = url_lookup.get(key)
        if not url:
            slug = re.sub(r'[^a-z0-9\s-]', '', name.lower())
            slug = re.sub(r'\s+', '-', slug.strip())
            url  = f"https://www.heals.com/{slug}.html"

        was_price = was_lookup.get(key)
        is_on_sale = bool(was_price and price and was_price > price)
        discount_pct = round((1 - price/was_price)*100, 1) if is_on_sale else None
        stock_status = stock_lookup.get(key, "in_stock")

        category = p.get("item_category4") or p.get("item_category3") or p.get("item_category2") or p.get("item_category","")

        products.append({
            "sku":          item_id,
            "name":         name,
            "brand":        brand,
            "price":        price,
            "was_price":    was_price,
            "is_on_sale":   is_on_sale,
            "discount_pct": discount_pct,
            "stock_status": stock_status,
            "url":          url,
            "category":     category,
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


# ── Trustpilot review scraper ──────────────────────────────────────────────────

def scrape_trustpilot(html, site_name):
    soup = BeautifulSoup(html, "html.parser")
    result = {
        "site":           site_name,
        "overall_rating": None,
        "review_count":   None,
        "rating_label":   None,
        "scraped_at":     datetime.now().isoformat(),
    }

    # Overall rating score
    rating_el = soup.select_one(
        "[data-rating-typography], [class*='ratingValue'], "
        "span[class*='display_largeTextRating'], p[class*='typography_largeBody']"
    )
    if rating_el:
        result["overall_rating"] = to_float(rating_el.get_text())

    # Try JSON-LD structured data (most reliable)
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
            if isinstance(data, list):
                data = next((d for d in data if d.get("@type") == "Organization"), {})
            agg = data.get("aggregateRating", {})
            if agg.get("ratingValue"):
                result["overall_rating"] = float(agg["ratingValue"])
                result["review_count"]   = int(agg.get("reviewCount", 0)) or int(agg.get("ratingCount", 0))
                break
        except:
            continue

    # Rating label (Excellent / Great / etc.)
    label_el = soup.select_one("[class*='ratingLabel'], [class*='rating_label'], h2[class*='title']")
    if label_el:
        txt = label_el.get_text(strip=True)
        if any(w in txt for w in ["Excellent","Great","Good","Average","Bad"]):
            result["rating_label"] = txt[:30]

    # Review count fallback
    if not result["review_count"]:
        count_el = soup.select_one("[class*='reviewsCount'], [class*='review-count']")
        if count_el:
            result["review_count"] = to_float(count_el.get_text())

    return result


# ── Change detection ───────────────────────────────────────────────────────────

def detect_changes(current_products, history):
    prev_by_sku = {p["sku"]: p for p in history.get("all_products", [])}
    prev_names  = {p["name"].lower(): p for p in history.get("all_products", [])}

    price_changes   = []
    stock_changes   = []
    new_products    = []
    new_sales       = []
    ended_sales     = []

    for p in current_products:
        key  = p["sku"] or p["name"].lower()
        prev = prev_by_sku.get(p["sku"]) or prev_names.get(p["name"].lower())

        if not prev:
            new_products.append(p)
            continue

        # Price change
        if prev.get("price") and p.get("price") and abs(p["price"] - prev["price"]) >= 1:
            pct = round((p["price"] - prev["price"]) / prev["price"] * 100, 1)
            price_changes.append({
                "name":       p["name"],
                "url":        p["url"],
                "prev_price": prev["price"],
                "new_price":  p["price"],
                "change_pct": pct,
                "direction":  "up" if pct > 0 else "down",
            })

        # Stock change
        if prev.get("stock_status") and p["stock_status"] != prev["stock_status"]:
            stock_changes.append({
                "name":  p["name"],
                "url":   p["url"],
                "from":  prev["stock_status"],
                "to":    p["stock_status"],
            })

        # Sale started
        if p["is_on_sale"] and not prev.get("is_on_sale"):
            new_sales.append(p)

        # Sale ended
        if not p["is_on_sale"] and prev.get("is_on_sale"):
            ended_sales.append({"name": p["name"], "url": p["url"]})

    return {
        "price_changes":  price_changes,
        "stock_changes":  stock_changes,
        "new_products":   new_products,
        "new_sales":      new_sales,
        "ended_sales":    ended_sales,
    }


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "═"*60)
    print("  BARKER & STONEHOUSE — HEALS INTELLIGENCE SCRAPER")
    print("═"*60)

    # Load history for change detection
    history = {}
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            history = json.load(f)
        print(f"\n  History loaded: {len(history.get('all_products',[]))} products from last run")
    else:
        print("\n  No history file — this will be the baseline run")

    # ── Scrape Heals pages ────────────────────────────────────────────────────
    print("\n── Scraping Heals pages ──")
    all_products = []
    products_by_brand = {}

    for page_cfg in HEALS_PAGES:
        brand = page_cfg["brand"]
        url   = page_cfg["url"]
        base  = "https://www.heals.com"
        print(f"\n  {brand} ({url})")

        page_num    = 0
        brand_prods = []

        while url:
            page_num += 1
            html = fetch(url, premium=page_cfg["premium"])
            if not html:
                print(f"    ✗ Could not fetch page {page_num}")
                break
            prods = extract_heals_products(html, brand=brand)
            if not prods:
                print(f"    ✗ No products found on page {page_num}")
                break
            brand_prods.extend(prods)
            print(f"    ✓ Page {page_num}: {len(prods)} products")
            url = next_page_url(html, base)
            if url:
                time.sleep(0.5)

        all_products.extend(brand_prods)
        products_by_brand[brand] = brand_prods
        print(f"    Total for {brand}: {len(brand_prods)}")

    # De-duplicate by SKU across pages (e.g. a product appearing in both Ercol + New In)
    seen_skus = set()
    deduped = []
    for p in all_products:
        key = p["sku"] or p["name"].lower()
        if key not in seen_skus:
            seen_skus.add(key)
            deduped.append(p)
    all_products = deduped
    print(f"\n  Total unique products: {len(all_products)}")

    # ── Scrape Trustpilot ratings ─────────────────────────────────────────────
    print("\n── Scraping Trustpilot ratings ──")
    reviews = []
    for tp in TRUSTPILOT_PAGES:
        print(f"  {tp['site']}...")
        html = fetch(tp["url"], premium=tp["premium"])
        if not html:
            print(f"    ✗ Could not fetch")
            reviews.append({"site": tp["site"], "overall_rating": None, "review_count": None})
            continue
        result = scrape_trustpilot(html, tp["site"])
        reviews.append(result)
        print(f"    ✓ Rating: {result['overall_rating'] or '?'} | Reviews: {result['review_count'] or '?'}")

    # ── Detect changes ────────────────────────────────────────────────────────
    print("\n── Detecting changes since last run ──")
    changes = detect_changes(all_products, history)

    def _print_changes(label, items, fmt):
        if items:
            print(f"  {label}: {len(items)}")
            for item in items[:5]:
                print(f"    • {fmt(item)}")
            if len(items) > 5:
                print(f"    ... and {len(items)-5} more")
        else:
            print(f"  {label}: none")

    _print_changes("Price changes",  changes["price_changes"],
                   lambda x: f"{x['name'][:50]} £{x['prev_price']} → £{x['new_price']} ({x['change_pct']:+}%)")
    _print_changes("Stock changes",  changes["stock_changes"],
                   lambda x: f"{x['name'][:50]} {x['from']} → {x['to']}")
    _print_changes("New products",   changes["new_products"],
                   lambda x: f"{x['name'][:50]} £{x['price']}")
    _print_changes("New sales",      changes["new_sales"],
                   lambda x: f"{x['name'][:50]} {x['discount_pct']}% off")
    _print_changes("Ended sales",    changes["ended_sales"],
                   lambda x: x['name'][:50])

    # ── Category price stats ──────────────────────────────────────────────────
    category_stats = {}
    for p in all_products:
        cat = p.get("category") or p.get("brand") or "Unknown"
        if cat not in category_stats:
            category_stats[cat] = []
        if p.get("price"):
            category_stats[cat].append(p["price"])

    cat_summary = {}
    for cat, prices in category_stats.items():
        if not prices:
            continue
        prices_sorted = sorted(prices)
        n = len(prices_sorted)
        cat_summary[cat] = {
            "count":  n,
            "min":    round(min(prices_sorted), 2),
            "max":    round(max(prices_sorted), 2),
            "mean":   round(sum(prices_sorted)/n, 2),
            "median": round(prices_sorted[n//2], 2),
        }

    # ── Build output ──────────────────────────────────────────────────────────
    on_sale   = [p for p in all_products if p["is_on_sale"]]
    out_stock = [p for p in all_products if p["stock_status"] == "out_of_stock"]

    output = {
        "scraped_at":    datetime.now().isoformat(),
        "competitor":    "Heals",
        "summary": {
            "total_products":     len(all_products),
            "on_sale":            len(on_sale),
            "out_of_stock":       len(out_stock),
            "new_products":       len(changes["new_products"]),
            "price_changes":      len(changes["price_changes"]),
            "stock_changes":      len(changes["stock_changes"]),
            "new_sales":          len(changes["new_sales"]),
        },
        "all_products":     all_products,
        "on_sale":          on_sale,
        "out_of_stock":     out_stock,
        "changes":          changes,
        "reviews":          reviews,
        "category_stats":   cat_summary,
        "products_by_brand": {brand: len(prods) for brand, prods in products_by_brand.items()},
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # Save as new history baseline
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump({"all_products": all_products, "run_at": datetime.now().isoformat()}, f)

    print(f"\n{'═'*60}")
    print(f"✓ DONE — {len(all_products)} products saved to {OUTPUT_FILE}")
    print(f"  On sale:      {len(on_sale)}")
    print(f"  Out of stock: {len(out_stock)}")
    print(f"  Upload {OUTPUT_FILE} to GitHub to update the dashboard.")
    print(f"{'═'*60}\n")

if __name__ == "__main__":
    main()
