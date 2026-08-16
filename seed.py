"""Demo data.

Idempotent: safe to run on every boot. It fills an empty database and leaves a
populated one alone, so a fresh clone opens on a store that already looks like
a going concern rather than an empty shell.
"""
import config
import db
from services import staff

STORE = {
    "id": config.STORE_ID,
    "name": "CMR Store",
    "tagline": "Electronics, apparel and everyday essentials",
    "rating": 4.6,
    "city": "Bengaluru",
    "address": "12 MG Road, Bengaluru 560001",
    "phone": "+91 98765 43210",
    "email": "hello@cmrstore.example",
    "opens_at": "09:30",
    "closes_at": "21:30",
    "lat": 12.9752,
    "lng": 77.6050,
    "accent_color": "#3d5afe",
}

# (name, brand, category, rating, count, popularity, description, tags, image, [variants])
# variant = (label, sku, barcode, price, on_hand, age_minutes)
PRODUCTS = [
    ("Nike Air Max", "Nike", "Footwear", 4.7, 812, 98,
     "Cushioned everyday trainer with a visible Air unit and breathable mesh upper.",
     "shoes sneakers trainers footwear running sports black white",
     "airmax", [
         ("Black - Size 8", "NIK-AM-088", "8901234500018", 4999, 2, 6),
         # 5 on hand less the demo reservation below reads as "4 available,
         # updated 2 minutes ago" -- the exact line in the spec's walkthrough.
         ("Black - Size 9", "NIK-AM-092", "8901234500025", 4999, 5, 2),
         ("White - Size 10", "NIK-AM-101", "8901234500032", 5299, 0, 240),
     ]),
    ("Levi's 511 Jeans", "Levi's", "Apparel", 4.4, 431, 82,
     "Slim-fit stretch denim that holds its shape through the day.",
     "jeans denim pants trousers bottoms slim blue indigo black",
     "jeans", [
         ("Indigo - W32", "LV-511-32", "8901234500049", 3299, 2, 14),
         ("Indigo - W34", "LV-511-34", "8901234500056", 3299, 6, 9),
         ("Black - W32", "LV-511-B32", "8901234500063", 3499, 1, 35),
     ]),
    ("Samsung 25W Charger", "Samsung", "Electronics", 4.5, 1204, 95,
     "Super-fast USB-C wall adapter with PD support. Cable sold separately.",
     "charger adapter usb-c fast charging power plug electronics white black",
     "charger", [
         ("White", "SAM-25W", "8901234500070", 1499, 0, 45),
         ("Black", "SAM-25W-B", "8901234500087", 1499, 12, 4),
     ]),
    ("Bluetooth Headphones", "Sony", "Electronics", 4.6, 967, 91,
     "Over-ear wireless headphones with active noise cancelling and 30-hour battery.",
     "headphones earphones headset wireless bluetooth audio music noise cancelling",
     "headphones", [
         ("Midnight Blue", "SNY-BT-MB", "8901234500094", 8999, 3, 11),
         ("Graphite", "SNY-BT-GR", "8901234500100", 8999, 1, 22),
     ]),
    ("Everyday Backpack", "Wildcraft", "Bags", 4.3, 288, 74,
     "28-litre daypack with a padded laptop sleeve and water-resistant base.",
     "backpack bag rucksack daypack laptop school college travel",
     "backpack", [
         ("Charcoal", "WC-BP-CH", "8901234500117", 2199, 7, 18),
         ("Olive", "WC-BP-OL", "8901234500124", 2199, 4, 30),
     ]),
    ("Cotton T-Shirt", "Allen Solly", "Apparel", 4.2, 512, 69,
     "Combed cotton crew neck that survives a hot wash without losing shape.",
     "tshirt t-shirt shirt tee top cotton casual black white plain",
     "tshirt", [
         ("Black - M", "AS-TS-BM", "8901234500131", 899, 9, 7),
         ("Black - L", "AS-TS-BL", "8901234500148", 899, 5, 7),
         ("White - M", "AS-TS-WM", "8901234500155", 899, 0, 320),
     ]),
    ("Ruled Notebook", "Classmate", "Stationery", 4.1, 176, 58,
     "200-page A5 ruled notebook with a stitched spine that lies flat.",
     "notebook notepad diary journal stationery paper writing school",
     "notebook", [
         ("A5 - 200 pages", "CM-NB-200", "8901234500162", 149, 24, 3),
     ]),
    ("Running Shoes", "Adidas", "Footwear", 4.5, 640, 87,
     "Lightweight road runner with responsive foam and a breathable knit upper.",
     "shoes sneakers trainers footwear running sports jogging grey",
     "runner", [
         ("Grey - Size 9", "ADI-RN-092", "8901234500179", 3799, 3, 13),
         ("Grey - Size 10", "ADI-RN-102", "8901234500186", 3799, 1, 55),
     ]),
]

