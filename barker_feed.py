"""
╔══════════════════════════════════════════════════════════════════╗
║  Barker & Stonehouse — Own Product Feed Processor               ║
║  Converts the B&S Facebook product feed into the intelligence   ║
║  JSON format so your own prices appear in the dashboard         ║
╠══════════════════════════════════════════════════════════════════╣
║  Usage:  py barker_feed.py                                      ║
║  Output: barker_intelligence.json → upload to GitHub            ║
╚══════════════════════════════════════════════════════════════════╝

The feed is fetched automatically from the B&S feed URL.
No manual download needed — just run py barker_feed.py
"""

import requests, gzip, io, csv, re, json, os
from datetime import datetime

# ── Config ─────────────────────────────────────────────────────────────────────
FEED_URL    = "https://sftpgo.feedonomics.com/ftp/fdx_fc2e94f866798/barker_and_stonehouse_facebook_v2.csv.gz"
OUTPUT_FILE = "barker_intelligence.json"
HISTORY_FILE= "barker_history.json"

# Only skip truly blank rows — ALL branded products including own-label are included
EXCLUDE_BRANDS = {''}


# ── Helpers ────────────────────────────────────────────────────────────────────

def to_float(text):
    if not text: return None
    m = re.search(r'[\d,]+\.?\d*', str(text).replace(',','').replace(' GBP',''))
    return float(m.group()) if m else None

def normalise_brand(brand):
    b = brand.strip()
    if b.lower() in {'barker and stonehouse', 'barker & stonehouse'}:
        return 'Barker & Stonehouse Own Brand'
    if b.startswith('Tetrad'):
        return 'Tetrad'
    return b if b else 'Unknown'

def barker_delivery(name):
    n = name.lower()
    if any(w in n for w in ['sofa','wardrobe','sideboard','bookcase','dining table','extending table']):
        return 99.0
    elif any(w in n for w in ['armchair','chair','coffee table','tv unit','chest','cabinet','recliner']):
        return 49.0
    elif any(w in n for w in ['bedside','side table','lamp table','stool','bar stool']):
        return 15.0
    elif 'mattress' in n:
        return 29.0
    else:
        return 69.0

def map_to_page_label(product_type):
    """Map product_type from feed to a page_label matching the dashboard folders."""
    pt = product_type.lower()
    if 'sofa' in pt:                                    return 'Sofas'
    if 'footstool' in pt:                               return 'Footstools'
    if 'armchair' in pt:                                return 'Armchairs'
    if 'chair' in pt and 'dining' in pt:                return 'Dining Chairs'
    if 'chair' in pt:                                   return 'Armchairs'
    if 'dining table' in pt or 'extending' in pt:       return 'Dining Tables'
    if 'coffee table' in pt:                            return 'Coffee Tables'
    if 'side table' in pt or 'lamp table' in pt:        return 'Side Tables'
    if 'bedside' in pt:                                 return 'Bedside Tables'
    if 'bed' in pt and 'mattress' not in pt:            return 'All Beds'
    if 'mattress' in pt:                                return 'All Mattresses'
    if 'wardrobe' in pt:                                return 'Wardrobes'
    if 'chest' in pt or 'drawer' in pt:                 return 'Chest of Drawers'
    if 'sideboard' in pt or 'storage' in pt:            return 'Sideboards'
    if 'bookcase' in pt or 'shelf' in pt or 'shelv' in pt: return 'Bookcases'
    if 'tv' in pt or 'media' in pt:                     return 'TV Stands'
    if 'lighting' in pt or 'lamp' in pt:                return 'Lighting'
    if 'rug' in pt:                                     return 'Rugs'
    if 'cushion' in pt:                                 return 'Cushions'
    if 'desk' in pt:                                    return 'Office Desks'
    if 'dressing table' in pt:                          return 'Dressing Tables'
    if 'console' in pt:                                 return 'Console Tables'
    if 'dining' in pt:                                  return 'Dining Tables'
    return 'Other'


# ── Change detection ───────────────────────────────────────────────────────────

