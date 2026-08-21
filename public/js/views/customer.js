import { api, ApiError } from '../api.js';
import { cart } from '../cart.js';
import { navigate, refreshCustomerBadges, state } from '../state.js';
import {
  confirmSheet, el, empty, errorBox, h, money, sheet,
  skeletonGrid, skeletonLines, staleWarning, statusLine, timeline, toast,
} from '../ui.js';

const SEARCH_IDEAS = ['Basmati rice', 'Cow ghee', 'Almonds', 'Toor dal', 'Fresh paneer'];

/* ---------- default imagery ----------
   A product added without a photo (see README: the +Add form's photo is
   optional) still needs to look like something on the shelf, not a blank
   box. This picks a category-appropriate emoji on a coloured tile instead
   of inventing a fake product photo. */
const CATEGORY_ICONS = [
  [/millet|pulse|dal|lentil|chana|moong|ragi/i, '🫘'],
  [/grain|rice|wheat|atta|flour|poha/i, '🌾'],
  [/nut|cashew|almond|raisin|walnut|dry ?fruit/i, '🥜'],
  [/ghee|\boil\b/i, '🫙'],
  [/milk|dairy|paneer|curd|butter/i, '🥛'],
  [/spice|masala|turmeric|chilli|coriander/i, '🌶️'],
  [/tea|coffee|beverage|juice|drink/i, '☕'],
  [/organic|oats|honey|jaggery/i, '🍯'],
  [/combo|hamper|bundle/i, '🎁'],
  [/soap|detergent|dishwash|clean|household/i, '🧴'],
  [/baby/i, '🍼'],
];

export function categoryIcon(name = '') {
  const hit = CATEGORY_ICONS.find(([re]) => re.test(name));
  return hit ? hit[1] : '🏷️';
}

/** A stable colour per product, but kept inside the showroom's own range:
    wheat and honey through to fresh green. Left unbounded this drifts into
    lavender and blue, which look wrong next to food. */
function hueFor(seed) {
  let n = 0;
  for (const ch of String(seed || 'x')) n = (n * 31 + ch.charCodeAt(0)) % 360;
  const WARM_START = 26;   // amber
  const WARM_SPAN = 116;   // ...through olive to leaf green
  return WARM_START + (n % WARM_SPAN);
}

const img = (p) => {
  if (p.image_url) return `<img src="${h(p.image_url)}" alt="${h(p.name || p.product_name || '')}" loading="lazy">`;
  const emoji = categoryIcon(`${p.category || ''} ${p.name || p.product_name || ''}`);
  const hue = hueFor(p.category || p.name || p.product_name);
  return `<div class="thumb-default" style="--h:${hue}"><span>${emoji}</span></div>`;
};

/* ---------- how a picture meets the shelf ----------
   Two kinds of artwork arrive here and they want opposite treatment. A
   cut-out (transparent PNG/SVG) should stand on the lit shelf with a shadow
   under it. A photograph carries its own backdrop, and floating that on the
   shelf just puts a pale rectangle in the middle of the alcove -- it wants
   to sit flush in the frame instead.

   Nothing in CSS can tell them apart, so the corners are sampled once per
   image and the tile is tagged. Same-origin files and data: URLs both draw
   to a canvas cleanly; anything that refuses is treated as a photo, which
   is the safe default. */
const ARTWORK_KIND = new Map();
const SAMPLE = 20;

function sampleKind(node) {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = SAMPLE;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  ctx.drawImage(node, 0, 0, SAMPLE, SAMPLE);
  const { data } = ctx.getImageData(0, 0, SAMPLE, SAMPLE);
  const alphaAt = (x, y) => data[(y * SAMPLE + x) * 4 + 3];
  const edge = SAMPLE - 1;
  const corners = [[0, 0], [edge, 0], [0, edge], [edge, edge]];
  const clear = corners.filter(([x, y]) => alphaAt(x, y) < 24).length;
  // Three clear corners is enough: a cut-out photographed on transparency
  // can still have one corner clipped by the subject.
  return clear >= 3 ? 'cutout' : 'photo';
}

/** True when all four corners are solid -- i.e. the picture sits on a real
    backdrop rather than already being a cut-out. */
function hasOpaqueBorder(node) {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = SAMPLE;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  ctx.drawImage(node, 0, 0, SAMPLE, SAMPLE);
  const { data } = ctx.getImageData(0, 0, SAMPLE, SAMPLE);
  const edge = SAMPLE - 1;
  const alpha = ([x, y]) => data[(y * SAMPLE + x) * 4 + 3];
  return [[0, 0], [edge, 0], [0, edge], [edge, edge]].every((c) => alpha(c) >= 24);
}

/* ---------- lifting a product off its backdrop ----------
   An uploaded photograph usually arrives on a flat studio background. Shown
   honestly on a lit cream shelf that reads as a slab of black (or white)
   around the product, which is exactly what a showroom should not look
   like.

   So the backdrop is knocked out: flood-fill inwards from every edge pixel
   while the colour stays within tolerance of the corner, and make what the
   fill reaches transparent. Filling by connectivity rather than by colour
   alone is the important part -- a dark label or a shadow *inside* the
   bottle is never reached from the edge, so it survives, where a plain
   "everything darker than X" threshold would punch holes through it.

   What remains is cropped to the product and re-encoded as a PNG, so it
   behaves exactly like a cut-out from then on. The stored image is never
   modified; this only changes what gets painted. */
const KNOCKOUT_MAX = 900;        // long edge to process at, to bound the work
const KNOCKOUT_TOLERANCE = 46;   // per channel, generous enough for JPEG noise
const KNOCKOUT_MIN = 0.04;       // ignore if it barely removed anything

function knockOutBackdrop(node) {
  if (!hasOpaqueBorder(node)) return null;   // already a cut-out, leave alone

  const scale = Math.min(1, KNOCKOUT_MAX / Math.max(node.naturalWidth, node.naturalHeight));
  const W = Math.max(1, Math.round(node.naturalWidth * scale));
  const H = Math.max(1, Math.round(node.naturalHeight * scale));

  const canvas = document.createElement('canvas');
  canvas.width = W; canvas.height = H;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  ctx.drawImage(node, 0, 0, W, H);
  const frame = ctx.getImageData(0, 0, W, H);
  const d = frame.data;

  const bg = [d[0], d[1], d[2]];
  const isBackdrop = (o) => Math.abs(d[o] - bg[0]) <= KNOCKOUT_TOLERANCE
                         && Math.abs(d[o + 1] - bg[1]) <= KNOCKOUT_TOLERANCE
                         && Math.abs(d[o + 2] - bg[2]) <= KNOCKOUT_TOLERANCE;

  // Flood from the border inwards. Explicit stack, not recursion: a full
  // frame of backdrop is nearly a million pixels deep.
  const reached = new Uint8Array(W * H);
  const stack = [];
  for (let x = 0; x < W; x++) { stack.push(x, 0, x, H - 1); }
  for (let y = 0; y < H; y++) { stack.push(0, y, W - 1, y); }
  while (stack.length) {
    const y = stack.pop(); const x = stack.pop();
    if (x < 0 || y < 0 || x >= W || y >= H) continue;
    const p = y * W + x;
    if (reached[p] || !isBackdrop(p * 4)) continue;
    reached[p] = 1;
    stack.push(x + 1, y, x - 1, y, x, y + 1, x, y - 1);
  }

  let removed = 0;
  for (let p = 0; p < W * H; p++) if (reached[p]) { d[p * 4 + 3] = 0; removed++; }
  if (removed / (W * H) < KNOCKOUT_MIN) return null;

  // Soften the cut: a pixel still touching the hole, and still close to the
  // backdrop, is JPEG fringing rather than product.
  for (let y = 1; y < H - 1; y++) {
    for (let x = 1; x < W - 1; x++) {
      const p = y * W + x;
      if (reached[p]) continue;
      const o = p * 4;
      if (d[o + 3] === 0) continue;
      const touchesHole = reached[p - 1] || reached[p + 1] || reached[p - W] || reached[p + W];
      if (!touchesHole) continue;
      const drift = Math.max(Math.abs(d[o] - bg[0]), Math.abs(d[o + 1] - bg[1]), Math.abs(d[o + 2] - bg[2]));
      if (drift <= KNOCKOUT_TOLERANCE * 1.8) d[o + 3] = Math.round(255 * (drift / (KNOCKOUT_TOLERANCE * 1.8)));
    }
  }

  // Crop to whatever is still standing.
  let top = H, bottom = -1, left = W, right = -1;
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      if (d[(y * W + x) * 4 + 3] > 12) {
        if (y < top) top = y;
        if (y > bottom) bottom = y;
        if (x < left) left = x;
        if (x > right) right = x;
      }
    }
  }
  if (bottom < 0) return null;

  ctx.putImageData(frame, 0, 0);
  const cw = right - left + 1;
  const ch = bottom - top + 1;
  const out = document.createElement('canvas');
  out.width = cw; out.height = ch;
  out.getContext('2d').drawImage(canvas, left, top, cw, ch, 0, 0, cw, ch);
  return out.toDataURL('image/png');
}
function tagArtwork(node) {
  const stage = node.closest('.thumb, .hero-jar, .cat-thumb, .pdp-stage, .hero');
  if (!stage || !node.naturalWidth) return;
  const key = node.dataset.artKey || node.currentSrc || node.src;

  // The verdict is cached per source and carries the lifted copy with it --
  // otherwise the first tile to see an image would be the only one to get
  // the backdrop removed, and the same product would differ per screen.
  let seen = ARTWORK_KIND.get(key);

  if (!seen) {
    let lifted = null;
    try { lifted = knockOutBackdrop(node); } catch { lifted = null; }
    if (lifted) {
      ARTWORK_KIND.set(key, { kind: null, lifted });   // kind decided once it reloads
      node.dataset.artKey = key;
      node.src = lifted;                                // re-fires load
      return;
    }
    let kind;
    try { kind = sampleKind(node); } catch { kind = 'photo'; }
    seen = { kind, lifted: null };
    ARTWORK_KIND.set(key, seen);
  } else if (seen.lifted && node.src !== seen.lifted) {
    // A later tile showing the same product: hand it the lifted copy too.
    node.dataset.artKey = key;
    node.src = seen.lifted;
    return;
  } else if (!seen.kind) {
    // The lifted copy has just finished loading -- classify what remains.
    try { seen.kind = sampleKind(node); } catch { seen.kind = 'photo'; }
  }

  stage.classList.toggle('has-cutout', seen.kind === 'cutout');
  stage.classList.toggle('has-photo', seen.kind === 'photo');
}

