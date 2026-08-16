import { api, auth } from '../api.js';
import { navigate, refreshStaffBadges, state } from '../state.js';
import {
  barChart, confirmSheet, empty, errorBox, h, money, rankedBars,
  sheet, skeletonLines, statusLine, toast,
} from '../ui.js';

/* ---------- sign in ---------- */

export function staffLoginView(mount) {
  mount.innerHTML = `
    <div class="wrap landing">
      <div class="logo">🏪</div>
      <h1>Store mode</h1>
      <p class="lede">Sign in to manage inventory, reservations and sales for ${h(state.store?.name || 'this store')}.</p>
      <label class="field" style="margin-top:24px">
        <span class="lbl">Staff passcode</span>
        <input class="input" id="pass" type="password" inputmode="numeric" placeholder="••••" autocomplete="off">
      </label>
      <p class="msg" id="msg" style="color:var(--bad);font-size:.82rem;min-height:18px;margin-top:8px"></p>
      <button class="btn lg block" id="go">Enter store mode</button>
      <p class="demonote">Demo passcode: <strong>${h(state.config?.demo_passcode || '2468')}</strong></p>
      <button class="btn ghost block" id="back" style="margin-top:10px">← Back</button>
    </div>`;

  const pass = mount.querySelector('#pass');
  const msg = mount.querySelector('#msg');
  const submit = async () => {
    msg.textContent = '';
    try {
      const { token } = await api.staffLogin(pass.value);
      auth.token = token;
      await refreshStaffBadges();
      navigate('/store/dashboard');
    } catch (err) {
      msg.textContent = err.message;
      pass.select();
    }
  };
  mount.querySelector('#go').onclick = submit;
  pass.onkeydown = (e) => { if (e.key === 'Enter') submit(); };
  mount.querySelector('#back').onclick = () => navigate('/');
  pass.focus();
}

function guard() {
  if (!auth.isStaff) { navigate('/store/login', { replace: true }); return false; }
  return true;
}

/* ---------- dashboard ---------- */

export async function dashboardView(mount) {
  if (!guard()) return;
  mount.innerHTML = `<div class="wrap" style="padding-top:16px"><div id="body">${skeletonLines(4)}</div></div>`;
  const body = mount.querySelector('#body');

  try {
    const o = await api.overview();
    const t = o.today;
    body.innerHTML = `
      <div class="sec-head" style="margin-bottom:12px"><h2>Today</h2>
        <span style="font-size:.78rem;color:var(--muted)">${new Date().toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'short' })}</span>
      </div>
      <div class="tiles">
        <div class="tile accent"><div class="k">Sales</div><div class="v">${money(t.revenue)}</div><div class="sub">${t.orders} order${t.orders === 1 ? '' : 's'}</div></div>
        <div class="tile"><div class="k">Reservations</div><div class="v">${t.reservations}</div><div class="sub">${t.pending_reservations} awaiting you</div></div>
        <div class="tile"><div class="k">Low stock</div><div class="v">${t.low_stock}</div><div class="sub">need restocking</div></div>
        <div class="tile"><div class="k">Out of stock</div><div class="v">${t.out_of_stock}</div><div class="sub">${t.stale_counts} stale counts</div></div>
      </div>

      <div class="sec">
        <div class="sec-head"><h2>Quick actions</h2></div>
        <div class="quickgrid">
          <button class="quick" data-go="/store/scan"><span class="ic">📷</span>Scan</button>
          <button class="quick" data-go="/store/inventory"><span class="ic">📦</span>Inventory</button>
          <button class="quick" data-go="/store/reservations"><span class="ic">🎟️</span>Reservations</button>
          <button class="quick" data-go="/store/analytics"><span class="ic">📈</span>Sales</button>
        </div>
      </div>

      <div class="sec">
        <div class="sec-head"><h2>This week</h2><span style="font-size:.8rem;color:var(--muted)">${money(o.week_revenue)} · ${o.week_orders} orders</span></div>
        <div class="card pad">${barChart(o.trend)}</div>
      </div>

      <div class="sec">
        <div class="sec-head"><h2>Inventory</h2><a class="link" href="#/store/inventory">Manage</a></div>
        <div class="tiles">
          <div class="tile"><div class="k">Products</div><div class="v">${o.inventory.total_products}</div><div class="sub">${o.inventory.total_variants} variants</div></div>
          <div class="tile"><div class="k">Value</div><div class="v" style="font-size:1.15rem">${money(o.inventory.inventory_value)}</div><div class="sub">at retail</div></div>
        </div>
      </div>

      ${o.low_stock.length ? `
        <div class="sec">
          <div class="sec-head"><h2>Needs attention</h2></div>
          <div class="stack">${o.low_stock.slice(0, 5).map((r) => `
            <button class="line" data-variant="${r.variant_id}">
              <div class="thumb">${r.image_url ? `<img src="${h(r.image_url)}" alt="">` : ''}</div>
              <div class="meta"><span class="name">${h(r.product_name)}</span><span class="sku">${h(r.sku)} · ${h(r.label)}</span></div>
              ${statusLine(r)}
            </button>`).join('')}</div>
        </div>` : ''}`;

    body.querySelectorAll('[data-go]').forEach((b) => { b.onclick = () => navigate(b.dataset.go); });
    body.querySelectorAll('[data-variant]').forEach((b) => {
      b.onclick = () => navigate('/store/inventory');
    });
  } catch (err) {
    if (err.status === 401) return navigate('/store/login', { replace: true });
    body.innerHTML = errorBox(err.message, 'retry');
    body.querySelector('#retry').onclick = () => dashboardView(mount);
  }
}

