import io

from flask import Blueprint, jsonify, request, send_file

import config
import db
import seed
from api.auth import (current_actor, issue_token, require_permission, require_staff,
                      revoke, revoke_all_for)
from services import (analytics, audit, catalog, customers, inventory, notifications,
                      reservations, staff, store)
from services.security import (NotAuthenticated, PermissionDenied, matrix,
                               permissions_for)

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


# A service refusing an operation must surface as 403, not 500 -- including
# when a service is reached by a path the route layer did not gate.
@api_bp.errorhandler(PermissionDenied)
def _permission_denied(err):
    return jsonify(error=str(err), permission=err.permission), 403


@api_bp.errorhandler(NotAuthenticated)
def _not_authenticated(err):
    return jsonify(error=str(err)), 401


# ---------- Session / store ----------

@api_bp.post("/session/staff")
def staff_login():
    body = _body()
    member = staff.authenticate(body.get("username"), body.get("password"))
    if not member:
        # One message for every failure mode. Saying which part was wrong tells
        # an attacker which usernames exist.
        audit.record(None, "auth.login_failed", "employee", "",
                     {"username": (body.get("username") or "")[:64]}, outcome="denied")
        return jsonify(error="wrong username or password"), 401

    audit.record(member, "auth.login", "employee", member["id"])
    return jsonify(
        token=issue_token(member["id"]),
        user=staff.public(member),
        permissions=permissions_for(member["role"]),
    )


@api_bp.post("/session/demo")
def demo_login():
    """One-tap sign-in as a demo role.

    This is an authentication bypass, stated plainly. It exists so the showcase
    can be handed to someone without credentials being shared, and it is gated
    on DEMO_MODE -- with that off, the endpoint does not exist and the only way
    in is a real password.

    It is deliberately narrow: it signs in a named seeded account, it cannot
    reach any account created later, and it is audited distinctly from a real
    login so the trail never claims someone typed a password.
    """
    if not config.DEMO_MODE:
        return jsonify(error="not found"), 404

    role = (_body().get("role") or "").strip().lower()
    if role not in ("owner", "manager", "staff"):
        return jsonify(error="unknown demo role"), 400

    member = staff.get_by_username(role)
    if not member or member["status"] != "active":
        return jsonify(error="demo account unavailable"), 404

    audit.record(member, "auth.demo_login", "employee", member["id"], {"role": role})
    return jsonify(
        token=issue_token(member["id"]),
        user=staff.public(member),
        permissions=permissions_for(member["role"]),
    )


@api_bp.post("/session/staff/logout")
def staff_logout():
    actor = current_actor()
    if actor:
        audit.record(actor, "auth.logout", "employee", actor["id"])
    revoke(request.headers.get("X-Staff-Token", ""))
    return jsonify(ok=True)


@api_bp.get("/session/me")
@require_staff
def session_me():
    """Who am I and what may I do -- so the client can lay out its UI."""
    actor = current_actor()
    return jsonify(user=staff.public(actor), permissions=permissions_for(actor["role"]))


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
        demo_mode=config.DEMO_MODE,
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
@require_staff  # per-action permission enforced in the service
def act_on_reservation(reservation_id, action):
    handler = _STAFF_ACTIONS.get(action)
    if not handler:
        return jsonify(error=f"unknown action: {action}"), 404
    return jsonify(handler(reservation_id, actor=current_actor()))


# ---------- Inventory (store mode) ----------

@api_bp.get("/inventory")
@require_permission("inventory.view")
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
@require_permission("inventory.view")
def inventory_summary():
    return jsonify(inventory.summary())


@api_bp.post("/inventory/<int:variant_id>/movement")
@require_staff  # finer check in the service: adjust vs stocktake
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
            variant_id, kind, quantity, note=body.get("note", ""), actor=current_actor())
    except ValueError as err:
        return jsonify(error=str(err)), 400

    # Anyone waiting on this variant hears about it as soon as it is back.
    fired = notifications.fire_back_in_stock(variant_id)
    payload = inventory.describe(row)
    payload["variant_id"] = variant_id
    payload["notified"] = fired
    return jsonify(payload)