/** Tags anything already decoded; the capture listener below catches the rest. */
export function tagArtworkIn(root = document) {
  root.querySelectorAll('img').forEach((node) => { if (node.complete) tagArtwork(node); });
}

// `load` does not bubble, so this listens on the way down instead.
document.addEventListener('load', (e) => {
  if (e.target instanceof HTMLImageElement) tagArtwork(e.target);
}, true);

/* ---------- shared pieces ---------- */

// Full product rows (with their variants) as last rendered, so the card's
// quick actions can reserve/hold without a second round trip to the server.
const cardData = new Map();

function pickVariant(p) {
  if (!p || !p.variants || !p.variants.length) return null;
  return p.variants.find((v) => v.stock && v.stock.available > 0) || p.variants[0];
}

/** The item as it sits on the shelf: picture under its own spot, then the
    label (brand, name, pack size, rating, price), then what you can do with
    it. Low stock is phrased as a nudge, and anything already held for this
    shopper shows its countdown instead of a second hold button. */
export function productCard(p) {
  cardData.set(p.id, p);
  const saved = state.wishlistIds.has(p.id);
  const variant = pickVariant(p);
  const held = variant ? state.holds.get(variant.id) : null;
  const lowLeft = p.status === 'limited' && p.available
    ? `<span class="leftnote">Only ${p.available} left</span>` : '';

  return `
    <div class="prod" data-product="${p.id}">
      <div class="thumb">
        ${img(p)}
        <button class="heartbtn" data-heart="${p.id}" aria-label="${saved ? 'Remove from' : 'Add to'} wishlist">${saved ? '❤️' : '🤍'}</button>
      </div>
      <div class="body">
        ${p.brand ? `<span class="brand">${h(p.brand)}</span>` : ''}
        <span class="name">${h(p.name)}</span>
        ${variant?.label ? `<span class="qty">${h(variant.label)}</span>` : ''}
        ${p.rating ? `<span class="rate"><span class="star">★</span>${p.rating} <span style="color:var(--muted);font-weight:600">(${p.rating_count})</span></span>` : ''}
        <span class="price">${money(p.price_from)}</span>
        ${statusLine({ ...p, status: p.status, available: p.available }, { showUnits: false })}
        ${lowLeft}
        ${held ? holdNote(held) : `
        <div class="cardactions">
          ${p.status === 'out'
            ? `<button class="btn ghost block" data-notify="${p.id}">🔔 Tell me when it is back</button>`
            : `<button class="btn block" data-add="${p.id}">Add to basket</button>
               <button class="btn ghost block" data-hold="${p.id}">🔒 Hold for 1 hour</button>`}
        </div>`}
      </div>
    </div>`;
}

/** "Reserved for you · 59:42" -- the live half is filled in by startClocks(). */
function holdNote(reservation) {
  return `
    <div class="holdnote">
      <span class="ic">🔒</span>
      <span>
        <b>Reserved for you</b>
        <span class="clock" data-until="${h(reservation.expires_at || '')}">${h(fallbackClock(reservation))}</span>
      </span>
    </div>`;
}

function fallbackClock(reservation) {
  const mins = reservation.expires_in_minutes;
  if (mins === null || mins === undefined) return 'Hold active';
  return `${mins} min remaining`;
}

/** SQLite hands back "YYYY-MM-DD HH:MM:SS" in UTC with no zone marker, so it
    has to be spelled out or the browser reads it as local time. */
function parseUtc(text) {
  if (!text) return null;
  const ms = Date.parse(text.replace(' ', 'T') + 'Z');
  return Number.isNaN(ms) ? null : ms;
}

/** Ticks every countdown on screen once a second. Safe to call after any
    render: it clears the previous timer first. */
let clockTimer = null;
export function startClocks(root = document) {
  if (clockTimer) clearInterval(clockTimer);

  const tick = () => {
    const nodes = root.querySelectorAll('.clock[data-until]');
    if (!nodes.length) return;
    nodes.forEach((node) => {
      const end = parseUtc(node.dataset.until);
      if (!end) return;
      const left = Math.max(0, Math.floor((end - Date.now()) / 1000));
      if (!left) {
        node.textContent = 'Hold ended';
        return;
      }
      const m = String(Math.floor(left / 60)).padStart(2, '0');
      const s = String(left % 60).padStart(2, '0');
      node.textContent = `${m}:${s} remaining`;
    });
  };

  tick();
  clockTimer = setInterval(() => {
    if (!document.body.contains(root === document ? document.body : root)) {
      clearInterval(clockTimer);
      clockTimer = null;
      return;
    }
    tick();
  }, 1000);
}

export function productLine(p) {
  return `
    <button class="line" data-product="${p.id}">
      <div class="thumb">${img(p)}</div>
      <div class="meta">
        <span class="brand" style="font-size:.68rem;color:var(--muted);font-weight:800;text-transform:uppercase">${h(p.brand || '')}</span>
        <span class="name">${h(p.name)}</span>
        <span style="font-weight:800">${money(p.price_from)}</span>
      </div>
      <div style="text-align:right">${statusLine({ status: p.status, available: p.available, freshness: p.freshness })}</div>
    </button>`;
}

/** One place decides what clicking a card, its heart, or its quick actions does. */
export function wireProductClicks(root) {
  tagArtworkIn(root);
  root.querySelectorAll('[data-product]').forEach((node) => {
    node.addEventListener('click', async (e) => {
      const heart = e.target.closest('[data-heart]');
      if (heart) {
        e.stopPropagation();
        await toggleWishlist(Number(heart.dataset.heart), heart);
        return;
      }

      const reserveBtn = e.target.closest('[data-reserve]');
      if (reserveBtn) {
        e.stopPropagation();
        const p = cardData.get(Number(reserveBtn.dataset.reserve));
        const variant = pickVariant(p);
        if (p && variant) openReserveSheet(p, variant);
        return;
      }

      const addBtn = e.target.closest('[data-add]');
      if (addBtn) {
        e.stopPropagation();
        const p = cardData.get(Number(addBtn.dataset.add));
        const variant = pickVariant(p);
        if (!variant || !variant.stock?.available) {
          toast('That one is off the shelf right now', 'err');
          return;
        }
        cart.add(p, variant, 1);
        toast(`${p.name} added to your basket`, 'ok');
        return;
      }

      const holdBtn = e.target.closest('[data-hold]');
      if (holdBtn) {
        e.stopPropagation();
        await quickHold(Number(holdBtn.dataset.hold), holdBtn);
        return;
      }

      const notifyBtn = e.target.closest('[data-notify]');
      if (notifyBtn) {
        e.stopPropagation();
        const p = cardData.get(Number(notifyBtn.dataset.notify));
        const variant = p && p.variants && p.variants[0];
        if (variant) {
          try {
            await api.notifyMe(state.me.id, variant.id);
            toast('We will let you know when it is back', 'ok');
          } catch (err) { toast(err.message, 'err'); }
        }
        return;
      }

      navigate(`/p/${node.dataset.product}`);
    });
  });
}

