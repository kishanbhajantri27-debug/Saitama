import { api, ApiError } from '../api.js';
import { navigate, refreshCustomerBadges, state } from '../state.js';
import {
  barChart, confirmSheet, el, empty, errorBox, h, money, sheet,
  skeletonGrid, skeletonLines, staleWarning, statusLine, toast,
} from '../ui.js';

const SEARCH_IDEAS = ['Nike shoes', 'Samsung charger', 'Black shirt', 'Notebook', 'Bluetooth headphones'];

const img = (p) => p.image_url
  ? `<img src="${h(p.image_url)}" alt="${h(p.name || p.product_name || '')}" loading="lazy">`
  : '';

/* ---------- shared pieces ---------- */

export function productCard(p) {
  const saved = state.wishlistIds.has(p.id);
  return `
    <button class="prod" data-product="${p.id}">
      <div class="thumb">
        ${img(p)}
        <span class="heartbtn" data-heart="${p.id}" role="button" aria-label="${saved ? 'Remove from' : 'Add to'} wishlist">${saved ? '❤️' : '🤍'}</span>
      </div>
      <div class="body">
        <span class="brand">${h(p.brand || '')}</span>
        <span class="name">${h(p.name)}</span>
        ${p.rating ? `<span class="rate">★ ${p.rating} (${p.rating_count})</span>` : ''}
        <span class="price">${money(p.price_from)}</span>
        ${statusLine({ ...p, status: p.status, available: p.available }, { showUnits: true })}
      </div>
    </button>`;
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

/** One place decides what clicking a card or a heart does. */
export function wireProductClicks(root) {
  root.querySelectorAll('[data-product]').forEach((node) => {
    node.addEventListener('click', async (e) => {
      const heart = e.target.closest('[data-heart]');
      if (heart) {
        e.stopPropagation();
        await toggleWishlist(Number(heart.dataset.heart), heart);
        return;
      }
      navigate(`/p/${node.dataset.product}`);
    });
  });
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

/* ---------- home ---------- */

export async function homeView(mount) {
  mount.innerHTML = `
    <div class="wrap">
      <div style="padding:16px 0 6px">
        <h2 style="font-size:1.3rem">Hi there 👋</h2>
        <p style="color:var(--muted);font-size:.88rem;margin-top:3px">Find what you need at ${h(state.store?.name || 'the store')}.</p>
      </div>
      <div class="searchbox" style="margin-top:12px">
        <span class="ic">🔍</span>
        <input id="q" type="search" placeholder="What are you looking for?" autocomplete="off">
      </div>
      <div class="chips" style="margin-top:10px" id="ideas">
        ${SEARCH_IDEAS.map((s) => `<button class="chip" data-idea="${h(s)}">${h(s)}</button>`).join('')}
      </div>
      <button class="btn lg block" id="check" style="margin-top:14px">✅ Check availability of a list</button>
      <div id="body">${skeletonGrid(4)}</div>
    </div>`;

  const q = mount.querySelector('#q');
  q.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && q.value.trim()) navigate(`/search/${encodeURIComponent(q.value.trim())}`);
  });
  mount.querySelectorAll('[data-idea]').forEach((b) => {
    b.onclick = () => navigate(`/search/${encodeURIComponent(b.dataset.idea)}`);
  });
  mount.querySelector('#check').onclick = () => navigate('/find');

  const body = mount.querySelector('#body');
  try {
    const [popular, wishlist] = await Promise.all([
      api.products({ sort: 'popular' }),
      api.wishlist(state.me.id),
    ]);
    state.wishlistIds = new Set(wishlist.map((p) => p.id));

    const availableNow = popular.filter((p) => p.status === 'available');
    const recommended = [...popular].sort((a, b) => b.rating - a.rating).slice(0, 6);

    body.innerHTML = `
      ${section('🔥 Popular right now', `<div class="hlist">${popular.slice(0, 8).map(productCard).join('')}</div>`)}
      ${section('🟢 Available now', availableNow.length
        ? `<div class="prodgrid">${availableNow.slice(0, 6).map(productCard).join('')}</div>`
        : empty({ icon: '🫙', title: 'Nothing in stock right now', body: 'Check back shortly.' }))}
      ${section('⭐ Recommended for you', `<div class="hlist">${recommended.map(productCard).join('')}</div>`)}
      ${wishlist.length ? section('❤️ Your wishlist',
        `<div class="hlist">${wishlist.map(productCard).join('')}</div>`,
        '<a class="link" href="#/wishlist">See all</a>') : ''}
      ${section('🏪 Store', storeCard())}`;

    wireProductClicks(body);
    const sc = body.querySelector('#storecard');
    if (sc) sc.onclick = () => navigate('/store-info');
  } catch (err) {
    body.innerHTML = errorBox(err.message, 'retry');
    body.querySelector('#retry').onclick = () => homeView(mount);
  }
}

const section = (title, inner, link = '') => `
  <div class="sec">
    <div class="sec-head"><h2>${title}</h2>${link}</div>
    ${inner}
  </div>`;

function storeCard() {
  const s = state.store;
  if (!s) return '';
  return `
    <button class="modecard" id="storecard">
      <span class="ic">🏪</span>
      <span style="flex:1">
        <span class="t">${h(s.name)}</span>
        <span class="d">★ ${s.rating} · ${h(s.city)} · ${s.is_open ? 'Open now' : 'Closed'} · ${h(s.hours_label)}</span>
      </span>
      <span style="color:var(--muted)">›</span>
    </button>`;
}