/* ---------- reservations ---------- */

const FILTERS = [
  ['pending', 'Pending'], ['accepted', 'Accepted'], ['ready', 'Ready'],
  ['completed', 'Completed'], ['all', 'All'],
];

export async function reservationsView(mount) {
  if (!guard()) return;
  let filter = 'pending';

  mount.innerHTML = `
    <div class="wrap" style="padding-top:16px">
      <h2 style="margin-bottom:12px">Reservations</h2>
      <div class="chips" id="f"></div>
      <div id="list" style="margin-top:14px">${skeletonLines(3)}</div>
    </div>`;

  const list = mount.querySelector('#list');

  const drawFilters = () => {
    mount.querySelector('#f').innerHTML = FILTERS.map(([k, label]) =>
      `<button class="chip ${filter === k ? 'on' : ''}" data-f="${k}">${label}</button>`).join('');
    mount.querySelectorAll('[data-f]').forEach((b) => {
      b.onclick = () => { filter = b.dataset.f; drawFilters(); load(); };
    });
  };

  async function load() {
    list.innerHTML = skeletonLines(2);
    try {
      const rows = await api.reservations({ status: filter });
      if (!rows.length) {
        list.innerHTML = empty({ icon: '🎟️', title: `No ${filter === 'all' ? '' : filter} reservations`, body: 'New customer reservations land here.' });
        return;
      }
      list.innerHTML = `<div class="stack">${rows.map(card).join('')}</div>`;
      wire();
    } catch (err) {
      if (err.status === 401) return navigate('/store/login', { replace: true });
      list.innerHTML = errorBox(err.message);
    }
  }

  const card = (r) => `
    <div class="card pad">
      <div class="row between" style="align-items:flex-start">
        <div style="min-width:0">
          <div class="row" style="gap:8px"><span class="badge ${h(r.status)}">${h(r.status)}</span>
            <span class="sku" style="font-family:ui-monospace,monospace;font-size:.74rem;color:var(--muted)">${h(r.code)}</span></div>
          <div style="font-weight:800;margin-top:8px">${h(r.customer_name)}</div>
          <div style="font-size:.84rem;color:var(--ink-2)">${h(r.product_name)} · ${h(r.variant_label)}</div>
          <div style="font-size:.8rem;color:var(--muted);margin-top:3px">Qty ${r.quantity} · ${money(r.price * r.quantity)}${
            r.is_open && r.expires_in_minutes !== null ? ` · expires in ${r.expires_in_minutes}m` : ''}</div>
          ${r.phone || r.email ? `<div style="font-size:.78rem;color:var(--muted)">${h(r.phone || r.email)}</div>` : ''}
        </div>
        <div class="thumb" style="width:54px;height:54px;border-radius:10px;overflow:hidden;background:var(--surface-2);flex-shrink:0">
          ${r.image_url ? `<img src="${h(r.image_url)}" alt="" style="width:100%;height:100%;object-fit:cover">` : ''}
        </div>
      </div>
      ${r.status === 'ready' ? `
        <div class="row" style="gap:12px;margin-top:12px;padding-top:12px;border-top:1px solid var(--line-2)">
          <div class="qrbox" style="padding:6px"><img src="/api/reservations/${r.id}/qr.svg" alt="" style="width:76px;height:76px"></div>
          <div style="font-size:.8rem;color:var(--muted)">Customer shows this code at the counter.</div>
        </div>` : ''}
      <div class="row" style="gap:8px;margin-top:12px;flex-wrap:wrap">
        ${r.status === 'pending' ? `<button class="btn sm" data-act="accept" data-id="${r.id}">Accept</button>` : ''}
        ${['pending', 'accepted'].includes(r.status) ? `<button class="btn sm soft" data-act="ready" data-id="${r.id}">Mark ready</button>` : ''}
        ${['accepted', 'ready'].includes(r.status) ? `<button class="btn sm ok" data-act="complete" data-id="${r.id}">Complete pickup</button>` : ''}
        ${r.is_open ? `<button class="btn sm ghost" data-act="reject" data-id="${r.id}">Reject</button>` : ''}
      </div>
    </div>`;

  function wire() {
    list.querySelectorAll('[data-act]').forEach((b) => {
      b.onclick = async () => {
        const { act, id } = b.dataset;
        if (act === 'reject') {
          const yes = await confirmSheet({
            title: 'Reject this reservation?',
            body: 'The customer is told and the stock goes back on sale.',
            confirmLabel: 'Reject', danger: true,
          });
          if (!yes) return;
        }
        b.disabled = true;
        try {
          await api.reservationAction(id, act);
          toast({ accept: 'Reservation accepted', ready: 'Marked ready for pickup',
                   complete: 'Pickup completed — stock updated', reject: 'Reservation rejected' }[act], 'ok');
          await refreshStaffBadges();
          load();
        } catch (err) {
          b.disabled = false;
          toast(err.message, 'err');
        }
      };
    });
  }

  drawFilters();
  load();
}