@api_bp.post("/inventory/<int:variant_id>/touch")
@require_permission("inventory.adjust")
def touch_stock(variant_id):
    return jsonify(inventory.describe(inventory.touch(variant_id, actor=current_actor())))


@api_bp.get("/inventory/movements")
@require_permission("inventory.history.view")
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


# ---------- Customers (store mode) ----------

@api_bp.get("/customers")
@require_permission("customer.view")
def list_customers():
    return jsonify(customers.list_all(actor=current_actor()))


@api_bp.put("/customers/<int:customer_id>")
@require_permission("customer.edit", entity_type="customer")
def update_customer(customer_id):
    try:
        return jsonify(customers.update(current_actor(), customer_id, _body()))
    except ValueError as err:
        return jsonify(error=str(err)), 404


# ---------- Staff administration ----------

@api_bp.get("/staff")
@require_permission("staff.view")
def list_staff():
    return jsonify(staff.list_all(actor=current_actor()))


@api_bp.post("/staff")
@require_permission("staff.create")
def create_staff():
    body = _body()
    try:
        return jsonify(staff.create(
            current_actor(), body.get("name"), body.get("username"),
            body.get("password"), body.get("role", "staff"))), 201
    except ValueError as err:
        return jsonify(error=str(err)), 400


@api_bp.put("/staff/<int:employee_id>/role")
@require_permission("staff.edit", entity_type="employee")
def change_staff_role(employee_id):
    try:
        member = staff.set_role(current_actor(), employee_id, _body().get("role"))
    except ValueError as err:
        return jsonify(error=str(err)), 400
    # A demotion must not leave the old powers usable on an open session.
    revoke_all_for(employee_id)
    return jsonify(member)


@api_bp.put("/staff/<int:employee_id>/status")
@require_permission("staff.disable", entity_type="employee")
def change_staff_status(employee_id):
    status = _body().get("status")
    try:
        member = staff.set_status(current_actor(), employee_id, status)
    except ValueError as err:
        return jsonify(error=str(err)), 400
    if status == "disabled":
        revoke_all_for(employee_id)
    return jsonify(member)


@api_bp.put("/staff/<int:employee_id>/password")
@require_staff  # own password allowed; the service decides
def change_staff_password(employee_id):
    try:
        member = staff.set_password(current_actor(), employee_id, _body().get("password"))
    except ValueError as err:
        return jsonify(error=str(err)), 400
    return jsonify(member)


@api_bp.delete("/staff/<int:employee_id>")
@require_permission("staff.edit", entity_type="employee")
def delete_staff(employee_id):
    try:
        staff.delete(current_actor(), employee_id)
    except ValueError as err:
        return jsonify(error=str(err)), 400
    revoke_all_for(employee_id)
    return "", 204


@api_bp.get("/permissions")
def permission_matrix():
    """The whole matrix. Public because it documents policy, not secrets."""
    return jsonify(matrix())


# ---------- Audit ----------

@api_bp.get("/audit")
@require_permission("audit.view")
def audit_log():
    return jsonify(audit.recent(
        limit=_int(request.args.get("limit"), 100) or 100,
        actor_id=_int(request.args.get("actor_id")),
        action=request.args.get("action"),
        outcome=request.args.get("outcome"),
    ))


# ---------- Demo controls ----------

@api_bp.post("/demo/reset")
@require_permission("demo.reset")
def demo_reset():
    """Put the showcase back to its opening state.

    Owner-only: it destroys every row in the store. Demo data or not, an
    endpoint that wipes the database should not be reachable by anyone who
    happens to find the URL.
    """
    actor = current_actor()
    audit.record(actor, "demo.reset", "store", config.STORE_ID)
    db.reset()
    seed.run(force=True)
    return jsonify(ok=True, message="Demo data restored")


# ---------- Analytics (store mode) ----------

@api_bp.get("/analytics/today")
@require_permission("analytics.view")
def analytics_today():
    return jsonify(analytics.today())


@api_bp.get("/analytics/overview")
@require_permission("analytics.view")
def analytics_overview():
    return jsonify(analytics.overview())