/** "Hold for 1 hour" reserves one unit for 60 minutes right from the card --
    no sheet, the same real reservation the product page's picker creates.
    The card then swaps its buttons for the countdown rather than navigating
    away, so you can keep shopping with the hold running. */
async function quickHold(productId, btn) {
  const p = cardData.get(productId);
  const variant = pickVariant(p);
  if (!variant || !variant.stock || !variant.stock.available) {
    toast('Nothing left to hold', 'err');
    return;
  }
  const original = btn.textContent;
  btn.disabled = true;
  btn.textContent = 'Holding…';
  try {
    const res = await api.reserve({
      variant_id: variant.id,
      customer_id: state.me.id,
      quantity: 1,
      minutes: 60,
      name: state.me.name,
    });
    state.holds.set(variant.id, res);
    await refreshCustomerBadges();

    const actions = btn.closest('.cardactions');
    if (actions) {
      actions.outerHTML = holdNote(state.holds.get(variant.id) || res);
      startClocks();
    }
    toast('Held for you for 1 hour', 'ok');
  } catch (err) {
    btn.disabled = false;
    btn.textContent = original;
    toast(err.message, 'err');
  }
}

async function toggleWishlist(productId, heartNode) {
  const saved = state.wishlistIds.has(productId);
  try {
    if (saved) {
      await api.removeWishlist(state.me.id, productId);
      state.wishlistIds.delete(productId);
      if (heartNode) heartNode.textContent = '🤍';
      toast('Removed from wishlist');
    } else {
      await api.addWishlist(state.me.id, productId);
      state.wishlistIds.add(productId);
      if (heartNode) heartNode.textContent = '❤️';
      toast('Saved to wishlist', 'ok');
    }
  } catch (err) {
    toast(err.message, 'err');
  }
}

/* ---------- home ----------
   One storefront layout for every shop type: a hero, a real category strip
   and grid (from api.categories(), counted against the catalogue actually
   on the shelf), best sellers, and a right rail modelled on the spotlight /
   why-shop-with-us / refer-a-friend layout this store's own design uses --
   built from real store data and real actions (Reserve / Hold 1 hr are
   genuine reservations, not a cart). The store's `type` only picks a
   cosmetic icon here; nothing about the layout branches on it. */

const TYPE_ICON = { grocery: '🛒', mall: '🏬', general: '🛍️' };

// Plain text, escaped at the point of use. Pre-escaping it here meant the
// rail's h() escaped the ampersand a second time and printed the entity.
const FEATURES = [
  ['🌾', '100% natural', 'No preservatives added'],
  ['📦', 'Hygienically packed', 'Sealed for your family'],
  ['🟢', 'Live shelf counts', 'Real stock, not estimates'],
  ['🔒', 'Hold & collect', 'Keep it aside for an hour'],
];

/* The aisles, in the order a shopper walks them. Each entry finds the real
   category it belongs to; anything in the catalogue that matches none of
   them still gets its own bay at the end, so adding a category upstream
   never leaves products stranded off the shop floor. */
const AISLES = [
  [/grain|rice|wheat|atta|flour/i, '🌾', 'Everyday Grains'],
  [/millet|pulse|dal|lentil/i, '🫘', 'Millets & Pulses'],
  [/nut|dry ?fruit/i, '🥜', 'Dry Fruits & Nuts'],
  [/milk|dairy/i, '🥛', 'Fresh Dairy'],
  [/ghee|oil|butter/i, '🫙', 'Pure Ghee & Oils'],
  [/spice|masala/i, '🌶️', 'Indian Spices'],
  [/organic/i, '🌱', 'Organic Choices'],
];

/* The themed runs of product down the page. Each one is only drawn if the
   catalogue actually has something to put in it. */
const SHELVES = [
  {
    title: 'Fresh From Our Shelves',
    sub: 'Counted most recently, so these numbers are the freshest we have',
    pick: (all) => [...all.filter((p) => p.status !== 'out')]
      .sort((a, b) => (a.freshness?.minutes ?? 1e9) - (b.freshness?.minutes ?? 1e9)).slice(0, 8),
  },
  {
    title: 'Popular Grains',
    sub: 'Rice, wheat and atta for the everyday kitchen',
    match: /grain|rice|wheat|atta|flour/i,
  },
  {
    title: 'Premium Dry Fruits',
    sub: 'Almonds, cashews and everything to keep in the good jar',
    match: /nut|dry ?fruit/i,
  },
  {
    title: 'Pure Dairy',
    sub: 'Milk, paneer, curd and butter from the cold shelf',
    match: /milk|dairy/i,
  },
  {
    title: 'Indian Kitchen Essentials',
    sub: 'The spice box: turmeric, chilli, masalas and whole spices',
    match: /spice|masala/i,
  },
  {
    title: 'Healthy & Organic',
    sub: 'Grown and packed with nothing extra added',
    match: /organic/i,
  },
  {
    title: 'Everyday Essentials',
    sub: 'The things that quietly run out first',
    pick: (all) => all.slice(0, 8),
  },
  {
    title: 'Customer Favourites',
    sub: 'What people here rate the highest',
    pick: (all) => [...all].sort((a, b) => b.rating - a.rating).slice(0, 8),
  },
];

export async function homeView(mount) {
  mount.innerHTML = `
    <div class="shop-home">
      <div class="shop-main showroom">
        <div id="hero"></div>

        <div class="feature-grid">
          ${FEATURES.map(([ic, t, d]) => `
            <div class="feature">
              <span class="feature-ic">${ic}</span>
              <span><b>${h(t)}</b><small>${h(d)}</small></span>
            </div>`).join('')}
        </div>

        <div class="searchbox" style="margin-top:26px">
          <span class="ic">🔍</span>
          <input id="q" type="search" placeholder="Search for grains, dry fruits, milk products…" autocomplete="off">
        </div>
        <div class="chips" style="margin-top:12px" id="ideas">
          ${SEARCH_IDEAS.map((s) => `<button class="chip" data-idea="${h(s)}">${h(s)}</button>`).join('')}
        </div>

        <div id="catrow"></div>
        <div id="body">${skeletonGrid(6)}</div>
      </div>
      <aside class="shop-rail" id="rail"></aside>
    </div>`;

  const q = mount.querySelector('#q');
  q.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && q.value.trim()) navigate(`/search/${encodeURIComponent(q.value.trim())}`);
  });
  mount.querySelectorAll('[data-idea]').forEach((b) => {
    b.onclick = () => navigate(`/search/${encodeURIComponent(b.dataset.idea)}`);
  });

  const hero = mount.querySelector('#hero');
  const catrow = mount.querySelector('#catrow');
  const body = mount.querySelector('#body');
  const rail = mount.querySelector('#rail');
  try {
    const [products, wishlist, categories] = await Promise.all([
      api.products({ sort: 'popular' }),
      api.wishlist(state.me.id),
      api.categories(),
    ]);
    state.wishlistIds = new Set(wishlist.map((p) => p.id));

    hero.innerHTML = heroBanner(products);
    catrow.innerHTML = catRow(categories, products);
    body.innerHTML = catalogBody(products, categories);
    rail.innerHTML = railBody(wishlist);

    wireProductClicks(body);
    wireProductClicks(rail);
    tagArtworkIn(mount);
    startClocks();

    mount.querySelectorAll('[data-cat]').forEach((b) => {
      b.onclick = () => navigate(`/search/cat:${encodeURIComponent(b.dataset.cat)}`);
    });
    const more = mount.querySelector('#morecat');
    if (more) more.onclick = () => navigate('/categories');

    const shopNow = mount.querySelector('#shopnow');
    if (shopNow) shopNow.onclick = () => body.scrollIntoView({ behavior: 'smooth', block: 'start' });
    const checkBtn = mount.querySelector('#check');
    if (checkBtn) checkBtn.onclick = () => navigate('/find');

    const sc = rail.querySelector('#storecard');
    if (sc) sc.onclick = () => navigate('/store-info');
  } catch (err) {
    body.innerHTML = errorBox(err.message, 'retry');
    body.querySelector('#retry').onclick = () => homeView(mount);
  }
}

/** The display window: the store's promise, and a little shelf of real jars
    from the catalogue behind it. */
