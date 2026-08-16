"""Products, variants, search and filtering."""
import config
import db
from services import inventory


def _attach_stock(variants, branch_id=None):
    branch_id = branch_id or config.BRANCH_ID
    if not variants:
        return variants
    ids = [v["id"] for v in variants]
    placeholders = ",".join("?" for _ in ids)
    rows = {
        r["variant_id"]: r
        for r in db.query(
            f"""SELECT variant_id, on_hand, reserved, updated_at FROM inventory
                WHERE branch_id = ? AND variant_id IN ({placeholders})""",
            (branch_id, *ids),
        )
    }
    for v in variants:
        v["stock"] = inventory.describe(rows.get(v["id"], {}))
    return variants


def variants_for(product_id, branch_id=None):
    rows = db.query(
        "SELECT * FROM product_variants WHERE product_id = ? ORDER BY label",
        (product_id,),
    )
    return _attach_stock(rows, branch_id)


def _roll_up(product, variants):
    """A product's headline stock is the best any of its variants can offer.

    Showing "out of stock" because one size is gone would be wrong, so the
    strongest variant sets the badge and the detail page breaks it down.
    """
    product["variants"] = variants
    available = sum(v["stock"]["available"] for v in variants)
    prices = [v["price"] for v in variants] or [0]
    freshest = min(
        (v["stock"]["freshness"] for v in variants),
        key=lambda f: f["minutes"] if f["minutes"] is not None else 10**9,
        default={"level": "unknown", "label": "Never updated", "minutes": None, "stale": True},
    )
    product["available"] = available
    product["status"] = inventory.stock_status(available)
    product["price_from"] = min(prices)
    product["price_to"] = max(prices)
    product["freshness"] = freshest
    return product


def get_product(product_id, branch_id=None):
    product = db.query_one(
        "SELECT * FROM products WHERE id = ? AND store_id = ?", (product_id, config.STORE_ID))
    if not product:
        return None
    return _roll_up(product, variants_for(product_id, branch_id))


def list_products(search="", category=None, status=None, sort="popular", branch_id=None):
    sql = "SELECT * FROM products WHERE store_id = ?"
    params = [config.STORE_ID]

    if search:
        # Split the query and require every word to land somewhere on the
        # product. "Nike shoes" only works this way: "nike" hits the brand and
        # "shoes" hits the tags, and neither field contains the whole phrase.
        for token in search.strip().lower().split():
            like = f"%{token}%"
            sql += """ AND (lower(name) LIKE ? OR lower(brand) LIKE ?
                            OR lower(category) LIKE ? OR lower(description) LIKE ?
                            OR lower(tags) LIKE ?
                            OR id IN (SELECT product_id FROM product_variants
                                      WHERE lower(sku) LIKE ? OR lower(label) LIKE ?
                                         OR barcode LIKE ?))"""
            params += [like] * 8

    if category and category != "all":
        sql += " AND lower(category) = ?"
        params.append(category.strip().lower())

    products = db.query(sql, tuple(params))
    for p in products:
        _roll_up(p, variants_for(p["id"], branch_id))

    if status and status != "all":
        products = [p for p in products if p["status"] == status]

    keys = {
        "popular": lambda p: (-p["popularity"], p["name"]),
        "price_low": lambda p: p["price_from"],
        "price_high": lambda p: -p["price_from"],
        "rating": lambda p: (-p["rating"], p["name"]),
        "name": lambda p: p["name"].lower(),
    }
    return sorted(products, key=keys.get(sort, keys["popular"]))


def categories():
    return [
        r["category"]
        for r in db.query(
            """SELECT DISTINCT category FROM products
               WHERE store_id = ? AND category != '' ORDER BY category""",
            (config.STORE_ID,),
        )
    ]


def get_variant(variant_id, branch_id=None):
    row = db.query_one(
        """SELECT v.*, p.name AS product_name, p.brand, p.image_url, p.category
           FROM product_variants v JOIN products p ON p.id = v.product_id
           WHERE v.id = ?""",
        (variant_id,),
    )
    if not row:
        return None
    return _attach_stock([row], branch_id)[0]


def find_by_code(code, branch_id=None):
    """Resolve a scanned barcode or a typed SKU to one variant."""
    code = (code or "").strip()
    if not code:
        return None
    row = db.query_one(
        """SELECT v.*, p.name AS product_name, p.brand, p.image_url, p.category
           FROM product_variants v JOIN products p ON p.id = v.product_id
           WHERE v.barcode = ? OR upper(v.sku) = upper(?)""",
        (code, code),
    )
    if not row:
        return None
    return _attach_stock([row], branch_id)[0]


def check_many(names, branch_id=None):
    """The 'find everything' demo: can this store cover the whole list?

    A rehearsal for multi-store search on the parent platform, where the same
    question gets asked of every branch at once.
    """
    results = []
    for raw in names:
        term = (raw or "").strip()
        if not term:
            continue
        matches = list_products(search=term, branch_id=branch_id)
        in_stock = [m for m in matches if m["available"] > 0]
        best = in_stock[0] if in_stock else (matches[0] if matches else None)
        results.append({
            "term": term,
            "found": bool(matches),
            "available": bool(in_stock),
            "product": best,
        })
    return {
        "items": results,
        "all_available": bool(results) and all(r["available"] for r in results),
        "available_count": sum(1 for r in results if r["available"]),
        "total": len(results),
    }
