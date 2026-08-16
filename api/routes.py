import io

from flask import Blueprint, jsonify, request, send_file

import config
import db
import seed
from api.auth import check_passcode, issue_token, require_staff, revoke
from services import (analytics, catalog, customers, inventory, notifications,
                      reservations, store)

api_bp = Blueprint("api", __name__, url_prefix="/api")


def _body():
    return request.get_json(silent=True) or {}


def _int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@api_bp.errorhandler(reservations.ReservationError)
def _reservation_error(err):
    return jsonify(error=str(err)), 400


# ---------- Session / store ----------

@api_bp.post("/session/staff")
def staff_login():
    if not check_passcode(_body().get("passcode")):
        return jsonify(error="wrong passcode"), 401
    return jsonify(token=issue_token(), role="staff")


@api_bp.post("/session/staff/logout")
def staff_logout():
    revoke(request.headers.get("X-Staff-Token", ""))
    return jsonify(ok=True)


@api_bp.get("/store")
def get_store():
    return jsonify(store.profile())


@api_bp.get("/config")
def get_config():
    """What the client needs to render before it knows anything else."""
    return jsonify(
        store_id=config.STORE_ID,
        branch_id=config.BRANCH_ID,
        currency=config.CURRENCY,
        reservation_minutes=config.RESERVATION_MINUTES,
        low_stock_at=config.LOW_STOCK_AT,
        demo_passcode=config.DEMO_PASSCODE_HINT,
    )


# ---------- Catalog ----------

@api_bp.get("/products")
def list_products():
    return jsonify(catalog.list_products(
        search=request.args.get("q", ""),
        category=request.args.get("category"),
        status=request.args.get("status"),
        sort=request.args.get("sort", "popular"),
    ))


@api_bp.get("/products/<int:product_id>")
def get_product(product_id):
    product = catalog.get_product(product_id)
    if not product:
        return jsonify(error="product not found"), 404
    return jsonify(product)


@api_bp.get("/categories")
def get_categories():
    return jsonify(catalog.categories())


@api_bp.get("/lookup")
def lookup_code():
    """Barcode or SKU to a single variant. Used by the scanner."""
    variant = catalog.find_by_code(request.args.get("code", ""))
    if not variant:
        return jsonify(error="no product matches that code"), 404
    return jsonify(variant)


@api_bp.post("/check-many")
def check_many():
    names = _body().get("items") or []
    if not isinstance(names, list):
        return jsonify(error="items must be a list"), 400
    return jsonify(catalog.check_many(names[:12]))


# ---------- Customer identity, wishlist, notifications ----------

@api_bp.get("/me")
def me():
    return jsonify(customers.demo_customer())


@api_bp.get("/customers/<int:customer_id>/wishlist")
def get_wishlist(customer_id):
    return jsonify(customers.wishlist(customer_id))


@api_bp.post("/customers/<int:customer_id>/wishlist")
def add_wishlist(customer_id):
    product_id = _int(_body().get("product_id"))
    if not product_id:
        return jsonify(error="product_id is required"), 400
    return jsonify(customers.add_to_wishlist(customer_id, product_id)), 201


@api_bp.delete("/customers/<int:customer_id>/wishlist/<int:product_id>")
def remove_wishlist(customer_id, product_id):
    return jsonify(customers.remove_from_wishlist(customer_id, product_id))


@api_bp.post("/customers/<int:customer_id>/notify")
def notify_me(customer_id):
    variant_id = _int(_body().get("variant_id"))
    if not variant_id:
        return jsonify(error="variant_id is required"), 400
    try:
        return jsonify(notifications.request_notify(customer_id, variant_id)), 201
    except ValueError as err:
        return jsonify(error=str(err)), 404


@api_bp.get("/customers/<int:customer_id>/notifications")
def list_notifications(customer_id):
    return jsonify(notifications.for_customer(
        customer_id, unseen_only=request.args.get("unseen") == "1"))


@api_bp.post("/customers/<int:customer_id>/notifications/seen")
def seen_notifications(customer_id):
    return jsonify(marked=notifications.mark_seen(customer_id))


# ---------- Reservations ----------

@api_bp.post("/reservations")
def create_reservation():
    body = _body()
    variant_id = _int(body.get("variant_id"))
    if not variant_id:
        return jsonify(error="variant_id is required"), 400

    customer_id = _int(body.get("customer_id"))
    if not customer_id:
        customer = customers.find_or_create(
            body.get("name", "Guest"), body.get("phone", ""), body.get("email", ""))
        customer_id = customer["id"]

    result = reservations.create(
        variant_id=variant_id,
        customer_id=customer_id,
        quantity=_int(body.get("quantity"), 1) or 1,
        note=body.get("note", ""),
        minutes=_int(body.get("minutes")),
    )
    return jsonify(result), 201


@api_bp.get("/reservations")
def list_reservations():
    """Staff see the whole queue; a customer may read only their own."""
    customer_id = _int(request.args.get("customer_id"))
    from api.auth import is_staff
    if not customer_id and not is_staff():
        return jsonify(error="store mode sign-in required"), 401
    return jsonify(reservations.list_all(
        status=request.args.get("status"), customer_id=customer_id))