function heroBanner(products) {
  const withArt = products.filter((p) => p.image_url);
  const jarFor = (re) => withArt.find((p) => re.test(`${p.category} ${p.name}`));
  const picks = [
    jarFor(/rice|grain/i), jarFor(/dal|pulse|millet/i), jarFor(/nut|almond|cashew/i),
    jarFor(/milk|dairy|paneer/i), jarFor(/ghee|oil/i), jarFor(/spice|masala|turmeric/i),
  ].filter(Boolean);

  // Fill any gaps so the shelf is never half empty on a small catalogue.
  const seen = new Set(picks.map((p) => p.id));
  for (const p of withArt) {
    if (picks.length >= 6) break;
    if (!seen.has(p.id)) { picks.push(p); seen.add(p.id); }
  }

  return `
    <section class="hero-banner">
      <div class="hero-text">
        <span class="hero-eyebrow">🌿 ${h(state.store?.city || 'Your neighbourhood store')}</span>
        <h1>Pure Food.<br><span class="leaf">Better Life.</span></h1>
        <p>${h(state.store?.tagline || 'Quality grains, dry fruits and dairy, kept fresh and ready to collect.')}</p>
        <div class="hero-cta">
          <button class="btn lg" id="shopnow">Shop now →</button>
          <button class="btn lg ghost" id="check">✅ Check a shopping list</button>
        </div>
      </div>
      ${picks.length ? `
      <div class="hero-shelf" aria-hidden="true">
        ${picks.slice(0, 6).map((p) => `<div class="hero-jar"><img src="${h(p.image_url)}" alt="" loading="lazy"></div>`).join('')}
      </div>` : ''}
    </section>`;
}

/** Stable-order grouping: first-seen order for the group, insertion order within it. */
function groupBy(rows, keyFn, fallback = 'Other') {
  const groups = new Map();
  for (const row of rows) {
    const key = (keyFn(row) || '').trim() || fallback;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(row);
  }
  return groups;
}

/** Walk the aisles in shopping order, not alphabetical order: the staples
    this store is built around come first, and anything else keeps its place
    behind them rather than being dropped. */
export function inAisleOrder(categories) {
  const rank = (name) => {
    const i = AISLES.findIndex(([re]) => re.test(name));
    return i === -1 ? AISLES.length : i;
  };
  return [...categories].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
}

/** Aisle signs: a quick jump to each real category. */
function catRow(categories, products) {
  if (!categories.length) return '';
  const shown = inAisleOrder(categories).slice(0, 6);
  return `
    <div class="cat-row">
      ${shown.map((c) => `
        <button class="cat-pill" data-cat="${h(c)}">
          <span class="cat-pill-ic">${categoryIcon(c)}</span>${h(c)}
        </button>`).join('')}
      ${categories.length > shown.length
        ? `<button class="cat-pill cat-pill-more" id="morecat"><span class="cat-pill-ic">⋯</span>More</button>` : ''}
    </div>`;
}

/** A collection bay: real product art lit in an alcove, with the names of
    what is actually stocked in it underneath. */
function catCard(name, items) {
  const art = items.find((p) => p.image_url);
  const names = items.slice(0, 4).map((p) => p.name.split(/[,(]/)[0].trim());
  const aisle = AISLES.find(([re]) => re.test(name));
  return `
    <button class="cat-card" data-cat="${h(name)}">
      <span class="cat-thumb">
        ${art
          ? `<img src="${h(art.image_url)}" alt="" loading="lazy">`
          : `<span class="cat-thumb-ic">${aisle ? aisle[1] : categoryIcon(name)}</span>`}
      </span>
      <span class="cat-body">
        <span class="cat-name">${aisle ? aisle[1] + ' ' : ''}${h(name)}</span>
        ${names.length ? `<span class="cat-items">${h(names.join(' • '))}</span>` : ''}
        <span class="cat-count">${items.length} item${items.length === 1 ? '' : 's'}</span>
      </span>
    </button>`;
}

/** One shelf of products, lit and planked. */
function shelf(title, sub, items, link = '') {
  if (!items.length) return '';
  return `
    <div class="sec">
      <div class="sec-head">
        <div>
          <h2>${h(title)}</h2>
          ${sub ? `<div class="sub">${h(sub)}</div>` : ''}
        </div>
        ${link}
      </div>
      <div class="shelf"><div class="hlist">${items.map(productCard).join('')}</div></div>
    </div>`;
}

function catalogBody(products, categories) {
  const byCategory = groupBy(products, (p) => p.category, 'Other');

  if (!products.length) {
    return empty({ icon: '🧺', title: 'The shelves are being stocked', body: 'Check back once the store adds its first products.' });
  }

  const collections = categories.length ? `
    <div class="sec">
      <div class="sec-head">
        <div>
          <h2>🌿 Shop by collection</h2>
          <div class="sub">Every aisle in the store, and what is on it today</div>
        </div>
        <a class="link" href="#/categories">View all →</a>
      </div>
      <div class="cat-grid">${inAisleOrder(categories).map((c) => catCard(c, byCategory.get(c) || [])).join('')}</div>
    </div>` : '';

  // Category-matched shelves pull from the real catalogue; the rest are
  // computed picks. Either way an empty one simply does not render.
  const runs = SHELVES.map((s) => {
    const items = s.match
      ? products.filter((p) => s.match.test(`${p.category} ${p.name}`)).slice(0, 8)
      : s.pick(products);
    return shelf(s.title, s.sub, items,
      s.match ? `<a class="link" href="#/showcase">View all →</a>` : '');
  }).join('');

  return collections + runs;
}

/** Right rail, styled after this store's own spotlight / why-shop-with-us /
    refer-a-friend layout. Everything here is either real store data or, for
    the parts this demo genuinely has no backend for (referrals), a plain
    static panel that says so rather than pretending to work. */
function railBody(wishlist) {
  const s = state.store;
  return `
    ${s ? `
    <div class="spotlight-card">
      <div class="spotlight-banner" style="--h:${hueFor(s.name)}"><span>${TYPE_ICON[state.store?.type] || TYPE_ICON.general}</span></div>
      <div class="spotlight-body">
        <span class="k">Store spotlight</span>
        <h3>${h(s.name)}</h3>
        <p>${h(s.city)} · ★ ${s.rating} · ${s.is_open ? 'Open now' : 'Closed'}</p>
        <button class="btn ghost sm block" id="storecard">Explore store</button>
      </div>
    </div>` : ''}

    <!-- The four promises live in the strip under the hero. Repeating them
         here as "Why shop with us" put the same four lines on screen twice,
         side by side. -->

    <div class="card pad">
      <div class="sec-head" style="margin-bottom:${wishlist.length ? '10px' : '2px'}">
        <h2 style="font-size:.92rem">❤️ Your wishlist</h2>
        <a class="link" href="#/wishlist">See all</a>
      </div>
      ${wishlist.length
        ? `<div class="stack">${wishlist.slice(0, 3).map(productLine).join('')}</div>`
        : `<p style="font-size:.82rem;color:var(--muted)">Tap the heart on any product to save it here.</p>`}
    </div>

    ${s?.phone ? `
    <div class="card pad">
      <h3 class="rail-title">Need help?</h3>
      <a class="btn ghost block sm" style="margin-top:8px" href="tel:${h(s.phone.replace(/\s/g, ''))}">📞 Call the store</a>
    </div>` : ''}`;
}

/* ---------- showcase (everything, one collection) ---------- */

export async function showcaseView(mount) {
  mount.innerHTML = `<div class="wrap" style="padding-top:14px"><div id="body">${skeletonGrid(8)}</div></div>`;
  const body = mount.querySelector('#body');
  try {
    const [products, wishlist] = await Promise.all([
      api.products({ sort: 'name' }),
      api.wishlist(state.me.id),
    ]);
    state.wishlistIds = new Set(wishlist.map((p) => p.id));

    body.innerHTML = products.length
      ? `<p style="color:var(--muted);font-size:.84rem;margin-bottom:12px">${products.length} item${products.length === 1 ? '' : 's'} in the collection</p>
         <div class="prodgrid">${products.map(productCard).join('')}</div>`
      : empty({ icon: '🗂️', title: 'Nothing in the collection yet', body: 'Check back once the store adds items.' });

    wireProductClicks(body);
  } catch (err) {
    body.innerHTML = errorBox(err.message, 'retry');
    body.querySelector('#retry').onclick = () => showcaseView(mount);
  }
}

const section = (title, inner, link = '') => `
  <div class="sec">
    <div class="sec-head"><h2>${title}</h2>${link}</div>
    ${inner}
  </div>`;

/* ---------- search ---------- */

export async function searchView(mount, term = '') {
  // A category card/link passes "cat:<name>" instead of free text -- same
  // encoding the category chips below already use for `filter`.
  const isCategoryLink = term.startsWith('cat:');
  const initialQuery = isCategoryLink ? '' : term;

  mount.innerHTML = `
    <div class="wrap">
      <div style="padding:14px 0 0" class="searchbox">
        <span class="ic">🔍</span>
        <input id="q" type="search" placeholder="What are you looking for?" value="${h(initialQuery)}" autocomplete="off">
        <button class="clr" id="clr" aria-label="Clear">✕</button>
      </div>
      <div class="chips" style="margin-top:12px" id="filters"></div>
      <div id="count" style="font-size:.8rem;color:var(--muted);margin:10px 2px"></div>
      <div id="results">${skeletonLines(4)}</div>
    </div>`;

  const q = mount.querySelector('#q');
  const results = mount.querySelector('#results');
  const count = mount.querySelector('#count');
  let filter = isCategoryLink ? term : 'all';
  let sort = 'popular';
  let categories = [];

  mount.querySelector('#clr').onclick = () => { q.value = ''; q.focus(); run(); };

  let timer;
  q.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(run, 220); });
  q.addEventListener('keydown', (e) => { if (e.key === 'Escape') { q.value = ''; run(); } });

  async function drawFilters() {
    try { categories = await api.categories(); } catch { categories = []; }
    mount.querySelector('#filters').innerHTML = `
      ${['all', 'available', 'limited', 'out'].map((f) => `
        <button class="chip ${filter === f ? 'on' : ''}" data-f="${f}">${
          { all: 'All', available: '🟢 In stock', limited: '🟡 Limited', out: '🔴 Out' }[f]
        }</button>`).join('')}
      ${categories.map((c) => `<button class="chip ${filter === 'cat:' + c ? 'on' : ''}" data-f="cat:${h(c)}">${h(c)}</button>`).join('')}`;
    mount.querySelectorAll('[data-f]').forEach((b) => {
      b.onclick = () => { filter = b.dataset.f; drawFilters(); run(); };
    });
  }

  async function run() {
    results.innerHTML = skeletonLines(3);
    const params = { q: q.value.trim(), sort };
    if (filter.startsWith('cat:')) params.category = filter.slice(4);
    else if (filter !== 'all') params.status = filter;

    try {
      const rows = await api.products(params);
      count.textContent = rows.length
        ? `${rows.length} ${rows.length === 1 ? 'product' : 'products'}`
        : '';
      results.innerHTML = rows.length
        ? `<div class="stack">${rows.map(productLine).join('')}</div>`
        : empty({
            icon: '🔍',
            title: 'Nothing matched that',
            body: q.value.trim()
              ? `We could not find "${q.value.trim()}" in this store. Try a brand or a category.`
              : 'Try one of the suggestions on the home screen.',
          });
      wireProductClicks(results);
    } catch (err) {
      results.innerHTML = errorBox(err.message, 'retry');
      results.querySelector('#retry').onclick = run;
    }
  }

  await drawFilters();
  run();
  if (!term) q.focus();
}