def detect_changes(current_products, history):
    prev_by_sku  = {p["sku"]: p for p in history.get("all_products", []) if p.get("sku")}
    prev_by_name = {p["name"].lower(): p for p in history.get("all_products", [])}
    price_changes, stock_changes, new_products, new_sales, ended_sales = [], [], [], [], []
    for p in current_products:
        prev = prev_by_sku.get(p["sku"]) or prev_by_name.get(p["name"].lower())
        if not prev:
            new_products.append(p); continue
        if prev.get("price") and p.get("price") and abs(p["price"] - prev["price"]) >= 1:
            pct = round((p["price"] - prev["price"]) / prev["price"] * 100, 1)
            price_changes.append({"name": p["name"], "url": p["url"],
                "page_label": p.get("page_label",""), "prev_price": prev["price"],
                "new_price": p["price"], "change_pct": pct,
                "direction": "up" if pct > 0 else "down"})
        if prev.get("stock_status") and p["stock_status"] != prev["stock_status"]:
            stock_changes.append({"name": p["name"], "url": p["url"],
                "from": prev["stock_status"], "to": p["stock_status"]})
        if p["is_on_sale"] and not prev.get("is_on_sale"):
            new_sales.append(p)
        if not p["is_on_sale"] and prev.get("is_on_sale"):
            ended_sales.append({"name": p["name"], "url": p["url"]})
    return {"price_changes": price_changes, "stock_changes": stock_changes,
            "new_products": new_products, "new_sales": new_sales, "ended_sales": ended_sales}


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "="*62)
    print("  BARKER & STONEHOUSE — PRODUCT FEED PROCESSOR")
    print("="*62)

    # Load history
    history = {}
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            history = json.load(f)
        print(f"\n  History: {len(history.get('all_products',[]))} products from last run")
    else:
        print("\n  No history — this is the baseline run")

    # Fetch feed
    print(f"\n-- Fetching product feed --")
    try:
        r = requests.get(FEED_URL, timeout=60)
        r.raise_for_status()
        print(f"  Downloaded: {len(r.content):,} bytes")
    except requests.RequestException as e:
        print(f"  x Feed fetch failed: {e}")
        return

    with gzip.open(io.BytesIO(r.content), 'rt', encoding='utf-8') as f:
        lines = f.readlines()

    csv_content = "".join(lines[2:])  # skip 2 comment header lines
    reader = csv.DictReader(io.StringIO(csv_content))
    all_rows = [row for row in reader
                if row.get('title','').strip()]  # skip blank rows only
    print(f"  Rows after brand filter: {len(all_rows)}")

    # Process & deduplicate
    seen = {}
    for row in all_rows:
        brand  = row.get('brand','').strip()
        brand  = 'Tetrad' if brand.startswith('Tetrad') else brand
        title  = re.sub(r'\s*\|\s*Barker.*$', '', row['title'], flags=re.I).strip()
        price  = to_float(row['price'])
        sale   = to_float(row['sale_price'])
        actual = sale if sale and sale > 0 and sale != price else price
        was    = price if sale and sale > 0 and sale != price else None
        avail  = row['availability']
        url    = row['link']
        sku    = row['id']
        pt     = row.get('product_type', '')

        product = {
            "sku":          sku,
            "name":         title,
            "page_label":   map_to_page_label(pt),
            "brand":        brand,
            "price":        actual,
            "was_price":    was,
            "is_on_sale":   bool(was and actual and was > actual),
            "discount_pct": round((1-actual/was)*100, 1) if was and actual and was > actual else None,
            "stock_status": "in_stock" if avail == "in stock" else "out_of_stock",
            "delivery_cost": barker_delivery(title),
            "url":          url,
            "scraped_at":   datetime.now().isoformat(),
        }

        key = title.lower()
        if key not in seen:
            seen[key] = product
        else:
            existing = seen[key]
            # Prefer in-stock, then lower price
            if avail == "in stock" and existing["stock_status"] != "in_stock":
                seen[key] = product
            elif actual and existing["price"] and actual < existing["price"]:
                seen[key] = product

    products = list(seen.values())

    # Change detection
    print("\n-- Detecting changes --")
    changes = detect_changes(products, history)
    print(f"  Price changes: {len(changes['price_changes'])}")
    print(f"  Stock changes: {len(changes['stock_changes'])}")
    print(f"  New products:  {len(changes['new_products'])}")
    print(f"  Price drops:   {sum(1 for c in changes['price_changes'] if c['direction']=='down')}")

    on_sale   = [p for p in products if p["is_on_sale"]]
    out_stock = [p for p in products if p["stock_status"] == "out_of_stock"]

    output = {
        "scraped_at":  datetime.now().isoformat(),
        "competitor":  "Barker & Stonehouse",
        "is_own_data": True,  # flag so dashboard can style differently
        "summary": {
            "total_products": len(products),
            "pages_scraped":  1,
            "pages_failed":   0,
            "on_sale":        len(on_sale),
            "out_of_stock":   len(out_stock),
            "new_products":   len(changes["new_products"]),
            "price_changes":  len(changes["price_changes"]),
            "stock_changes":  len(changes["stock_changes"]),
            "new_sales":      len(changes["new_sales"]),
        },
        "pages_summary":  {"Product Feed": len(products)},
        "failed_urls":    [],
        "all_products":   products,
        "on_sale":        on_sale,
        "out_of_stock":   out_stock,
        "changes":        changes,
        "category_stats": {},
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump({"all_products": products, "run_at": datetime.now().isoformat()}, f)

    print(f"\n{'='*62}")
    print(f"  DONE — {len(products)} products saved to {OUTPUT_FILE}")
    print(f"  In stock: {len(products)-len(out_stock)} | Out of stock: {len(out_stock)}")
    print(f"  On sale:  {len(on_sale)}")
    print(f"\n  Upload {OUTPUT_FILE} to GitHub to update the dashboard.")
    print(f"{'='*62}\n")

if __name__ == "__main__":
    main()