/* ---------- inventory ---------- */

export async function inventoryView(mount) {
  if (!guard()) return;
  let q = '', status = 'all', sort = 'name';

  mount.innerHTML = `
    <div class="wrap" style="padding-top:16px">
      <div class="row between" style="margin-bottom:12px">
        <h2>Inventory</h2>
        <button class="btn sm soft" id="scan">📷 Scan</button>
      </div>
      <div class="searchbox"><span class="ic">🔍</span><input id="q" type="search" placeholder="Search name, SKU or barcode"></div>
      <div class="chips" style="margin-top:10px" id="f"></div>
      <div class="row" style="margin-top:10px;gap:8px">
        <select class="input" id="sort" style="max-width:190px">
          <option value="name">Sort: name</option>
          <option value="stock_low">Sort: lowest stock</option>
          <option value="stock_high">Sort: highest stock</option>
          <option value="value">Sort: stock value</option>
          <option value="updated">Sort: least recently counted</option>
        </select>
      </div>
      <div id="list" style="margin-top:14px">${skeletonLines(5)}</div>
    </div>`;

  mount.querySelector('#scan').onclick = () => navigate('/store/scan');
  const list = mount.querySelector('#list');

  const drawFilters = () => {
    mount.querySelector('#f').innerHTML = [['all', 'All'], ['available', '🟢 In stock'], ['limited', '🟡 Low'], ['out', '🔴 Out']]
      .map(([k, l]) => `<button class="chip ${status === k ? 'on' : ''}" data-f="${k}">${l}</button>`).join('');
    mount.querySelectorAll('[data-f]').forEach((b) => {
      b.onclick = () => { status = b.dataset.f; drawFilters(); load(); };
    });
  };

  let timer;
  mount.querySelector('#q').addEventListener('input', (e) => {
    q = e.target.value;
    clearTimeout(timer); timer = setTimeout(load, 220);
  });
  mount.querySelector('#sort').onchange = (e) => { sort = e.target.value; load(); };

  async function load() {
    try {
      const rows = await api.inventory({ q, status, sort });
      if (!rows.length) {
        list.innerHTML = empty({ icon: '📦', title: 'Nothing matches', body: 'Try a different search or filter.' });
        return;
      }
      list.innerHTML = `
        <div class="tablewrap">
          <table>
            <thead><tr><th>Product</th><th>SKU</th><th>Stock</th><th>Status</th><th></th></tr></thead>
            <tbody>${rows.map((r) => `
              <tr>
                <td><div style="font-weight:700">${h(r.product_name)}</div><div style="font-size:.75rem;color:var(--muted)">${h(r.label)}</div></td>
                <td style="font-family:ui-monospace,monospace;font-size:.78rem">${h(r.sku)}</td>
                <td><strong>${r.on_hand}</strong>${r.reserved ? ` <span style="color:var(--muted);font-size:.76rem">(${r.reserved} held)</span>` : ''}</td>
                <td>${statusLine(r, { showUnits: false })}</td>
                <td><button class="btn sm ghost" data-adj="${r.variant_id}">Update</button></td>
              </tr>`).join('')}</tbody>
          </table>
        </div>`;
      list.querySelectorAll('[data-adj]').forEach((b) => {
        b.onclick = () => {
          const row = rows.find((r) => r.variant_id === Number(b.dataset.adj));
          openStockSheet(row, load);
        };
      });
    } catch (err) {
      if (err.status === 401) return navigate('/store/login', { replace: true });
      list.innerHTML = errorBox(err.message);
    }
  }

  drawFilters();
  load();
}