CUSTOMERS = [
    ("Rahul Sharma", "+91 90000 11111", "rahul@example.com"),
    ("Priya Nair", "+91 90000 22222", "priya@example.com"),
    ("Demo Shopper", "", "demo@example.com"),
]

# (name, username, password, role). Demo credentials on purpose -- they are
# printed on the sign-in screen so the showcase can be handed to anyone. Change
# them before this is ever exposed beyond a demo.
EMPLOYEES = [
    ("Anita Rao", "owner", "owner123", "owner"),
    ("Vikram Singh", "manager", "manager123", "manager"),
    ("Sara Iqbal", "staff", "staff123", "staff"),
    ("Former Employee", "exstaff", "disabled123", "staff"),
]

# (customer index, sku, quantity, status)
RESERVATIONS = [
    (0, "NIK-AM-092", 1, "pending"),
    (1, "SNY-BT-MB", 1, "accepted"),
]

# (sku, quantity, days_ago) -- past sales so the dashboard and trend are not flat
PAST_SALES = [
    ("SAM-25W-B", 2, 0), ("CM-NB-200", 3, 0), ("AS-TS-BM", 1, 0),
    ("NIK-AM-088", 1, 0), ("WC-BP-CH", 1, 1), ("LV-511-34", 2, 1),
    ("SNY-BT-GR", 1, 2), ("ADI-RN-092", 1, 2), ("CM-NB-200", 5, 3),
    ("AS-TS-BL", 2, 3), ("SAM-25W-B", 1, 4), ("WC-BP-OL", 1, 5),
    ("LV-511-32", 1, 5), ("NIK-AM-092", 1, 6),
]


def already_seeded():
    row = db.query_one("SELECT COUNT(*) AS n FROM products WHERE store_id = ?", (config.STORE_ID,))
    return bool(row and row["n"])