@api_bp.get("/reservations/<int:reservation_id>")
def get_reservation(reservation_id):
    row = reservations.get(reservation_id)
    if not row:
        return jsonify(error="reservation not found"), 404
    return jsonify(row)


@api_bp.get("/reservations/code/<code>")
def get_reservation_by_code(code):
    row = reservations.get_by_code(code)
    if not row:
        return jsonify(error="no reservation with that code"), 404
    return jsonify(row)


@api_bp.get("/reservations/<int:reservation_id>/qr.svg")
def reservation_qr(reservation_id):
    row = reservations.get(reservation_id)
    if not row:
        return jsonify(error="reservation not found"), 404

    import qrcode
    from qrcode.image.svg import SvgPathImage

    img = qrcode.make(row["code"], image_factory=SvgPathImage, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf)
    buf.seek(0)
    return send_file(buf, mimetype="image/svg+xml")


@api_bp.post("/reservations/<int:reservation_id>/cancel")
def cancel_reservation(reservation_id):
    return jsonify(reservations.cancel(reservation_id))


_STAFF_ACTIONS = {
    "accept": reservations.accept,
    "ready": reservations.mark_ready,
    "reject": reservations.reject,
    "complete": reservations.complete,
}


@api_bp.post("/reservations/<int:reservation_id>/<action>")
@require_staff
def act_on_reservation(reservation_id, action):
    handler = _STAFF_ACTIONS.get(action)
    if not handler:
        return jsonify(error=f"unknown action: {action}"), 404
    return jsonify(handler(reservation_id))


# ---------- Inventory (store mode) ----------

@api_bp.get("/inventory")
@require_staff
def get_inventory():
    rows = inventory.levels()
    q = (request.args.get("q") or "").strip().lower()
    if q:
        rows = [r for r in rows
                if q in r["product_name"].lower() or q in r["sku"].lower()
                or q in (r["brand"] or "").lower() or q in (r["barcode"] or "")]
    status = request.args.get("status")
    if status and status != "all":
        rows = [r for r in rows if r["status"] == status]

    sort = request.args.get("sort", "name")
    keys = {
        "name": lambda r: r["product_name"].lower(),
        "stock_low": lambda r: r["available"],
        "stock_high": lambda r: -r["available"],
        "value": lambda r: -(r["on_hand"] * r["price"]),
        "updated": lambda r: r["freshness"]["minutes"] or 0,
    }
    return jsonify(sorted(rows, key=keys.get(sort, keys["name"])))


@api_bp.get("/inventory/summary")
@require_staff
def inventory_summary():
    return jsonify(inventory.summary())


@api_bp.post("/inventory/<int:variant_id>/movement")
@require_staff
def move_stock(variant_id):
    body = _body()
    kind = body.get("kind")
    if kind not in ("add", "remove", "adjust"):
        return jsonify(error="kind must be add, remove or adjust"), 400
    quantity = _int(body.get("quantity"))
    if quantity is None:
        return jsonify(error="quantity must be a whole number"), 400
    try:
        row = inventory.change_stock(
            variant_id, kind, quantity, note=body.get("note", ""), actor="staff")
    except ValueError as err:
        return jsonify(error=str(err)), 400

    # Anyone waiting on this variant hears about it as soon as it is back.
    fired = notifications.fire_back_in_stock(variant_id)
    payload = inventory.describe(row)
    payload["variant_id"] = variant_id
    payload["notified"] = fired
    return jsonify(payload)


@api_bp.post("/inventory/<int:variant_id>/touch")
@require_staff
def touch_stock(variant_id):
    return jsonify(inventory.describe(inventory.touch(variant_id)))


@api_bp.get("/inventory/movements")
@require_staff
def movement_log():
    return jsonify(inventory.movements(
        limit=_int(request.args.get("limit"), 50) or 50,
        variant_id=_int(request.args.get("variant_id")),
        product_id=_int(request.args.get("product_id")),
    ))


# Public: a shopper looking at a product may see how its count has moved. It
# reveals nothing about who reserved what -- only that stock came and went.
@api_bp.get("/products/<int:product_id>/history")
def product_history(product_id):
    rows = inventory.movements(limit=30, product_id=product_id)
    for row in rows:
        row.pop("actor", None)
        row.pop("note", None)
    return jsonify(rows)


# ---------- Demo controls ----------

@api_bp.post("/demo/reset")
def demo_reset():
    """Put the showcase back to its opening state.

    Not staff-gated on purpose: whoever is running the demo needs it whichever
    mode they are in, and there is nothing here but demo data.
    """
    db.reset()
    seed.run(force=True)
    return jsonify(ok=True, message="Demo data restored")


# ---------- Analytics (store mode) ----------

@api_bp.get("/analytics/today")
@require_staff
def analytics_today():
    return jsonify(analytics.today())


@api_bp.get("/analytics/overview")
@require_staff
def analytics_overview():
    return jsonify(analytics.overview())