/** Shared by the inventory table and the scanner result. */
export function openStockSheet(row, onDone) {
  sheet(`
    <h3>${h(row.product_name)}</h3>
    <p style="color:var(--muted);font-size:.84rem;margin-bottom:14px">${h(row.label)} · ${h(row.sku)}</p>
    <div class="card pad" style="margin-bottom:14px">
      <div class="kv"><span class="k">On hand</span><span class="v">${row.on_hand}</span></div>
      <div class="kv"><span class="k">Held for customers</span><span class="v">${row.reserved}</span></div>
      <div class="kv"><span class="k">Available</span><span class="v">${row.available}</span></div>
      <div class="kv"><span class="k">Last counted</span><span class="v">${h(row.freshness.label)}</span></div>
    </div>
    <div class="row" style="gap:8px;margin-bottom:12px">
      <select class="input" id="kind" style="flex:0 0 130px">
        <option value="add">Add stock</option>
        <option value="remove">Remove</option>
        <option value="adjust">Set count</option>
      </select>
      <input class="input" id="qty" type="number" min="0" value="1" style="flex:1">
    </div>
    <input class="input" id="note" placeholder="Note (optional) — e.g. delivery, damage" style="margin-bottom:14px">
    <button class="btn lg block" id="apply">Apply change</button>
    <button class="btn ghost block" id="recount" style="margin-top:8px">Mark as re-counted now</button>
  `, {
    onMount(panel, close) {
      panel.querySelector('#apply').onclick = async (e) => {
        e.currentTarget.disabled = true;
        try {
          const res = await api.moveStock(
            row.variant_id,
            panel.querySelector('#kind').value,
            Number(panel.querySelector('#qty').value),
            panel.querySelector('#note').value.trim()
          );
          close();
          toast(res.notified ? `Stock updated — ${res.notified} customer(s) notified` : 'Stock updated', 'ok');
          onDone && onDone();
        } catch (err) {
          e.currentTarget.disabled = false;
          toast(err.message, 'err');
        }
      };
      panel.querySelector('#recount').onclick = async () => {
        try {
          await api.touchStock(row.variant_id);
          close();
          toast('Marked as counted just now', 'ok');
          onDone && onDone();
        } catch (err) { toast(err.message, 'err'); }
      };
    },
  });
}

