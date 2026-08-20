"""Demo data.

Idempotent: safe to run on every boot. It fills an empty database and leaves a
populated one alone, so a fresh clone opens on a store that already looks like
a going concern rather than an empty shell.
"""
import secrets

import config
import db
from services import staff


def _announce(generated):
    """Print generated passwords once, at seed time.

    The only moment these exist in plaintext. They are not written to a file
    or returned over HTTP -- if they scroll away, reset the demo or set them
    through the environment.
    """
    if not generated:
        return
    if config.DEMO_MODE:
        # One-tap demo sign-in does not need them, so they are noise for the
        # common case. Mention how to get them rather than printing them.
        print("[store] seeded staff accounts with random passwords; "
              "use the demo role buttons, or set DEMO_*_PASSWORD to pin them",
              flush=True)
        return
    print("[store] generated staff passwords (shown once):", flush=True)
    for username, password in generated.items():
        print(f"[store]   {username}: {password}", flush=True)



STORE = {
    "id": config.STORE_ID,
    "name": "CMR Store",
    "type": "grocery",
    "tagline": "Grains, dry fruits, dairy and everyday grocery essentials",
    "rating": 4.6,
    "city": "Bengaluru",
    "address": "12 MG Road, Bengaluru 560001",
    "phone": "+91 98765 43210",
    "email": "hello@cmrstore.example",
    "opens_at": "09:30",
    "closes_at": "21:30",
    "lat": 12.9752,
    "lng": 77.6050,
    "accent_color": "#2e7d32",
}