/* ---------- search ---------- */

export async function searchView(mount, term = '') {
  mount.innerHTML = `
    <div class="wrap">
      <div style="padding:14px 0 0" class="searchbox">
        <span class="ic">🔍</span>
        <input id="q" type="search" placeholder="What are you looking for?" value="${h(term)}" autocomplete="off">
        <button class="clr" id="clr" aria-label="Clear">✕</button>
      </div>
      <div class="chips" style="margin-top:12px" id="filters"></div>
      <div id="count" style="font-size:.8rem;color:var(--muted);margin:10px 2px"></div>
      <div id="results">${skeletonLines(4)}</div>
    </div>`;

  const q = mount.querySelector('#q');
  const results = mount.querySelector('#results');
  const count = mount.querySelector('#count');
  let filter = 'all';
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
    mount.innerHTML = `
      <div class="wrap" style="padding-top:14px">
        <div class="hero">${img(product)}</div>

        <div class="stack" style="margin-top:16px;gap:8px">
          <span class="brand" style="font-size:.72rem;font-weight:800;color:var(--muted);text-transform:uppercase;letter-spacing:.05em">${h(product.brand)}</span>
          <h2 style="font-size:1.3rem">${h(product.name)}</h2>
          ${product.rating ? `<div style="font-size:.84rem;color:var(--muted);font-weight:600">★ ${product.rating} · ${product.rating_count} ratings</div>` : ''}
          <div class="price-lg">${money(selected.price)}</div>
          ${statusLine(s)}
          ${staleWarning(s)}
        </div>

        <p style="color:var(--ink-2);font-size:.89rem;margin-top:14px">${h(product.description)}</p>

        <div class="sec">
          <div class="sec-head"><h2>Options</h2></div>
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
        </div>

        <div class="sec">
          <div class="sec-head"><h2>Details</h2></div>
          <div class="card pad">
            <div class="kv"><span class="k">SKU</span><span class="v">${h(selected.sku)}</span></div>
            <div class="kv"><span class="k">Barcode</span><span class="v">${h(selected.barcode || '—')}</span></div>
            <div class="kv"><span class="k">Category</span><span class="v">${h(product.category)}</span></div>
            <div class="kv"><span class="k">In store</span><span class="v">${h(state.store?.name || '')}, ${h(state.store?.city || '')}</span></div>
            <div class="kv"><span class="k">Stock checked</span><span class="v">${h(s.freshness.label)}</span></div>
          </div>
        </div>
      </div>

      <div class="stickybar">
        <button class="btn ghost" id="wish" style="flex:0 0 52px" aria-label="Wishlist">${saved ? '❤️' : '🤍'}</button>
        ${s.available > 0
          ? `<button class="btn lg" id="reserve">Reserve now</button>`
          : `<button class="btn lg soft" id="notify">🔔 Notify me when back</button>`}
      </div>`;

    mount.querySelectorAll('[data-var]').forEach((b) => {
      b.onclick = () => {
        selected = product.variants.find((v) => v.id === Number(b.dataset.var));
        render();
      };
    });

    mount.querySelector('#wish').onclick = async (e) => {
      await toggleWishlist(product.id, null);
      e.currentTarget.textContent = state.wishlistIds.has(product.id) ? '❤️' : '🤍';
    };

    const reserveBtn = mount.querySelector('#reserve');
    if (reserveBtn) reserveBtn.onclick = () => openReserveSheet(product, selected);

    const notifyBtn = mount.querySelector('#notify');
    if (notifyBtn) notifyBtn.onclick = async () => {
      try {
        await api.notifyMe(state.me.id, selected.id);
        toast('We will let you know when it is back', 'ok');
      } catch (err) { toast(err.message, 'err'); }
    };
  };

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
  ready: { icon: '🟢', title: 'Ready for pickup', body: 'Show this code at the counter to collect your item.' },
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

        ${['accepted', 'ready', 'pending'].includes(r.status) ? `
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
  mount.innerHTML = `<div class="wrap" style="padding-top:16px"><h2 style="margin-bottom:14px">Your reservations</h2><div id="list">${skeletonLines(3)}</div></div>`;
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
  mount.innerHTML = `<div class="wrap" style="padding-top:16px">
      <h2 style="margin-bottom:6px">Your wishlist</h2>
      <p style="color:var(--muted);font-size:.85rem;margin-bottom:14px">We flag these the moment they are back on the shelf.</p>
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

/* ---------- find everything ---------- */

export async function findView(mount) {
  mount.innerHTML = `
    <div class="wrap" style="padding-top:16px">
      <h2>Find everything</h2>
      <p style="color:var(--muted);font-size:.86rem;margin:6px 0 16px">
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
    rows.appendChild(el(`<div class="row"><input class="input" placeholder="e.g. Nike shoes" value="${h(value)}"><button class="iconbtn" data-del aria-label="Remove">✕</button></div>`));
    rows.lastElementChild.querySelector('[data-del]').onclick = (e) => {
      if (rows.children.length > 1) e.currentTarget.closest('.row').remove();
    };
  };
  ['Nike shoes', 'Black jeans', 'Backpack'].forEach(addRow);
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