/* ---------- scanner ---------- */

export async function scanView(mount) {
  if (!guard()) return;

  const supported = 'BarcodeDetector' in window;
  mount.innerHTML = `
    <div class="wrap" style="padding-top:16px">
      <h2>Scan product</h2>
      <p style="color:var(--muted);font-size:.85rem;margin:6px 0 14px">
        Point the camera at a barcode, or type a code below.
      </p>
      <div class="scanview" id="view">
        <video id="vid" playsinline muted></video>
        <div class="reticle"></div>
      </div>
      <div id="camnote" style="font-size:.78rem;color:var(--muted);margin-top:8px"></div>

      <div class="card pad" style="margin-top:14px">
        <label class="field">
          <span class="lbl">Barcode or SKU</span>
          <input class="input" id="code" placeholder="e.g. NIK-AM-092 or 8901234500025" autocomplete="off">
        </label>
        <button class="btn block" id="go" style="margin-top:10px">Look up</button>
        <div class="chips" style="margin-top:10px">
          <button class="chip" data-demo="NIK-AM-092">Demo: Nike Air Max</button>
          <button class="chip" data-demo="8901234500070">Demo: Samsung charger</button>
          <button class="chip" data-demo="RSV">Demo: reservation code</button>
        </div>
      </div>
      <div id="out" style="margin-top:14px"></div>
    </div>`;

  const out = mount.querySelector('#out');
  const codeInput = mount.querySelector('#code');
  const camnote = mount.querySelector('#camnote');
  const video = mount.querySelector('#vid');
  let stream = null, stopped = false;

  const stop = () => {
    stopped = true;
    if (stream) stream.getTracks().forEach((t) => t.stop());
  };
  // Leaving the screen must release the camera, or the light stays on.
  window.addEventListener('hashchange', stop, { once: true });

  async function lookup(code) {
    if (!code) return;
    out.innerHTML = skeletonLines(1);

    // A reservation code at the scanner means a customer is collecting.
    if (/^RSV-/i.test(code)) return lookupReservation(code);

    try {
      const v = await api.lookup(code);
      const inv = await api.inventory({ q: v.sku });
      const row = inv.find((r) => r.variant_id === v.id) || {
        ...v, variant_id: v.id, product_name: v.product_name,
        on_hand: v.stock.on_hand, reserved: v.stock.reserved,
        available: v.stock.available, freshness: v.stock.freshness, status: v.stock.status,
      };
      out.innerHTML = `
        <div class="card pad">
          <div class="row" style="gap:12px">
            <div class="thumb" style="width:64px;height:64px;border-radius:10px;overflow:hidden;background:var(--surface-2)">
              ${v.image_url ? `<img src="${h(v.image_url)}" alt="" style="width:100%;height:100%;object-fit:cover">` : ''}
            </div>
            <div style="flex:1;min-width:0">
              <div style="font-weight:800">✅ ${h(v.product_name)}</div>
              <div style="font-size:.8rem;color:var(--muted)">${h(v.label)} · ${h(v.sku)}</div>
              <div style="font-weight:800;margin-top:4px">${money(v.price)}</div>
            </div>
            <div style="text-align:right">${statusLine(row)}</div>
          </div>
          <div class="row" style="gap:8px;margin-top:12px">
            <button class="btn sm" id="add">+ Add stock</button>
            <button class="btn sm ghost" id="rem">− Remove</button>
            <button class="btn sm soft" id="view">View</button>
          </div>
        </div>`;
      out.querySelector('#add').onclick = () => openStockSheet(row, () => lookup(code));
      out.querySelector('#rem').onclick = () => openStockSheet(row, () => lookup(code));
      out.querySelector('#view').onclick = () => navigate(`/p/${v.product_id}`);
    } catch (err) {
      out.innerHTML = err.status === 404
        ? empty({ icon: '🤷', title: 'No product matches that code', body: `Nothing in this store uses "${code}".` })
        : errorBox(err.message);
    }
  }

  async function lookupReservation(code) {
    try {
      const r = await api.reservationByCode(code);
      out.innerHTML = `
        <div class="card pad">
          <div class="row between"><span class="badge ${h(r.status)}">${h(r.status)}</span><span class="rescode" style="font-size:.95rem">${h(r.code)}</span></div>
          <div style="font-weight:800;margin-top:10px">${h(r.customer_name)}</div>
          <div style="font-size:.85rem;color:var(--ink-2)">${h(r.product_name)} · ${h(r.variant_label)} · qty ${r.quantity}</div>
          ${['accepted', 'ready'].includes(r.status)
            ? `<button class="btn ok block" id="done" style="margin-top:12px">Complete pickup</button>`
            : `<p style="font-size:.82rem;color:var(--muted);margin-top:10px">This reservation is ${h(r.status)} — nothing to hand over.</p>`}
        </div>`;
      const done = out.querySelector('#done');
      if (done) done.onclick = async () => {
        done.disabled = true;
        try {
          await api.reservationAction(r.id, 'complete');
          toast('Pickup completed — stock updated', 'ok');
          lookupReservation(code);
        } catch (err) { done.disabled = false; toast(err.message, 'err'); }
      };
    } catch (err) {
      out.innerHTML = err.status === 404
        ? empty({ icon: '🎟️', title: 'No reservation with that code', body: 'Check the code and try again.' })
        : errorBox(err.message);
    }
  }

  mount.querySelector('#go').onclick = () => lookup(codeInput.value.trim());
  codeInput.onkeydown = (e) => { if (e.key === 'Enter') lookup(codeInput.value.trim()); };
  mount.querySelectorAll('[data-demo]').forEach((b) => {
    b.onclick = async () => {
      let code = b.dataset.demo;
      if (code === 'RSV') {
        // Grab a live reservation so the demo always has something real to open.
        try {
          const rows = await api.reservations({ status: 'all' });
          const open = rows.find((r) => ['accepted', 'ready'].includes(r.status)) || rows[0];
          code = open ? open.code : 'RSV-00000';
        } catch { code = 'RSV-00000'; }
      }
      codeInput.value = code;
      lookup(code);
    };
  });

  // Camera. Detection needs BarcodeDetector, which most desktop browsers do
  // not ship -- so the preview is best-effort and the manual field above is
  // always the reliable path.
  if (!navigator.mediaDevices?.getUserMedia) {
    camnote.textContent = 'No camera available on this device — use the code field below.';
    mount.querySelector('#view').style.display = 'none';
    return;
  }
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
    if (stopped) return stream.getTracks().forEach((t) => t.stop());
    video.srcObject = stream;
    await video.play();

    if (!supported) {
      camnote.textContent = 'This browser cannot decode barcodes from video — type the code below instead.';
      return;
    }
    camnote.textContent = 'Scanning…';
    const detector = new BarcodeDetector({
      formats: ['ean_13', 'ean_8', 'code_128', 'code_39', 'upc_a', 'upc_e', 'qr_code'],
    });
    const tick = async () => {
      if (stopped || !document.body.contains(video)) return;
      try {
        const found = await detector.detect(video);
        if (found.length) {
          stop();
          camnote.textContent = `Detected ${found[0].rawValue}`;
          codeInput.value = found[0].rawValue;
          lookup(found[0].rawValue);
          return;
        }
      } catch { /* a dropped frame is not worth reporting */ }
      requestAnimationFrame(tick);
    };
    tick();
  } catch {
    camnote.textContent = 'Camera permission denied — use the code field below.';
    mount.querySelector('#view').style.display = 'none';
  }
}