/* ---------- product detail ---------- */

export async function productView(mount, id) {
  mount.innerHTML = `<div class="wrap" style="padding-top:16px">${skeletonLines(2)}</div>`;

  let product;
  try {
    product = await api.product(id);
    trackRecentlyViewed(product.id);
  } catch (err) {
    mount.innerHTML = `<div class="wrap" style="padding-top:16px">${
      err.status === 404
        ? empty({ icon: '🕵️', title: 'Product not found', body: 'It may have been removed from this store.' })
        : errorBox(err.message)
    }</div>`;
    return;
  }

  const inStock = product.variants.filter((v) => v.stock.available > 0);
  let selected = (inStock[0] || product.variants[0]);

  const render = () => {
    const s = selected.stock;
    const saved = state.wishlistIds.has(product.id);
    // One set of actions, rendered twice: beside the product on a wide
    // screen, and in the sticky bar on a phone where the info column has
    // scrolled far below the fold. Both are wired by class, not id.
    const actions = () => (s.available > 0
      ? `<button class="btn lg js-add">Add to basket</button>
         <button class="btn lg ghost js-hold">🔒 Hold for 1 hour</button>`
      : `<button class="btn lg soft js-notify">🔔 Notify me when back</button>`);

    mount.innerHTML = `
      <div class="wrap pdp-wrap">
        <div class="pdp">
          <!-- the display stand: product lit from above, standing on wood -->
          <div class="pdp-stage">
            <button class="heartbtn js-wish" aria-label="${saved ? 'Remove from' : 'Add to'} wishlist">${saved ? '❤️' : '🤍'}</button>
            ${img(product)}
          </div>

          <div class="pdp-info">
            ${product.brand ? `<span class="pdp-brand">${h(product.brand)}</span>` : ''}
            <h2 class="pdp-name">${h(product.name)}</h2>
            ${product.rating ? `<div class="pdp-rating"><span class="star">★</span> ${product.rating}
              <span class="count">· ${product.rating_count} ratings</span></div>` : ''}

            <div class="pdp-price">
              <span class="price-lg">${money(selected.price)}</span>
              ${selected.label ? `<span class="pdp-pack">${h(selected.label)}</span>` : ''}
            </div>

            <div class="pdp-avail">
              ${statusLine(s, { showUnits: true })}
            </div>
            ${staleWarning(s)}

            ${product.description ? `<p class="pdp-desc">${h(product.description)}</p>` : ''}

            ${product.variants.length > 1 ? `
            <div class="pdp-block">
              <h3 class="pdp-label">Pack size</h3>
              <div class="varlist">
                ${product.variants.map((v) => `
                  <button class="var ${v.id === selected.id ? 'on' : ''} ${v.stock.available ? '' : 'dead'}"
                          data-var="${v.id}" ${v.stock.available ? '' : 'disabled'}>
                    <span style="flex:1">
                      <span class="l">${h(v.label)}</span>
                      <span class="sku" style="display:block">${h(v.sku)}</span>
                    </span>
                    <span style="text-align:right">
                      <span style="font-weight:800;display:block">${money(v.price)}</span>
                      <span class="stat ${h(v.stock.status)}" style="font-size:.72rem"><span class="dot"></span>${
                        v.stock.available ? `${v.stock.available} left` : 'Out'}</span>
                    </span>
                  </button>`).join('')}
              </div>
            </div>` : ''}

            <div class="pdp-block">
              <h3 class="pdp-label">On the shelf</h3>
              <div class="card pad">
                <div class="kv"><span class="k">In stock</span><span class="v">${s.on_hand}</span></div>
                <div class="kv"><span class="k">Reserved by others</span><span class="v">${s.reserved}</span></div>
                <div class="kv" style="border-top:1px solid var(--line);margin-top:4px;padding-top:10px">
                  <span class="k" style="font-weight:800;color:var(--ink)">Available to reserve</span>
                  <span class="v stat ${h(s.status)}" style="font-size:.95rem"><span class="dot"></span>${s.available}</span>
                </div>
                <div class="kv"><span class="k">Last counted</span><span class="v">${h(s.freshness.label)}</span></div>
              </div>
            </div>

            <div class="pdp-actions">${actions()}</div>
          </div>

          <!-- These sit under the picture on a wide screen rather than below
               the whole grid, which is what used to leave a column of empty
               page beside the details. In source order they stay after the
               details, so a phone still reads picture, product, then these. -->
          <div class="sec pdp-extra">
            <div class="sec-head"><h2>Details</h2></div>
            <div class="card pad">
              <div class="kv"><span class="k">SKU</span><span class="v">${h(selected.sku)}</span></div>
              <div class="kv"><span class="k">Barcode</span><span class="v">${h(selected.barcode || '—')}</span></div>
              <div class="kv"><span class="k">Category</span><span class="v">${h(product.category)}</span></div>
              <div class="kv"><span class="k">In store</span><span class="v">${h(state.store?.name || '')}, ${h(state.store?.city || '')}</span></div>
            </div>
          </div>

          <div class="sec pdp-extra">
            <div class="sec-head"><h2>Stock history</h2></div>
            <div id="history" class="card pad"><div class="sk t" style="height:44px"></div></div>
          </div>
        </div>
      </div>

      <div class="stickybar pdp-bar">
        <button class="btn ghost js-wish" style="flex:0 0 52px" aria-label="Wishlist">${saved ? '❤️' : '🤍'}</button>
        ${actions()}
      </div>`;

    mount.querySelectorAll('[data-var]').forEach((b) => {
      b.onclick = () => {
        selected = product.variants.find((v) => v.id === Number(b.dataset.var));
        render();
      };
    });

    // Both copies of each control share a class, so whichever one the
    // breakpoint is showing is live.
    mount.querySelectorAll('.js-wish').forEach((btn) => {
      btn.onclick = async () => {
        await toggleWishlist(product.id, null);
        const mark = state.wishlistIds.has(product.id) ? '❤️' : '🤍';
        mount.querySelectorAll('.js-wish').forEach((b) => { b.textContent = mark; });
      };
    });

    mount.querySelectorAll('.js-hold').forEach((btn) => {
      btn.onclick = () => openReserveSheet(product, selected);
    });

    // Adds the option the shopper is actually looking at, not the first one
    // in stock -- on this screen they have already made that choice.
    mount.querySelectorAll('.js-add').forEach((btn) => {
      btn.onclick = () => {
        cart.add(product, selected, 1);
        toast(`${product.name} added to your basket`, 'ok');
      };
    });

    mount.querySelectorAll('.js-notify').forEach((btn) => {
      btn.onclick = async () => {
        try {
          await api.notifyMe(state.me.id, selected.id);
          toast('We will let you know when it is back', 'ok');
        } catch (err) { toast(err.message, 'err'); }
      };
    });

    tagArtworkIn(mount);
    loadHistory();
  };

  async function loadHistory() {
    const box = mount.querySelector('#history');
    if (!box) return;
    try {
      const rows = await api.productHistory(product.id);
      box.innerHTML = timeline(rows.slice(0, 8), { emptyText: 'No stock movements recorded yet.' });
    } catch {
      box.innerHTML = '<p class="empty" style="padding:16px">Stock history unavailable.</p>';
    }
  }

  render();
}