def run(force=False):
    if already_seeded() and not force:
        return False

    with db.transaction() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO stores
                 (id, name, tagline, rating, city, address, phone, email,
                  opens_at, closes_at, lat, lng, accent_color)
               VALUES (:id, :name, :tagline, :rating, :city, :address, :phone, :email,
                       :opens_at, :closes_at, :lat, :lng, :accent_color)""",
            STORE,
        )
        conn.execute(
            """INSERT OR REPLACE INTO branches (id, store_id, name, address)
               VALUES (?, ?, ?, ?)""",
            (config.BRANCH_ID, config.STORE_ID, "MG Road", STORE["address"]),
        )

        sku_to_variant = {}
        for name, brand, category, rating, count, pop, desc, tags, img, variants in PRODUCTS:
            cur = conn.execute(
                """INSERT INTO products
                     (store_id, name, brand, category, description, tags, image_url,
                      rating, rating_count, popularity)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (config.STORE_ID, name, brand, category, desc, tags,
                 f"/images/{img}.svg", rating, count, pop),
            )
            product_id = cur.lastrowid
            for label, sku, barcode, price, on_hand, age in variants:
                vc = conn.execute(
                    """INSERT INTO product_variants
                         (product_id, store_id, sku, barcode, label, price)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (product_id, config.STORE_ID, sku, barcode, label, price),
                )
                variant_id = vc.lastrowid
                sku_to_variant[sku] = variant_id
                # Ages are staggered so every freshness state is visible in the
                # demo without anyone having to wait around for one.
                conn.execute(
                    """INSERT INTO inventory
                         (store_id, branch_id, variant_id, on_hand, reserved, updated_at)
                       VALUES (?, ?, ?, ?, 0, datetime('now', ?))""",
                    (config.STORE_ID, config.BRANCH_ID, variant_id, on_hand, f"-{age} minutes"),
                )
                conn.execute(
                    """INSERT INTO inventory_movements
                         (store_id, branch_id, variant_id, kind, quantity, on_hand_delta,
                          note, actor, created_at)
                       VALUES (?, ?, ?, 'STOCK_RECEIVED', ?, ?, 'opening stock', 'system',
                               datetime('now', ?))""",
                    (config.STORE_ID, config.BRANCH_ID, variant_id, on_hand, on_hand,
                     f"-{age} minutes"),
                )

        customer_ids = []
        for cname, phone, email in CUSTOMERS:
            cc = conn.execute(
                "INSERT INTO customers (store_id, name, phone, email) VALUES (?, ?, ?, ?)",
                (config.STORE_ID, cname, phone, email),
            )
            customer_ids.append(cc.lastrowid)

        for ename, username, password, role in EMPLOYEES:
            conn.execute(
                """INSERT INTO employees (store_id, name, username, password_hash, role, status)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (config.STORE_ID, ename, username, staff.hash_password(password), role,
                 # One account ships disabled so the "account switched off"
                 # path is demonstrable without breaking a working login.
                 "disabled" if username == "exstaff" else "active"),
            )

        # Past sales, dated backwards so the week's trend has shape.
        for order_no, (sku, qty, days_ago) in enumerate(PAST_SALES, start=1):
            variant_id = sku_to_variant[sku]
            v = conn.execute(
                """SELECT v.price, p.name FROM product_variants v
                   JOIN products p ON p.id = v.product_id WHERE v.id = ?""",
                (variant_id,),
            ).fetchone()
            total = round(v["price"] * qty, 2)
            oc = conn.execute(
                """INSERT INTO orders
                     (store_id, branch_id, customer_id, variant_id, product_name, sku,
                      unit_price, quantity, total, channel, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'in-store', datetime('now', ?))""",
                (config.STORE_ID, config.BRANCH_ID,
                 customer_ids[order_no % len(customer_ids)], variant_id,
                 v["name"], sku, v["price"], qty, total, f"-{days_ago} days"),
            )
            conn.execute(
                """INSERT INTO payments (store_id, order_id, method, amount, status)
                   VALUES (?, ?, 'card', ?, 'captured')""",
                (config.STORE_ID, oc.lastrowid, total),
            )
            conn.execute(
                "INSERT INTO invoices (store_id, order_id, number, amount) VALUES (?, ?, ?, ?)",
                (config.STORE_ID, oc.lastrowid, f"INV-{oc.lastrowid:05d}", total),
            )
            conn.execute(
                """INSERT INTO inventory_movements
                     (store_id, branch_id, variant_id, kind, quantity, on_hand_delta,
                      note, actor, created_at)
                   VALUES (?, ?, ?, 'SALE', ?, ?, 'counter sale', 'staff',
                           datetime('now', ?))""",
                (config.STORE_ID, config.BRANCH_ID, variant_id, qty, -qty, f"-{days_ago} days"),
            )

        # A couple of live reservations so the store queue is not empty on open.
        for idx, (cust_idx, sku, qty, status) in enumerate(RESERVATIONS):
            variant_id = sku_to_variant[sku]
            conn.execute(
                """INSERT INTO reservations
                     (code, store_id, branch_id, variant_id, customer_id, quantity,
                      status, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now', ?))""",
                (f"RSV-{48291 + idx}", config.STORE_ID, config.BRANCH_ID, variant_id,
                 customer_ids[cust_idx], qty, status, f"+{config.RESERVATION_MINUTES} minutes"),
            )
            conn.execute(
                "UPDATE inventory SET reserved = reserved + ? WHERE variant_id = ? AND branch_id = ?",
                (qty, variant_id, config.BRANCH_ID),
            )
            conn.execute(
                """INSERT INTO inventory_movements
                     (store_id, branch_id, variant_id, kind, quantity, reserved_delta,
                      note, actor)
                   VALUES (?, ?, ?, 'RESERVATION', ?, ?, 'demo reservation', 'customer')""",
                (config.STORE_ID, config.BRANCH_ID, variant_id, qty, qty),
            )

        # Wishlist and a waiting notify-me, so those screens have something to show.
        conn.execute(
            "INSERT OR IGNORE INTO wishlists (store_id, customer_id, product_id) VALUES (?, ?, 1)",
            (config.STORE_ID, customer_ids[2]),
        )
        conn.execute(
            "INSERT OR IGNORE INTO wishlists (store_id, customer_id, product_id) VALUES (?, ?, 3)",
            (config.STORE_ID, customer_ids[2]),
        )
        conn.execute(
            """INSERT INTO notifications (store_id, customer_id, variant_id, kind, title, body)
               VALUES (?, ?, ?, 'back_in_stock', ?, ?)""",
            (config.STORE_ID, customer_ids[2], sku_to_variant["SAM-25W"],
             "We will tell you when Samsung 25W Charger is back",
             "Samsung 25W Charger (White) is out of stock right now."),
        )

    return True


if __name__ == "__main__":
    db.init()
    print("seeded" if run(force=True) else "already seeded", flush=True)