# (name, brand, category, rating, count, popularity, description, tags, image, [variants])
# variant = (label, sku, barcode, price, on_hand, age_minutes)
PRODUCTS = [
    ('India Gate Basmati Rice', 'India Gate', 'Grains', 4.6, 940, 96,
     'Long-grain aged basmati that stays separate and fluffy after cooking.',
     'rice basmati grains staple kitchen 5kg',
     'rice_basmati', [
         ('5 kg', 'IG-BAS-5K', '8901234500193', 699, 14, 8),
         ('1 kg', 'IG-BAS-1K', '8901234500200', 159, 30, 5),
     ]),
    ('Sona Masoori Rice', 'Fortune', 'Grains', 4.4, 512, 84,
     'Light, aromatic everyday rice that cooks quickly and reheats well.',
     'rice sona masoori grains staple daily',
     'rice_sona', [
         ('5 kg', 'FT-SM-5K', '8901234500207', 549, 9, 12),
         ('10 kg', 'FT-SM-10K', '8901234500214', 1049, 4, 40),
     ]),
    ('Aashirvaad Whole Wheat Atta', 'Aashirvaad', 'Grains', 4.7, 1340, 97,
     '100% whole wheat flour ground from selected grain for soft rotis.',
     'atta flour wheat chakki roti grains staple',
     'atta', [
         ('5 kg', 'ASH-ATT-5K', '8901234500221', 289, 22, 3),
         ('10 kg', 'ASH-ATT-10K', '8901234500228', 559, 6, 18),
     ]),
    ('Thick Poha (Flattened Rice)', 'Nature Fresh', 'Grains', 4.2, 214, 71,
     'Sun-dried flattened rice for a quick breakfast poha or chivda.',
     'poha flattened rice breakfast grains',
     'poha', [
         ('500 g', 'NF-POH-500', '8901234500235', 65, 26, 6),
     ]),
    ('Toor Dal (Split Pigeon Pea)', 'Tata Sampann', 'Millets & Pulses', 4.6, 780, 93,
     'Unpolished toor dal with the husk intact, cooks soft without losing nutrients.',
     'toor dal arhar pulses lentils protein',
     'dal_toor', [
         ('1 kg', 'TS-TOOR-1K', '8901234500242', 175, 18, 4),
         ('500 g', 'TS-TOOR-500', '8901234500249', 92, 10, 20),
     ]),
    ('Moong Dal (Split Green Gram)', 'Tata Sampann', 'Millets & Pulses', 4.5, 601, 88,
     'Split and de-husked moong, light on the stomach and quick to cook.',
     'moong dal pulses lentils protein',
     'dal_moong', [
         ('1 kg', 'TS-MOONG-1K', '8901234500256', 165, 15, 9),
     ]),
    ('Chana Dal (Split Bengal Gram)', 'Tata Sampann', 'Millets & Pulses', 4.4, 388, 79,
     'Nutty, high-protein split chana for dal, snacks and sweets.',
     'chana dal pulses lentils protein',
     'dal_chana', [
         ('1 kg', 'TS-CHANA-1K', '8901234500263', 135, 20, 11),
     ]),
    ('Ragi Flour (Finger Millet)', 'Patanjali', 'Millets & Pulses', 4.3, 266, 73,
     'Stone-ground finger millet flour, a calcium-rich base for rotis and porridge.',
     'ragi flour millet finger millet healthy',
     'ragi', [
         ('1 kg', 'PTJ-RAGI-1K', '8901234500270', 99, 12, 15),
     ]),
    ('Foxtail Millet (Thinai)', 'Patanjali', 'Millets & Pulses', 4.2, 173, 65,
     'A low-GI millet that swaps in for rice in everyday meals.',
     'foxtail millet thinai grains healthy',
     'millet', [
         ('500 g', 'PTJ-FOX-500', '8901234500277', 89, 16, 22),
     ]),
    ('California Almonds', 'Happilo', 'Dry Fruits & Nuts', 4.6, 1020, 94,
     'Crunchy, whole California almonds packed for freshness.',
     'almonds badam dry fruits nuts snack',
     'almonds', [
         ('250 g', 'HAP-ALM-250', '8901234500284', 299, 3, 6),
         ('500 g', 'HAP-ALM-500', '8901234500291', 549, 8, 2),
     ]),
    ('Cashews (Kaju) W240', 'Happilo', 'Dry Fruits & Nuts', 4.5, 812, 90,
     'Whole, creamy-white cashew kernels, lightly roasted or raw.',
     'cashew kaju dry fruits nuts snack',
     'cashews', [
         ('250 g', 'HAP-CSH-250', '8901234500298', 249, 2, 3),
         ('500 g', 'HAP-CSH-500', '8901234500305', 469, 6, 19),
     ]),
    ('Raisins (Kishmish)', 'Nutraj', 'Dry Fruits & Nuts', 4.3, 405, 77,
     'Naturally sun-dried seedless raisins, sweet and chewy.',
     'raisins kishmish dry fruits nuts sweet',
     'raisins', [
         ('250 g', 'NTJ-RAI-250', '8901234500312', 129, 24, 5),
     ]),
    ('Premium Mixed Nuts', 'Happilo', 'Dry Fruits & Nuts', 4.7, 690, 92,
     'An everyday trail mix of almonds, cashews, walnuts and raisins.',
     'mixed nuts trail mix dry fruits snack healthy',
     'mixednuts', [
         ('250 g', 'HAP-MIX-250', '8901234500319', 265, 11, 10),
         ('500 g', 'HAP-MIX-500', '8901234500326', 499, 5, 26),
     ]),
    ('Walnuts (Akhrot) Kernels', 'Nutraj', 'Dry Fruits & Nuts', 4.4, 301, 75,
     'Light-halved walnut kernels, rich and slightly bitter-sweet.',
     'walnuts akhrot dry fruits nuts brain food',
     'walnuts', [
         ('250 g', 'NTJ-WAL-250', '8901234500333', 349, 7, 14),
     ]),
    ('A2 Cow Milk', 'Amul', 'Milk Products', 4.7, 1450, 97,
     'Fresh, pasteurised A2 cow milk delivered chilled every morning.',
     'milk a2 cow dairy fresh daily',
     'milk', [
         ('1 L', 'AML-MILK-1L', '8901234500340', 65, 20, 1),
         ('500 ml', 'AML-MILK-500', '8901234500347', 35, 30, 1),
     ]),
    ('Fresh Paneer', 'Amul', 'Milk Products', 4.6, 560, 89,
     'Soft, malai-rich paneer cubes made from full-cream milk.',
     'paneer cottage cheese dairy fresh',
     'paneer', [
         ('200 g', 'AML-PNR-200', '8901234500354', 89, 14, 2),
         ('500 g', 'AML-PNR-500', '8901234500361', 209, 6, 2),
     ]),
    ('Fresh Curd (Dahi)', 'Mother Dairy', 'Milk Products', 4.5, 480, 85,
     'Thick, set curd cultured fresh daily from toned milk.',
     'curd dahi yogurt dairy fresh',
     'curd', [
         ('400 g', 'MD-CRD-400', '8901234500368', 45, 22, 1),
         ('1 kg', 'MD-CRD-1K', '8901234500375', 99, 9, 1),
     ]),
    ('Table Butter', 'Amul', 'Milk Products', 4.6, 640, 87,
     'Creamy salted butter, churned from fresh cream.',
     'butter dairy salted spread',
     'butter', [
         ('100 g', 'AML-BTR-100', '8901234500382', 58, 16, 4),
         ('500 g', 'AML-BTR-500', '8901234500389', 265, 5, 21),
     ]),
    ('Desi Cow Ghee', 'Amul', 'Ghee & Oils', 4.8, 990, 96,
     'Pure, aromatic cow ghee slow-cooked in small batches.',
     'ghee cow desi dairy pure clarified butter',
     'ghee', [
         ('500 ml', 'AML-GHEE-500', '8901234500396', 349, 5, 2),
         ('1 L', 'AML-GHEE-1L', '8901234500403', 649, 4, 33),
     ]),
    ('Organic A2 Ghee', 'Patanjali', 'Ghee & Oils', 4.7, 420, 90,
     'Bilona-method A2 ghee from grass-fed cows, no additives.',
     'ghee organic a2 pure dairy',
     'ghee_organic', [
         ('500 ml', 'PTJ-GHEE-500', '8901234500410', 599, 6, 17),
     ]),
    ('Sunflower Oil', 'Fortune', 'Ghee & Oils', 4.4, 733, 86,
     'Refined sunflower oil, light on the palate and heart-friendly.',
     'sunflower oil cooking refined',
     'oil_sunflower', [
         ('1 L', 'FT-SUN-1L', '8901234500417', 149, 18, 6),
         ('5 L', 'FT-SUN-5L', '8901234500424', 699, 0, 45),
     ]),
    ('Kachi Ghani Mustard Oil', 'Fortune', 'Ghee & Oils', 4.3, 288, 78,
     'Cold-pressed mustard oil with a sharp, traditional pungency.',
     'mustard oil kachi ghani cooking',
     'oil_mustard', [
         ('1 L', 'FT-MUS-1L', '8901234500431', 179, 13, 9),
     ]),
    ('Turmeric Powder (Haldi)', 'Everest', 'Spices & Masalas', 4.5, 560, 88,
     'Vivid, high-curcumin turmeric ground from selected fingers.',
     'turmeric haldi powder spice masala',
     'turmeric', [
         ('200 g', 'EVR-HLD-200', '8901234500438', 55, 28, 5),
     ]),
    ('Red Chilli Powder', 'Everest', 'Spices & Masalas', 4.4, 470, 84,
     'Deep red, medium-hot chilli powder for everyday cooking.',
     'chilli powder red masala spice hot',
     'chilipowder', [
         ('200 g', 'EVR-CHL-200', '8901234500445', 65, 21, 7),
     ]),
    ('Garam Masala', 'MDH', 'Spices & Masalas', 4.6, 690, 91,
     'A warm blend of roasted whole spices ground for everyday curries.',
     'garam masala spice blend curry',
     'garammasala', [
         ('100 g', 'MDH-GRM-100', '8901234500452', 79, 19, 4),
     ]),
    ('Coriander Powder (Dhania)', 'MDH', 'Spices & Masalas', 4.3, 340, 76,
     'Freshly milled coriander seeds with a citrusy, earthy aroma.',
     'coriander dhania powder spice masala',
     'corianderpowder', [
         ('200 g', 'MDH-DHN-200', '8901234500459', 49, 24, 8),
     ]),
    ('Organic Rolled Oats', 'Saffola', 'Organic Range', 4.5, 410, 83,
     'Whole-grain rolled oats for a fibre-rich breakfast porridge.',
     'oats organic rolled breakfast healthy',
     'oats', [
         ('500 g', 'SAF-OAT-500', '8901234500466', 165, 17, 5),
         ('1 kg', 'SAF-OAT-1K', '8901234500473', 299, 9, 29),
     ]),
    ('Organic Honey', 'Dabur', 'Organic Range', 4.6, 720, 89,
     '100% pure, unadulterated honey with no added sugar.',
     'honey organic pure natural sweetener',
     'honey', [
         ('500 g', 'DBR-HNY-500', '8901234500480', 249, 12, 6),
         ('250 g', 'DBR-HNY-250', '8901234500487', 139, 20, 2),
     ]),
    ('Organic Jaggery (Gur)', 'Patanjali', 'Organic Range', 4.3, 260, 74,
     'Traditional cane jaggery, unrefined and chemical-free.',
     'jaggery gur organic sweetener natural',
     'jaggery', [
         ('500 g', 'PTJ-GUR-500', '8901234500494', 89, 15, 10),
     ]),
    ('Assam Tea Leaves', 'Tata Tea', 'Beverages', 4.5, 880, 90,
     'Strong, malty CTC tea leaves from the gardens of Assam.',
     'tea leaves assam beverage chai',
     'tea', [
         ('250 g', 'TT-ASM-250', '8901234500501', 145, 26, 3),
         ('500 g', 'TT-ASM-500', '8901234500508', 275, 12, 12),
     ]),
    ('Filter Coffee Powder', 'Continental', 'Beverages', 4.4, 512, 85,
     'A classic South Indian blend of coffee and chicory.',
     'coffee filter powder beverage',
     'coffee', [
         ('200 g', 'CTL-COF-200', '8901234500515', 129, 18, 6),
     ]),
    ('Mixed Fruit Juice', 'Real', 'Beverages', 4.2, 340, 72,
     'No-added-sugar mixed fruit juice, ready to pour and serve.',
     'juice fruit beverage drink',
     'juice', [
         ('1 L', 'RL-JUC-1L', '8901234500522', 110, 14, 2),
     ]),
    ('Dishwash Liquid Gel', 'Vim', 'Household', 4.4, 610, 82,
     'Concentrated lemon dishwash gel that cuts grease fast.',
     'dishwash liquid gel household cleaning',
     'dishwash', [
         ('500 ml', 'VIM-DSH-500', '8901234500529', 99, 23, 4),
     ]),
    ('Detergent Powder', 'Surf Excel', 'Household', 4.5, 705, 86,
     'Stain-removing detergent powder safe for daily wash.',
     'detergent powder laundry household cleaning',
     'detergent', [
         ('1 kg', 'SE-DET-1K', '8901234500536', 135, 16, 7),
         ('3 kg', 'SE-DET-3K', '8901234500543', 375, 6, 31),
     ]),
    ('Infant Cereal', 'Cerelac', 'Baby Care', 4.5, 240, 80,
     'Wheat-based fortified cereal for babies from 6 months.',
     'baby cereal infant food wheat',
     'babycereal', [
         ('300 g', 'CRL-INF-300', '8901234500550', 219, 9, 3),
     ]),
    ('Festive Grocery Hamper', 'CMR Store', 'Combo Packs', 4.7, 96, 68,
     'A gift-ready hamper of ghee, dry fruits, tea and sweets for festive gifting.',
     'combo hamper gift festive grocery bundle',
     'hamper', [
         ('Standard', 'CMR-HMP-01', '8901234500557', 1499, 8, 40),
     ]),
    ('Daily Essentials Combo', 'CMR Store', 'Combo Packs', 4.5, 158, 70,
     'Rice, atta, dal and oil bundled together at a combo price.',
     'combo pack essentials bundle grocery kit',
     'basket', [
         ('Standard', 'CMR-CMB-01', '8901234500564', 899, 11, 12),
     ]),
]