/* ---------- reserve ---------- */

function openReserveSheet(product, variant) {
  const max = variant.stock.available;
  const mins = state.config?.reservation_minutes || 30;

  sheet(`
    <h3>Reserve product</h3>
    <p style="color:var(--muted);font-size:.85rem;margin-bottom:16px">Held for you at ${h(state.store?.name || 'the store')}.</p>
    <div class="card pad" style="margin-bottom:14px">
      <div class="kv"><span class="k">Product</span><span class="v">${h(product.name)}</span></div>
      <div class="kv"><span class="k">Option</span><span class="v">${h(variant.label)}</span></div>
      <div class="kv"><span class="k">Price</span><span class="v">${money(variant.price)}</span></div>
    </div>
    <label class="field" style="margin-bottom:12px">
      <span class="lbl">Quantity (max ${max})</span>
      <select class="input" id="qty">
        ${Array.from({ length: Math.min(max, 5) }, (_, i) => `<option value="${i + 1}">${i + 1}</option>`).join('')}
      </select>
    </label>
    <label class="field" style="margin-bottom:12px">
      <span class="lbl">Hold for</span>
      <select class="input" id="mins">
        <option value="30" selected>30 minutes</option>
        <option value="60">1 hour</option>
        <option value="120">2 hours</option>
      </select>
    </label>
    <label class="field" style="margin-bottom:18px">
      <span class="lbl">Your name</span>
      <input class="input" id="nm" value="${h(state.me?.name || '')}" placeholder="Name for the counter">
    </label>
    <p style="font-size:.76rem;color:var(--muted);margin-bottom:14px">Demo only — no payment is taken and no real details are needed.</p>
    <button class="btn lg block" id="go">Confirm reservation</button>
    <p style="font-size:.74rem;color:var(--muted);text-align:center;margin-top:10px">Default hold is ${mins} minutes.</p>
  `, {
    onMount(panel, close) {
      panel.querySelector('#go').onclick = async (e) => {
        const btn = e.currentTarget;
        btn.disabled = true;
        btn.textContent = 'Reserving…';
        try {
          const res = await api.reserve({
            variant_id: variant.id,
            customer_id: state.me.id,
            quantity: Number(panel.querySelector('#qty').value),
            minutes: Number(panel.querySelector('#mins').value),
            name: panel.querySelector('#nm').value.trim() || state.me.name,
          });
          close();
          navigate(`/reservation/${res.id}`);
        } catch (err) {
          btn.disabled = false;
          btn.textContent = 'Confirm reservation';
          toast(err.message, 'err');
        }
      };
    },
  });
}

/* ---------- reservation status ---------- */

const STATUS_COPY = {
  pending: { icon: '🟡', title: 'Awaiting store confirmation', body: 'The store has your request and will confirm shortly.' },
  accepted: { icon: '🔵', title: 'Accepted — being prepared', body: 'The store accepted your reservation and is getting it ready.' },
  ready_for_pickup: { icon: '🟢', title: 'Ready for pickup', body: 'Show this code at the counter to collect your item.' },
  completed: { icon: '✅', title: 'Picked up', body: 'This reservation is complete. Thanks for shopping with us.' },
  rejected: { icon: '🔴', title: 'Declined', body: 'The store could not fulfil this one. The stock has been released.' },
  expired: { icon: '⌛', title: 'Expired', body: 'The hold ran out and the item went back on sale.' },
  cancelled: { icon: '⚪', title: 'Cancelled', body: 'You cancelled this reservation.' },
};

export async function reservationView(mount, id) {
  const draw = async () => {
    let r;
    try {
      r = await api.reservation(id);
    } catch (err) {
      mount.innerHTML = `<div class="wrap" style="padding-top:16px">${errorBox(err.message)}</div>`;
      return;
    }

    const copy = STATUS_COPY[r.status] || STATUS_COPY.pending;
    mount.innerHTML = `
      <div class="wrap" style="padding-top:18px">
        <div style="text-align:center;padding:8px 0 18px">
          <div style="font-size:2.6rem">${copy.icon}</div>
          <h2 style="font-size:1.25rem;margin-top:8px">${h(copy.title)}</h2>
          <p style="color:var(--muted);font-size:.87rem;margin-top:6px">${h(copy.body)}</p>
        </div>

        ${['accepted', 'ready_for_pickup', 'pending'].includes(r.status) ? `
          <div class="card pad" style="text-align:center">
            <div class="qrbox"><img src="/api/reservations/${r.id}/qr.svg" alt="Reservation QR code" width="168" height="168"></div>
            <div class="rescode" style="margin-top:12px">${h(r.code)}</div>
            <p style="font-size:.78rem;color:var(--muted);margin-top:6px">
              ${r.expires_in_minutes !== null ? `Held for ${r.expires_in_minutes} more minute${r.expires_in_minutes === 1 ? '' : 's'}` : 'Hold active'}
            </p>
          </div>` : `
          <div class="card pad" style="text-align:center">
            <div class="rescode">${h(r.code)}</div>
          </div>`}

        <div class="card pad" style="margin-top:14px">
          <div class="kv"><span class="k">Product</span><span class="v">${h(r.product_name)}</span></div>
          <div class="kv"><span class="k">Option</span><span class="v">${h(r.variant_label)}</span></div>
          <div class="kv"><span class="k">Quantity</span><span class="v">${r.quantity}</span></div>
          <div class="kv"><span class="k">Total</span><span class="v">${money(r.price * r.quantity)}</span></div>
          <div class="kv"><span class="k">Status</span><span class="v"><span class="badge ${h(r.status)}">${h(r.status)}</span></span></div>
          <div class="kv"><span class="k">Pickup at</span><span class="v">${h(state.store?.name || '')}</span></div>
        </div>

        ${r.is_open ? `<button class="btn ghost block" id="cancel" style="margin-top:14px">Cancel reservation</button>` : ''}
        <button class="btn soft block" id="more" style="margin-top:10px">Keep shopping</button>
      </div>`;

    mount.querySelector('#more').onclick = () => navigate('/home');
    const cancelBtn = mount.querySelector('#cancel');
    if (cancelBtn) cancelBtn.onclick = async () => {
      const yes = await confirmSheet({
        title: 'Cancel this reservation?',
        body: 'The item goes back on sale straight away.',
        confirmLabel: 'Cancel it', danger: true,
      });
      if (!yes) return;
      try {
        await api.cancelReservation(r.id);
        toast('Reservation cancelled');
        draw();
      } catch (err) { toast(err.message, 'err'); }
    };
  };

  await draw();

  // The store may act while this screen is open; poll so the customer sees
  // "ready for pickup" without being told to refresh.
  const timer = setInterval(() => {
    if (!document.body.contains(mount) || document.hidden) return;
    if (!location.hash.includes(`/reservation/${id}`)) return clearInterval(timer);
    draw();
  }, 6000);
}

/* ---------- my reservations ---------- */

export async function myReservationsView(mount) {
  // The app bar already reads "Your reservations", so this is the standing
  // note rather than the title again.
  mount.innerHTML = `<div class="wrap" style="padding-top:20px">
      <p class="page-note">Show the code at the counter to collect.</p>
      <div id="list">${skeletonLines(3)}</div></div>`;
  const list = mount.querySelector('#list');
  try {
    const rows = await api.reservations({ customer_id: state.me.id });
    list.innerHTML = rows.length ? `<div class="stack">${rows.map((r) => `
      <button class="line" data-res="${r.id}">
        <div class="thumb">${r.image_url ? `<img src="${h(r.image_url)}" alt="">` : ''}</div>
        <div class="meta">
          <span class="name">${h(r.product_name)}</span>
          <span class="sku">${h(r.code)} · ${h(r.variant_label)}</span>
          <span style="font-size:.78rem;color:var(--muted)">Qty ${r.quantity} · ${money(r.price * r.quantity)}</span>
        </div>
        <span class="badge ${h(r.status)}">${h(r.status)}</span>
      </button>`).join('')}</div>`
      : empty({ icon: '🎟️', title: 'No reservations yet', body: 'Reserve something and it will show up here.' });

    list.querySelectorAll('[data-res]').forEach((b) => {
      b.onclick = () => navigate(`/reservation/${b.dataset.res}`);
    });
  } catch (err) {
    list.innerHTML = errorBox(err.message);
  }
}