/* ---------- analytics ---------- */

export async function analyticsView(mount) {
  if (!guard()) return;
  mount.innerHTML = `<div class="wrap" style="padding-top:16px"><h2 style="margin-bottom:14px">Sales & inventory</h2><div id="body">${skeletonLines(4)}</div></div>`;
  const body = mount.querySelector('#body');

  try {
    const o = await api.overview();
    body.innerHTML = `
      <div class="tiles">
        <div class="tile accent"><div class="k">Today</div><div class="v">${money(o.today.revenue)}</div><div class="sub">${o.today.orders} orders</div></div>
        <div class="tile"><div class="k">This week</div><div class="v">${money(o.week_revenue)}</div><div class="sub">${o.week_orders} orders</div></div>
        <div class="tile"><div class="k">Stock value</div><div class="v" style="font-size:1.15rem">${money(o.inventory.inventory_value)}</div><div class="sub">${o.inventory.total_variants} variants</div></div>
        <div class="tile"><div class="k">Open holds</div><div class="v">${o.today.reservations}</div><div class="sub">${o.today.pending_reservations} pending</div></div>
      </div>

      <div class="sec">
        <div class="sec-head"><h2>Sales trend</h2><span style="font-size:.78rem;color:var(--muted)">last 7 days</span></div>
        <div class="card pad">${barChart(o.trend)}</div>
      </div>

      <div class="sec">
        <div class="sec-head"><h2>Top products</h2></div>
        <div class="card pad">${o.top_products.length ? rankedBars(o.top_products) : empty({ icon: '📊', title: 'No sales yet' })}</div>
      </div>

      <div class="sec">
        <div class="sec-head"><h2>Low stock</h2><a class="link" href="#/store/inventory">Manage</a></div>
        <div class="stack">${o.low_stock.length ? o.low_stock.map((r) => `
          <div class="line" style="cursor:default">
            <div class="thumb">${r.image_url ? `<img src="${h(r.image_url)}" alt="">` : ''}</div>
            <div class="meta"><span class="name">${h(r.product_name)}</span><span class="sku">${h(r.sku)}</span></div>
            ${statusLine(r)}
          </div>`).join('') : empty({ icon: '✅', title: 'Everything is well stocked' })}</div>
      </div>

      <div class="sec">
        <div class="sec-head"><h2>Recent stock movements</h2></div>
        <div class="tablewrap"><table>
          <thead><tr><th>When</th><th>Product</th><th>Change</th><th>By</th></tr></thead>
          <tbody>${o.recent_movements.map((m) => `
            <tr>
              <td style="font-size:.78rem;color:var(--muted)">${h((m.created_at || '').slice(5, 16))}</td>
              <td>${h(m.product_name)}<div style="font-size:.72rem;color:var(--muted)">${h(m.sku)}</div></td>
              <td><span class="badge neutral">${h(m.kind)}</span> ${m.quantity}</td>
              <td style="font-size:.78rem;color:var(--muted)">${h(m.actor)}</td>
            </tr>`).join('')}</tbody>
        </table></div>
      </div>`;
  } catch (err) {
    if (err.status === 401) return navigate('/store/login', { replace: true });
    body.innerHTML = errorBox(err.message);
  }
}