CUSTOMERS = [
    ("Rahul Sharma", "+91 90000 11111", "rahul@example.com"),
    ("Priya Nair", "+91 90000 22222", "priya@example.com"),
    ("Demo Shopper", "", "demo@example.com"),
]

# (name, username, role). No passwords here on purpose: shipping known
# credentials in the repository means every copy of this code shares them.
# Each account gets a strong random password at seed time unless one is pinned
# through the environment, and the generated values are printed once.
EMPLOYEES = [
    ("Anita Rao", "owner", "owner"),
    ("Vikram Singh", "manager", "manager"),
    ("Sara Iqbal", "staff", "staff"),
    ("Former Employee", "exstaff", "staff"),
]

# (customer index, sku, quantity, status)
RESERVATIONS = [
    (0, "AML-GHEE-500", 1, "pending"),
    (1, "HAP-CSH-250", 1, "accepted"),
]

# (sku, quantity, days_ago) -- past sales so the dashboard and trend are not flat
PAST_SALES = [
    ("AML-MILK-1L", 6, 0), ("ASH-ATT-5K", 2, 0), ("EVR-HLD-200", 3, 0),
    ("IG-BAS-5K", 1, 0), ("TS-TOOR-1K", 2, 1), ("AML-PNR-200", 3, 1),
    ("HAP-ALM-250", 1, 2), ("TT-ASM-250", 2, 2), ("AML-MILK-500", 8, 3),
    ("MD-CRD-400", 4, 3), ("FT-SUN-1L", 2, 4), ("SAF-OAT-500", 1, 5),
    ("DBR-HNY-250", 1, 5), ("AML-GHEE-500", 1, 6),
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
                 (id, name, type, tagline, rating, city, address, phone, email,
                  opens_at, closes_at, lat, lng, accent_color)
               VALUES (:id, :name, :type, :tagline, :rating, :city, :address, :phone, :email,
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

        generated = {}
        for ename, username, role in EMPLOYEES:
            password = config.DEMO_PASSWORDS.get(username)
            if not password:
                password = secrets.token_urlsafe(12)
                generated[username] = password
            conn.execute(
                """INSERT INTO employees (store_id, name, username, password_hash, role, status)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (config.STORE_ID, ename, username, staff.hash_password(password), role,
                 # One account ships disabled so the "account switched off"
                 # path is demonstrable without breaking a working login.
                 "disabled" if username == "exstaff" else "active"),
            )
        _announce(generated)

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
            (config.STORE_ID, customer_ids[2], sku_to_variant["FT-SUN-5L"],
             "We will tell you when Sunflower Oil is back",
             "Sunflower Oil (5 L) is out of stock right now."),
        )

    return True


if __name__ == "__main__":
    db.init()
    print("seeded" if run(force=True) else "already seeded", flush=True)
