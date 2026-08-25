"""Products, variants, search and filtering."""
import config
import db
from services import audit, inventory
from services.security import require


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
        # product. "Amul ghee" only works this way: "amul" hits the brand and
        # "ghee" hits the name, and neither field contains the whole phrase.
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


# -- local catalogue editing --------------------------------------------------
#
# Distinct from the parent-platform push in services/parent_sync.py: these
# functions are for a person at this store adding or fixing a product by
# hand, so they carry no parent_ref and are gated on a staff permission
# rather than the parent token. A product created here and a product pushed
# from head office are indistinguishable rows afterwards -- there is nothing
# that marks one as "local" -- so a later push that happens to reuse the same
# parent_ref would still update it correctly.

_PRODUCT_FIELDS = ("name", "brand", "category", "description", "tags", "image_url")


def create_product(actor, *, name, brand="", category="", description="", tags="", image_url=""):
    require(actor, "product.create")
    name = (name or "").strip()
    if not name:
        raise ValueError("A product needs a name.")
    _rowcount, product_id = db.execute(
        """INSERT INTO products (store_id, name, brand, category, description, tags, image_url)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (config.STORE_ID, name, brand or "", category or "", description or "", tags or "", image_url or ""),
    )
    audit.record(actor, "product.create", "product", product_id, {"name": name})
    return get_product(product_id)


def update_product(actor, product_id, **fields):
    """Patch the fields given; anything omitted keeps its current value."""
    require(actor, "product.edit")
    existing = db.query_one(
        "SELECT * FROM products WHERE id = ? AND store_id = ?", (product_id, config.STORE_ID)
    )
    if not existing:
        raise ValueError("No such product.")
    merged = {key: fields.get(key, existing[key]) or "" for key in _PRODUCT_FIELDS}
    merged["name"] = merged["name"].strip()
    if not merged["name"]:
        raise ValueError("A product needs a name.")
    db.execute(
        "UPDATE products SET name=?, brand=?, category=?, description=?, tags=?, image_url=? WHERE id=?",
        (*merged.values(), product_id),
    )
    audit.record(actor, "product.edit", "product", product_id, {"changed": sorted(fields)})
    return get_product(product_id)


def delete_product(actor, product_id):
    """Removes every variant with it (ON DELETE CASCADE) -- a product with no
    variants left dangling would be unreachable but not gone."""
    require(actor, "product.delete")
    existing = db.query_one(
        "SELECT id FROM products WHERE id = ? AND store_id = ?", (product_id, config.STORE_ID)
    )
    if not existing:
        raise ValueError("No such product.")
    db.execute("DELETE FROM products WHERE id = ?", (product_id,))
    audit.record(actor, "product.delete", "product", product_id)


def _variant_fields(existing, fields):
    sku = (fields.get("sku") if "sku" in fields else existing["sku"]) or ""
    sku = sku.strip()
    if not sku:
        raise ValueError("A variant needs a SKU.")
    return {
        "sku": sku,
        "barcode": (fields.get("barcode") if "barcode" in fields else existing["barcode"]) or None,
        "label": (fields.get("label") if "label" in fields else existing["label"]) or "",
        "price": float((fields.get("price") if "price" in fields else existing["price"]) or 0),
    }


def add_variant(actor, product_id, *, sku, barcode="", label="", price=0):
    require(actor, "product.edit")
    product = db.query_one(
        "SELECT id FROM products WHERE id = ? AND store_id = ?", (product_id, config.STORE_ID)
    )
    if not product:
        raise ValueError("No such product.")
    sku = (sku or "").strip()
    if not sku:
        raise ValueError("A variant needs a SKU.")
    if db.query_one("SELECT id FROM product_variants WHERE sku = ?", (sku,)):
        raise ValueError(f"SKU {sku!r} is already in use.")
    _rowcount, variant_id = db.execute(
        """INSERT INTO product_variants (product_id, store_id, sku, barcode, label, price)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (product_id, config.STORE_ID, sku, barcode or None, label or "", float(price or 0)),
    )
    audit.record(actor, "product.variant_add", "variant", variant_id, {"sku": sku})
    return get_variant(variant_id)


def update_variant(actor, variant_id, **fields):
    require(actor, "product.edit")
    existing = db.query_one(
        "SELECT * FROM product_variants WHERE id = ? AND store_id = ?", (variant_id, config.STORE_ID)
    )
    if not existing:
        raise ValueError("No such variant.")
    merged = _variant_fields(existing, fields)
    if merged["sku"] != existing["sku"] and db.query_one(
        "SELECT id FROM product_variants WHERE sku = ? AND id != ?", (merged["sku"], variant_id)
    ):
        raise ValueError(f"SKU {merged['sku']!r} is already in use.")
    db.execute(
        "UPDATE product_variants SET sku=?, barcode=?, label=?, price=? WHERE id=?",
        (*merged.values(), variant_id),
    )
    audit.record(actor, "product.variant_edit", "variant", variant_id, {"changed": sorted(fields)})
    return get_variant(variant_id)


def delete_variant(actor, variant_id):
    """Refused on a product's last variant: a product with none is a dangling
    shelf label nothing can ever sell -- delete the product instead."""
    require(actor, "product.delete")
    existing = db.query_one(
        "SELECT id, product_id FROM product_variants WHERE id = ? AND store_id = ?",
        (variant_id, config.STORE_ID),
    )
    if not existing:
        raise ValueError("No such variant.")
    remaining = db.query_one(
        "SELECT COUNT(*) AS n FROM product_variants WHERE product_id = ?", (existing["product_id"],)
    )["n"]
    if remaining <= 1:
        raise ValueError("A product needs at least one variant — delete the product instead.")
    db.execute("DELETE FROM product_variants WHERE id = ?", (variant_id,))
    audit.record(actor, "product.variant_delete", "variant", variant_id)
