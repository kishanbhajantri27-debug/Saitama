"""The parent platform's write and read surface into this store.

Two operations, matching the trust boundary enforced at the route layer (see
api/auth.py's parent-token guard): the parent pushes its catalogue and
pricing down, and pulls stock levels back up for chain-wide reporting. This
store's own inventory counts are never overwritten by a push -- the only path
that changes on_hand is inventory.change_stock, and the parent never calls it.

Products and variants are matched by parent_ref, the parent's own id for each
row -- never by name or SKU, both of which a shopkeeper can legitimately
rename here. A push item with no parent_ref is refused outright: without one,
re-running the same push could never be told apart from a second, genuinely
new catalogue, and would duplicate every product instead of updating it.
"""
import db


class CatalogPushError(Exception):
    """A push payload was malformed enough to refuse outright."""


def _require_ref(value, what):
    value = (value or "").strip()
    if not value:
        raise CatalogPushError(f"every {what} needs a parent_ref")
    return value


def _upsert_product(conn, store_id, product):
    ref = _require_ref(product.get("parent_ref"), "product")
    fields = (
        (product.get("name") or "").strip() or "Unnamed product",
        product.get("brand") or "",
        product.get("category") or "",
        product.get("description") or "",
        product.get("tags") or "",
        product.get("image_url") or "",
    )
    row = conn.execute(
        "SELECT id FROM products WHERE store_id = ? AND parent_ref = ?", (store_id, ref)
    ).fetchone()
    if row:
        conn.execute(
            """UPDATE products SET name=?, brand=?, category=?, description=?,
                                    tags=?, image_url=? WHERE id=?""",
            (*fields, row["id"]),
        )
        return row["id"], False
    conn.execute(
        """INSERT INTO products (store_id, parent_ref, name, brand, category,
                                  description, tags, image_url)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (store_id, ref, *fields),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0], True


def _upsert_variant(conn, store_id, product_id, variant):
    ref = _require_ref(variant.get("parent_ref"), "variant")
    sku = _require_ref(variant.get("sku"), "variant sku")
    fields = (
        sku,
        variant.get("barcode") or None,
        variant.get("label") or "",
        float(variant.get("price") or 0),
    )
    row = conn.execute(
        "SELECT id FROM product_variants WHERE store_id = ? AND parent_ref = ?",
        (store_id, ref),
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE product_variants SET sku=?, barcode=?, label=?, price=? WHERE id=?",
            (*fields, row["id"]),
        )
        return row["id"], False
    conn.execute(
        """INSERT INTO product_variants (product_id, store_id, parent_ref, sku, barcode, label, price)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (product_id, store_id, ref, *fields),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0], True


def upsert_catalog(store_id, products):
    """Apply one push, all-or-nothing.

    A malformed item partway through a large payload must not leave the
    catalogue half updated -- the whole push is one transaction, exactly the
    property `db.transaction()` exists for.
    """
    if not isinstance(products, list):
        raise CatalogPushError("products must be a list")

    counts = {"products": 0, "products_created": 0, "variants": 0, "variants_created": 0}
    with db.transaction() as conn:
        for product in products:
            product_id, created = _upsert_product(conn, store_id, product)
            counts["products"] += 1
            counts["products_created"] += int(created)
            for variant in product.get("variants") or []:
                _variant_id, v_created = _upsert_variant(conn, store_id, product_id, variant)
                counts["variants"] += 1
                counts["variants_created"] += int(v_created)
    return counts


def inventory_for_parent(branch_id=None):
    """Stock levels shaped for the parent's reporting pull.

    Reuses inventory.levels -- the same numbers this store's own dashboard
    reads -- so the parent and the local screens can never quietly disagree
    about what is on the shelf. Rows with no parent_ref (created locally, or
    by seed.py) are included with a null ref; the parent decides what to do
    with stock it never pushed a catalogue entry for.
    """
    from services import inventory

    rows = inventory.levels(branch_id)
    return [
        {
            "parent_ref": r.get("parent_ref"),
            "sku": r["sku"],
            "product_name": r["product_name"],
            "on_hand": r["on_hand"],
            "reserved": r["reserved"],
            "available": r["available"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]