/* ---------- wishlist ---------- */

export async function wishlistView(mount) {
  mount.innerHTML = `<div class="wrap" style="padding-top:20px">
      <p class="page-note">We flag these the moment they are back on the shelf.</p>
      <div id="list">${skeletonGrid(4)}</div>
    </div>`;
  const list = mount.querySelector('#list');
  try {
    const [rows] = await Promise.all([api.wishlist(state.me.id), refreshCustomerBadges()]);
    state.wishlistIds = new Set(rows.map((p) => p.id));
    if (!rows.length) {
      list.innerHTML = empty({ icon: '🤍', title: 'Nothing saved yet', body: 'Tap the heart on any product to keep an eye on it.' });
      return;
    }
    list.innerHTML = `<div class="prodgrid">${rows.map((p) => `
      <div style="position:relative">
        ${p.back_in_stock ? '<span class="badge ready" style="position:absolute;top:8px;left:8px;z-index:3">🔔 Back in stock</span>' : ''}
        ${productCard(p)}
      </div>`).join('')}</div>`;
    wireProductClicks(list);
  } catch (err) {
    list.innerHTML = errorBox(err.message);
  }
}

/* ---------- recently viewed ----------
   Kept on this device only (localStorage, most-recent-first, capped) --
   there is no customer login for this to hang off server-side. */
const RECENT_KEY = 'recentlyViewed';
const RECENT_MAX = 12;

function trackRecentlyViewed(productId) {
  let ids = [];
  try { ids = JSON.parse(localStorage.getItem(RECENT_KEY) || '[]'); } catch { ids = []; }
  ids = ids.filter((id) => id !== productId);
  ids.unshift(productId);
  localStorage.setItem(RECENT_KEY, JSON.stringify(ids.slice(0, RECENT_MAX)));
}

export async function recentlyViewedView(mount) {
  mount.innerHTML = `<div class="wrap" style="padding-top:20px">
      <p class="page-note">Kept on this device only.</p>
      <div id="list">${skeletonGrid(4)}</div>
    </div>`;
  const list = mount.querySelector('#list');

  let ids = [];
  try { ids = JSON.parse(localStorage.getItem(RECENT_KEY) || '[]'); } catch { ids = []; }
  if (!ids.length) {
    list.innerHTML = empty({ icon: '🕓', title: 'Nothing viewed yet', body: 'Products you open will show up here.' });
    return;
  }

  try {
    const [all, wishlist] = await Promise.all([api.products({ sort: 'name' }), api.wishlist(state.me.id)]);
    state.wishlistIds = new Set(wishlist.map((p) => p.id));
    const byId = new Map(all.map((p) => [p.id, p]));
    const rows = ids.map((pid) => byId.get(pid)).filter(Boolean);
    list.innerHTML = rows.length
      ? `<div class="prodgrid">${rows.map(productCard).join('')}</div>`
      : empty({ icon: '🕓', title: 'Nothing viewed yet', body: 'Products you open will show up here.' });
    wireProductClicks(list);
  } catch (err) {
    list.innerHTML = errorBox(err.message);
  }
}

/* ---------- basket ----------
   The basket is a shopping list held on this device. Checkout is what makes
   it real: every line becomes a one-hour reservation, which is the only
   thing in this app that actually holds stock. */

export async function cartView(mount) {
  const draw = () => {
    const rows = cart.items();

    if (!rows.length) {
      mount.innerHTML = `<div class="wrap" style="padding-top:24px">
          ${empty({
            icon: '🧺',
            title: 'Your basket is empty',
            body: 'Add something from the shelves and it will wait for you here.',
            action: '<button class="btn lg" id="browse" style="margin-top:18px">Browse the shelves</button>',
          })}
        </div>`;
      mount.querySelector('#browse').onclick = () => navigate('/home');
      return;
    }

    mount.innerHTML = `
      <div class="wrap" style="padding-top:20px">
        <!-- The app bar already says "Basket"; repeating it as a heading here
             just pushed the list down, so this is only the count line. -->
        <p class="cart-count">${rows.length} item${rows.length === 1 ? '' : 's'} ready to hold for pickup</p>

        <div class="cart-layout">
          <div class="stack">
            ${rows.map((r) => `
              <div class="cart-line" data-line="${r.variant_id}">
                <div class="thumb">
                  ${r.image_url
                    ? `<img src="${h(r.image_url)}" alt="" loading="lazy">`
                    : `<span style="font-size:1.6rem">${categoryIcon(`${r.category} ${r.name}`)}</span>`}
                </div>
                <div class="meta">
                  ${r.brand ? `<div class="brand">${h(r.brand)}</div>` : ''}
                  <div class="name">${h(r.name)}</div>
                  ${r.label ? `<div class="qty">${h(r.label)}</div>` : ''}
                  <div class="qty">${money(r.price)} each</div>
                </div>
                <div class="stepper">
                  <button data-dec="${r.variant_id}" aria-label="One fewer">−</button>
                  <span class="n">${r.quantity}</span>
                  <button data-inc="${r.variant_id}" aria-label="One more">+</button>
                </div>
                <div class="lineprice">${money(r.price * r.quantity)}</div>
                <button class="iconbtn" data-del="${r.variant_id}" aria-label="Remove">✕</button>
              </div>`).join('')}
          </div>

          <div class="cart-summary">
            <!-- "Order summary" heads the panel; the amount is the "Total"
                 row below, so the old "Basket total" heading read as a
                 duplicate label for the same number. -->
            <h3>Order summary</h3>
            <div class="kv"><span class="k">Items</span><span class="v">${cart.count()}</span></div>
            <div class="kv"><span class="k">Pickup at</span><span class="v">${h(state.store?.name || '')}</span></div>
            <div class="total"><span>Total</span><span>${money(cart.total())}</span></div>
            <button class="btn lg block" id="checkout" style="margin-top:16px">🔒 Hold all for 1 hour</button>
            <p class="cart-note">
              Nothing is charged here. Holding puts each item aside at the counter for an hour
              so it is still there when you arrive.
            </p>
          </div>
        </div>
      </div>`;

    tagArtworkIn(mount);

    mount.querySelectorAll('[data-inc]').forEach((b) => {
      b.onclick = () => {
        const row = rows.find((r) => r.variant_id === Number(b.dataset.inc));
        cart.setQuantity(row.variant_id, row.quantity + 1);
        draw();
      };
    });
    mount.querySelectorAll('[data-dec]').forEach((b) => {
      b.onclick = () => {
        const row = rows.find((r) => r.variant_id === Number(b.dataset.dec));
        cart.setQuantity(row.variant_id, row.quantity - 1);
        draw();
      };
    });
    mount.querySelectorAll('[data-del]').forEach((b) => {
      b.onclick = () => { cart.remove(Number(b.dataset.del)); draw(); };
    });

    mount.querySelector('#checkout').onclick = async (e) => {
      const btn = e.currentTarget;
      btn.disabled = true;
      btn.textContent = 'Holding your basket…';

      const held = [];
      const failed = [];
      for (const row of rows) {
        try {
          const res = await api.reserve({
            variant_id: row.variant_id,
            customer_id: state.me.id,
            quantity: row.quantity,
            minutes: 60,
            name: state.me.name,
          });
          held.push(res);
          cart.remove(row.variant_id);
        } catch (err) {
          failed.push(`${row.name}: ${err.message}`);
        }
      }

      await refreshCustomerBadges();

      if (!held.length) {
        btn.disabled = false;
        btn.textContent = '🔒 Hold all for 1 hour';
        toast(failed[0] || 'Could not hold those items', 'err');
        draw();
        return;
      }

      // A partly-held basket keeps whatever could not be held, so it is
      // obvious what still needs attention.
      if (failed.length) toast(`Held ${held.length}, but ${failed.length} could not be held`, 'err');
      else toast('Your basket is held for the next hour', 'ok');

      if (held.length === 1 && !failed.length) navigate(`/reservation/${held[0].id}`);
      else navigate('/reservations');
    };
  };

  draw();
}

/* ---------- categories ---------- */

export async function categoriesView(mount) {
  mount.innerHTML = `<div class="wrap showroom" style="padding-top:22px">
      <div class="sec-head">
        <div>
          <h2>Every aisle in the store</h2>
          <div class="sub">Grains, pulses, dry fruits, dairy, ghee, spices and more</div>
        </div>
      </div>
      <div id="list">${skeletonGrid(6)}</div>
    </div>`;
  const list = mount.querySelector('#list');
  try {
    const [products, categories] = await Promise.all([api.products({ sort: 'name' }), api.categories()]);
    const byCategory = groupBy(products, (p) => p.category, 'Other');
    list.innerHTML = categories.length
      ? `<div class="cat-grid">${inAisleOrder(categories).map((c) => catCard(c, byCategory.get(c) || [])).join('')}</div>`
      : empty({ icon: '🗂️', title: 'No categories yet', body: 'They appear as the store adds products.' });
    tagArtworkIn(list);
    list.querySelectorAll('[data-cat]').forEach((b) => {
      b.onclick = () => navigate(`/search/cat:${encodeURIComponent(b.dataset.cat)}`);
    });
  } catch (err) {
    list.innerHTML = errorBox(err.message);
  }
}

/* ---------- account ---------- */

export async function accountView(mount) {
  const s = state.store;
  mount.innerHTML = `
    <div class="wrap" style="padding-top:16px">
      <div class="card pad" style="display:flex;gap:14px;align-items:center">
        <span class="account-avatar">👤</span>
        <span style="flex:1">
          <b style="display:block;font-size:1rem">Hi, ${h(state.me?.name || 'there')}</b>
          <small style="color:var(--muted)">Browsing as a guest — this showcase needs no account.</small>
        </span>
      </div>

      <div class="stack" style="margin-top:14px">
        <button class="modecard" data-go="/reservations">
          <span class="ic">🎟️</span>
          <span style="flex:1"><span class="t">My orders</span><span class="d">Reservations you have placed</span></span>
          <span style="color:var(--muted)">›</span>
        </button>
        <button class="modecard" data-go="/wishlist">
          <span class="ic">❤️</span>
          <span style="flex:1"><span class="t">Wishlist</span><span class="d">Items you are watching</span></span>
          <span style="color:var(--muted)">›</span>
        </button>
        <button class="modecard" data-go="/recently-viewed">
          <span class="ic">🕓</span>
          <span style="flex:1"><span class="t">Recently viewed</span><span class="d">Kept on this device</span></span>
          <span style="color:var(--muted)">›</span>
        </button>
        <button class="modecard" data-go="/store-info">
          <span class="ic">🏪</span>
          <span style="flex:1"><span class="t">Store info</span><span class="d">${h(s?.city || '')} · ${s?.is_open ? 'Open now' : 'Closed'}</span></span>
          <span style="color:var(--muted)">›</span>
        </button>
      </div>

      <p class="demonote">Demo data only. No account, no payment, no real customer details.</p>
    </div>`;

  mount.querySelectorAll('[data-go]').forEach((b) => {
    b.onclick = () => navigate(b.dataset.go);
  });
}

/* ---------- scan / code lookup ----------
   The bottom bar's scanner button. Real detection lives in store mode; for a
   shopper the useful half is the lookup itself, so this takes the SKU or
   barcode printed on the shelf label and jumps to that product. */

export function openLookupSheet() {
  sheet(`
    <h3>Scan or enter a code</h3>
    <p style="color:var(--muted);font-size:.85rem;margin-bottom:16px">Type the SKU or barcode from the shelf label to jump straight to that product.</p>
    <label class="field" style="margin-bottom:14px">
      <span class="lbl">SKU or barcode</span>
      <input class="input" id="code" placeholder="e.g. AML-GHEE-500" autocomplete="off">
    </label>
    <button class="btn lg block" id="go">Find product</button>
  `, {
    onMount(panel, close) {
      const input = panel.querySelector('#code');
      const submit = async () => {
        const code = input.value.trim();
        if (!code) return toast('Enter a code first', 'err');
        try {
          const hit = await api.lookup(code);
          close();
          navigate(`/p/${hit.product_id}`);
        } catch (err) {
          toast(err.status === 404 ? 'No product with that code' : err.message, 'err');
        }
      };
      panel.querySelector('#go').onclick = submit;
      input.addEventListener('keydown', (e) => { if (e.key === 'Enter') submit(); });
    },
  });
}

/* ---------- find everything ---------- */

export async function findView(mount) {
  mount.innerHTML = `
    <div class="wrap" style="padding-top:20px">
      <p class="page-note">
        List what you need and we will check the whole shelf at once. On the parent platform this same question gets asked of every nearby store.
      </p>
      <div class="card pad">
        <div id="rows" class="stack"></div>
        <button class="btn ghost sm" id="add" style="margin-top:10px">+ Add another</button>
      </div>
      <button class="btn lg block" id="go" style="margin-top:14px">Check this store</button>
      <div id="out" style="margin-top:16px"></div>
    </div>`;

  const rows = mount.querySelector('#rows');
  const addRow = (value = '') => {
    rows.appendChild(el(`<div class="row"><input class="input" placeholder="e.g. Basmati rice" value="${h(value)}"><button class="iconbtn" data-del aria-label="Remove">✕</button></div>`));
    rows.lastElementChild.querySelector('[data-del]').onclick = (e) => {
      if (rows.children.length > 1) e.currentTarget.closest('.row').remove();
    };
  };
  ['Basmati rice', 'Toor dal', 'Cow ghee'].forEach(addRow);
  mount.querySelector('#add').onclick = () => addRow();

  mount.querySelector('#go').onclick = async () => {
    const items = [...rows.querySelectorAll('input')].map((i) => i.value.trim()).filter(Boolean);
    const out = mount.querySelector('#out');
    if (!items.length) return toast('Add at least one item', 'err');
    out.innerHTML = skeletonLines(2);
    try {
      const r = await api.checkMany(items);
      out.innerHTML = `
        <div class="card pad" style="background:${r.all_available ? 'var(--ok-bg)' : 'var(--warn-bg)'};border:none;margin-bottom:14px">
          <div style="font-weight:800;color:${r.all_available ? 'var(--ok)' : 'var(--warn)'}">
            ${r.all_available ? '✅ Everything is available here' : `⚠️ ${r.available_count} of ${r.total} available here`}
          </div>
          ${!r.all_available ? '<div style="font-size:.8rem;color:var(--warn);margin-top:4px">The parent platform would widen this search to nearby stores.</div>' : ''}
        </div>
        <div class="stack">${r.items.map((row) => row.product ? `
          <button class="line" data-product="${row.product.id}">
            <div class="thumb">${img(row.product)}</div>
            <div class="meta">
              <span class="sku">${h(row.term)}</span>
              <span class="name">${h(row.product.name)}</span>
              <span style="font-weight:800">${money(row.product.price_from)}</span>
            </div>
            <div style="text-align:right">${statusLine({ status: row.product.status, available: row.product.available })}</div>
          </button>` : `
          <div class="line" style="cursor:default">
            <div class="thumb" style="display:grid;place-items:center;font-size:1.2rem">🚫</div>
            <div class="meta"><span class="sku">${h(row.term)}</span><span class="name">Not stocked here</span></div>
            <span class="badge rejected">None</span>
          </div>`).join('')}</div>`;
      wireProductClicks(out);
    } catch (err) {
      out.innerHTML = errorBox(err.message);
    }
  };
}

/* ---------- store info ---------- */

export async function storeInfoView(mount) {
  const s = state.store;
  if (!s) { mount.innerHTML = `<div class="wrap">${errorBox('Store details unavailable')}</div>`; return; }
  const maps = `https://www.google.com/maps/search/?api=1&query=${s.lat},${s.lng}`;

  mount.innerHTML = `
    <div class="wrap" style="padding-top:16px">
      <div class="card pad">
        <h2 style="font-size:1.25rem">${h(s.name)}</h2>
        <p style="color:var(--muted);font-size:.86rem;margin-top:4px">${h(s.tagline)}</p>
        <div class="row" style="margin-top:12px;gap:14px;flex-wrap:wrap">
          <span style="font-weight:800">★ ${s.rating}</span>
          <span class="badge ${s.is_open ? 'ready' : 'neutral'}">${s.is_open ? 'Open now' : 'Closed'}</span>
          <span style="font-size:.84rem;color:var(--muted)">${h(s.hours_label)}</span>
        </div>
      </div>

      <div class="card pad" style="margin-top:12px">
        <div class="kv"><span class="k">Address</span><span class="v">${h(s.address)}</span></div>
        <div class="kv"><span class="k">Phone</span><span class="v">${h(s.phone)}</span></div>
        <div class="kv"><span class="k">Products available</span><span class="v">${s.products_available}</span></div>
        <div class="kv"><span class="k">Catalogue size</span><span class="v">${s.total_products} products</span></div>
      </div>

      <div class="row" style="margin-top:14px;gap:10px">
        <a class="btn ghost" style="flex:1" href="${maps}" target="_blank" rel="noopener">🧭 Navigate</a>
        <a class="btn ghost" style="flex:1" href="tel:${h(s.phone.replace(/\s/g, ''))}">📞 Call</a>
      </div>
      <button class="btn lg block" id="browse" style="margin-top:10px">View products</button>
    </div>`;

  mount.querySelector('#browse').onclick = () => navigate('/search/');
}
