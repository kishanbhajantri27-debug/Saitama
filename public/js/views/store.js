import { api, auth } from '../api.js';
import { may, navigate, refreshStaffBadges, state } from '../state.js';
import {
  barChart, confirmSheet, empty, errorBox, h, money, rankedBars,
  sheet, skeletonLines, statusLine, timeline, toast,
} from '../ui.js';
import { svgIcon } from '../icons.js';

/* ---------- sign in ---------- */

// Demo roles. No passwords here -- the client never learns a credential.
// Tapping one asks the server for a demo session, which it grants only while
// DEMO_MODE is on.
const DEMO_ROLES = [
  ['owner', svgIcon('crown'), 'Owner', 'Full access, including staff and reset'],
  ['manager', svgIcon('bag'), 'Manager', 'Stock-takes, rejections, analytics'],
  ['staff', svgIcon('wrench'), 'Staff', 'Counter work: stock moves and pickups'],
];

export function staffLoginView(mount) {
  mount.innerHTML = `
    <div class="wrap landing">
      <div class="logo">${svgIcon('store')}</div>
      <h1>Store sign-in</h1>
      <p class="lede">Manage inventory, reservations and sales for ${h(state.store?.name || 'this store')}.</p>

      <label class="field" style="margin-top:22px">
        <span class="lbl">Username</span>
        <input class="input" id="user" type="text" autocomplete="username" placeholder="owner">
      </label>
      <label class="field" style="margin-top:10px">
        <span class="lbl">Password</span>
        <input class="input" id="pass" type="password" autocomplete="current-password" placeholder="••••••••">
      </label>
      <p class="msg" id="msg" style="color:var(--bad);font-size:.82rem;min-height:18px;margin-top:8px"></p>
      <button class="btn lg block" id="go">Sign in</button>

      ${state.config?.demo_mode ? `
        <p class="demonote" style="margin-top:20px">Or explore as a demo role — each one sees a different store</p>
        <div class="stack" style="gap:8px;margin-top:8px">
          ${DEMO_ROLES.map(([role, icon, label, blurb]) => `
            <button class="modecard" data-demo="${h(role)}">
              <span class="ic">${icon}</span>
              <span style="flex:1">
                <span class="t">${h(label)}</span>
                <span class="d">${h(blurb)}</span>
              </span>
              <span style="color:var(--muted)">›</span>
            </button>`).join('')}
        </div>` : ''}
      <button class="btn ghost block" id="back" style="margin-top:14px">${svgIcon('chevron-left')} Back</button>
    </div>`;

  const user = mount.querySelector('#user');
  const pass = mount.querySelector('#pass');
  const msg = mount.querySelector('#msg');

  const apply = async (res) => {
    auth.token = res.token;
    state.user = res.user;
    state.permissions = new Set(res.permissions);
    await refreshStaffBadges();
    navigate('/store/dashboard');
  };

  const submit = async () => {
    msg.textContent = '';
    try {
      const res = await api.staffLogin(user.value, pass.value);
      await apply(res);
    } catch (err) {
      msg.textContent = err.message;
      pass.select();
    }
  };

  mount.querySelector('#go').onclick = () => submit();
  pass.onkeydown = (e) => { if (e.key === 'Enter') submit(); };
  user.onkeydown = (e) => { if (e.key === 'Enter') pass.focus(); };
  mount.querySelector('#back').onclick = () => navigate('/');
  mount.querySelectorAll('[data-demo]').forEach((b) => {
    b.onclick = async () => {
      msg.textContent = '';
      try { await apply(await api.demoLogin(b.dataset.demo)); }
      catch (err) { msg.textContent = err.message; }
    };
  });
  user.focus();
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
    // A clerk cannot see takings, so the dashboard is assembled from whatever
    // this role is allowed to read rather than failing whole. Asking for the
    // sales figures and catching the 403 would work too, but deliberately not
    // requesting them is the honest version.
    const seesMoney = may('analytics.view');
    const o = seesMoney
      ? await api.overview()
      : { today: null, inventory: await api.inventorySummary(), low_stock: [], trend: [] };
    const t = o.today;

    body.innerHTML = `
      <div class="sec-head" style="margin-bottom:12px"><h2>Today</h2>
        <span style="font-size:.78rem;color:var(--muted)">${new Date().toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'short' })}</span>
      </div>
      <div class="tiles">
        ${seesMoney ? `
          <div class="tile accent"><div class="k">Sales</div><div class="v">${money(t.revenue)}</div><div class="sub">${t.orders} order${t.orders === 1 ? '' : 's'}</div></div>
          <div class="tile"><div class="k">Reservations</div><div class="v">${t.reservations}</div><div class="sub">${t.pending_reservations} awaiting you</div></div>
          <div class="tile"><div class="k">Low stock</div><div class="v">${t.low_stock}</div><div class="sub">need restocking</div></div>
          <div class="tile"><div class="k">Out of stock</div><div class="v">${t.out_of_stock}</div><div class="sub">${t.stale_counts} stale counts</div></div>
        ` : `
          <div class="tile accent"><div class="k">Awaiting you</div><div class="v">${state.pendingReservations}</div><div class="sub">reservations to action</div></div>
          <div class="tile"><div class="k">Low stock</div><div class="v">${o.inventory.low_stock}</div><div class="sub">need restocking</div></div>
          <div class="tile"><div class="k">Out of stock</div><div class="v">${o.inventory.out_of_stock}</div><div class="sub">of ${o.inventory.total_variants} lines</div></div>
          <div class="tile"><div class="k">Stale counts</div><div class="v">${o.inventory.stale}</div><div class="sub">worth re-checking</div></div>
        `}
      </div>

      <div class="sec">
        <div class="sec-head"><h2>Quick actions</h2></div>
        <div class="quickgrid">
          <button class="quick" data-go="/store/scan"><span class="ic">${svgIcon('scan')}</span>Scan</button>
          <button class="quick" data-go="/store/inventory"><span class="ic">${svgIcon('box')}</span>Inventory</button>
          <button class="quick" data-go="/store/reservations"><span class="ic">${svgIcon('ticket')}</span>Reservations</button>
          ${may('analytics.view') ? `<button class="quick" data-go="/store/analytics"><span class="ic">${svgIcon('chart-line')}</span>Sales</button>` : ''}
          ${may('inventory.history.view') ? `<button class="quick" data-go="/store/history"><span class="ic">${svgIcon('clock')}</span>History</button>` : ''}
          ${may('audit.view') ? `<button class="quick" data-go="/store/audit"><span class="ic">${svgIcon('shield')}</span>Audit</button>` : ''}
          ${may('settings.view') ? `<button class="quick" data-go="/store/settings"><span class="ic">${svgIcon('gear')}</span>Settings</button>` : ''}
        </div>
      </div>

      ${seesMoney ? `
        <div class="sec">
          <div class="sec-head"><h2>This week</h2><span style="font-size:.8rem;color:var(--muted)">${money(o.week_revenue)} · ${o.week_orders} orders</span></div>
          <div class="card pad">${barChart(o.trend)}</div>
        </div>` : ''}

      <div class="sec">
        <div class="sec-head"><h2>Inventory</h2><a class="link" href="#/store/inventory">Manage</a></div>
        <div class="tiles">
          <div class="tile"><div class="k">Products</div><div class="v">${o.inventory.total_products}</div><div class="sub">${o.inventory.total_variants} variants</div></div>
          ${seesMoney ? `<div class="tile"><div class="k">Value</div><div class="v" style="font-size:1.15rem">${money(o.inventory.inventory_value)}</div><div class="sub">at retail</div></div>` : ''}
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
  ['pending', 'Pending'], ['accepted', 'Accepted'], ['ready_for_pickup', 'Ready'],
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
        list.innerHTML = empty({ icon: svgIcon('ticket'), title: `No ${filter === 'all' ? '' : filter} reservations`, body: 'New customer reservations land here.' });
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
          <div class="row" style="gap:8px"><span class="badge ${h(r.status)}">${h(r.status.replace(/_/g, " "))}</span>
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
      ${r.status === 'ready_for_pickup' ? `
        <div class="row" style="gap:12px;margin-top:12px;padding-top:12px;border-top:1px solid var(--line-2)">
          <div class="qrbox" style="padding:6px"><img src="/api/reservations/${r.id}/qr.svg" alt="" style="width:76px;height:76px"></div>
          <div style="font-size:.8rem;color:var(--muted)">Customer shows this code at the counter.</div>
        </div>` : ''}
      <div class="row" style="gap:8px;margin-top:12px;flex-wrap:wrap">
        ${r.status === 'pending' ? `<button class="btn sm" data-act="accept" data-id="${r.id}">Accept</button>` : ''}
        ${['pending', 'accepted'].includes(r.status) ? `<button class="btn sm soft" data-act="ready" data-id="${r.id}">Mark ready</button>` : ''}
        ${['accepted', 'ready_for_pickup'].includes(r.status) ? `<button class="btn sm ok" data-act="complete" data-id="${r.id}">Complete pickup</button>` : ''}
        ${r.is_open && may('reservation.reject')
          ? `<button class="btn sm ghost" data-act="reject" data-id="${r.id}">Reject</button>` : ''}
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
        <div class="row" style="gap:8px">
          ${may('product.create') ? '<button class="btn sm" id="add">+ Add</button>' : ''}
          <button class="btn sm soft" id="scan">${svgIcon('scan')} Scan</button>
        </div>
      </div>
      <div class="searchbox"><span class="ic">${svgIcon('search')}</span><input id="q" type="search" placeholder="Search name, SKU or barcode"></div>
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
  const addBtn = mount.querySelector('#add');
  if (addBtn) addBtn.onclick = () => openProductSheet(null, load);
  const list = mount.querySelector('#list');

  const drawFilters = () => {
    mount.querySelector('#f').innerHTML = [['all', 'All'], ['available', `${svgIcon('dot-ok')} In stock`], ['limited', `${svgIcon('dot-warn')} Low`], ['out', `${svgIcon('dot-bad')} Out`]]
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
        list.innerHTML = empty({ icon: svgIcon('box'), title: 'Nothing matches', body: 'Try a different search or filter.' });
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
                <td style="white-space:nowrap">
                  <button class="btn sm ghost" data-adj="${r.variant_id}">Update</button>
                  ${may('product.edit') ? `<button class="btn sm ghost" data-edit="${r.variant_id}">Edit</button>` : ''}
                </td>
              </tr>`).join('')}</tbody>
          </table>
        </div>`;
      list.querySelectorAll('[data-adj]').forEach((b) => {
        b.onclick = () => {
          const row = rows.find((r) => r.variant_id === Number(b.dataset.adj));
          openStockSheet(row, load);
        };
      });
      list.querySelectorAll('[data-edit]').forEach((b) => {
        b.onclick = () => {
          const row = rows.find((r) => r.variant_id === Number(b.dataset.edit));
          openProductSheet(row, load);
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
        ${may('inventory.stocktake') ? '<option value="adjust">Set count</option>' : ''}
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

/** Add a product (row omitted) or edit one (row is an inventory row, which
 * already carries both its product and its one variant). The two are saved
 * together -- this app has no screen that edits them apart. */
// Kept modest on purpose: this is a demo-quality app with no file storage or
// upload pipeline anywhere in it, so a photo is stored the same way an
// image_url always has been -- as a string in that column. A data: URL is
// just a string that happens to decode to a picture, which means "add a
// photo" needed nothing new on the server at all. The cap exists because
// nothing else in the app bounds how large that string can get.
const MAX_PHOTO_BYTES = 1.5 * 1024 * 1024;

function readPhoto(file) {
  return new Promise((resolve, reject) => {
    if (!file.type.startsWith('image/')) return reject(new Error('That is not an image file.'));
    if (file.size > MAX_PHOTO_BYTES) return reject(new Error('Photos must be under 1.5 MB.'));
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error('Could not read that file.'));
    reader.readAsDataURL(file);
  });
}

export function openProductSheet(row, onDone) {
  const editing = Boolean(row);
  // null = leave the photo as it is; '' = explicitly cleared; a data: URL =
  // a new photo was chosen. Distinct from the other fields, which are always
  // sent, because re-sending the same image on every save just to leave it
  // unchanged would make an ordinary rename several megabytes of traffic.
  let photoDataUrl = null;

  sheet(`
    <h3>${editing ? h(row.product_name) : 'Add a product'}</h3>
    <div class="row" style="gap:12px;align-items:center;margin-bottom:10px">
      <div id="photoPreview" style="width:64px;height:64px;border-radius:10px;overflow:hidden;background:var(--surface-2);flex:0 0 auto;display:flex;align-items:center;justify-content:center;font-size:1.4rem">
        ${editing && row.image_url ? `<img src="${h(row.image_url)}" alt="" style="width:100%;height:100%;object-fit:cover">` : svgIcon('box')}
      </div>
      <div style="flex:1">
        <label class="btn sm ghost" style="cursor:pointer;display:inline-block">
          ${svgIcon('camera')} ${editing && row.image_url ? 'Change photo' : 'Add photo'}
          <input type="file" id="photo" accept="image/*" style="display:none">
        </label>
        ${editing && row.image_url ? '<button class="btn sm ghost" id="removePhoto" style="margin-left:6px">Remove</button>' : ''}
        <div id="photoErr" style="color:var(--danger);font-size:.78rem;margin-top:4px"></div>
      </div>
    </div>
    <label class="field">
      <span class="lbl">Name</span>
      <input class="input" id="name" value="${editing ? h(row.product_name) : ''}" placeholder="e.g. Rice 5kg">
    </label>
    <div class="row" style="gap:8px">
      <label class="field" style="flex:1">
        <span class="lbl">Brand</span>
        <input class="input" id="brand" value="${editing ? h(row.brand || '') : ''}">
      </label>
      <label class="field" style="flex:1">
        <span class="lbl">Category</span>
        <input class="input" id="category" value="${editing ? h(row.category || '') : ''}">
      </label>
    </div>
    <div class="row" style="gap:8px">
      <label class="field" style="flex:1">
        <span class="lbl">SKU</span>
        <input class="input" id="sku" value="${editing ? h(row.sku) : ''}" placeholder="unique code">
      </label>
      <label class="field" style="flex:1">
        <span class="lbl">Price</span>
        <input class="input" id="price" type="number" min="0" step="0.01" value="${editing ? row.price : ''}">
      </label>
    </div>
    ${!editing ? `
    <label class="field">
      <span class="lbl">Starting stock (optional)</span>
      <input class="input" id="stock" type="number" min="0" step="1" value="0">
    </label>` : ''}
    <label class="field">
      <span class="lbl">Variant label (optional)</span>
      <input class="input" id="label" value="${editing ? h(row.label || '') : ''}" placeholder="e.g. Black - Size 9">
    </label>
    <label class="field">
      <span class="lbl">Barcode (optional)</span>
      <input class="input" id="barcode" value="${editing ? h(row.barcode || '') : ''}">
    </label>
    <div id="err" style="color:var(--danger);font-size:.82rem;margin:4px 0 10px"></div>
    <button class="btn lg block" id="save">${editing ? 'Save changes' : 'Add product'}</button>
    ${editing && may('product.delete')
      ? '<button class="btn ghost block danger" id="del" style="margin-top:8px">Delete this variant</button>'
      : ''}
  `, {
    onMount(panel, close) {
      const err = panel.querySelector('#err');
      const field = (id) => panel.querySelector('#' + id).value.trim();
      const preview = panel.querySelector('#photoPreview');
      const photoErr = panel.querySelector('#photoErr');

      panel.querySelector('#photo').onchange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        photoErr.textContent = '';
        try {
          photoDataUrl = await readPhoto(file);
          preview.innerHTML = `<img src="${photoDataUrl}" alt="" style="width:100%;height:100%;object-fit:cover">`;
        } catch (ex) {
          photoErr.textContent = ex.message;
          e.target.value = '';
        }
      };

      const removeBtn = panel.querySelector('#removePhoto');
      if (removeBtn) {
        removeBtn.onclick = () => {
          photoDataUrl = '';
          preview.innerHTML = svgIcon('box');
          photoErr.textContent = '';
        };
      }

      panel.querySelector('#save').onclick = async (e) => {
        err.textContent = '';
        const name = field('name');
        const sku = field('sku');
        if (!name) { err.textContent = 'A product needs a name.'; return; }
        if (!sku) { err.textContent = 'A variant needs a SKU.'; return; }
        e.currentTarget.disabled = true;
        try {
          const productFields = { name, brand: field('brand'), category: field('category') };
          if (photoDataUrl !== null) productFields.image_url = photoDataUrl;
          const variantFields = {
            sku, label: field('label'), barcode: field('barcode'),
            price: Number(panel.querySelector('#price').value || 0),
          };
          if (editing) {
            await api.updateProduct(row.product_id, productFields);
            await api.updateVariant(row.variant_id, variantFields);
          } else {
            const product = await api.createProduct(productFields);
            const variant = await api.addVariant(product.id, variantFields);
            // A fresh variant has no inventory row at all until stock moves
            // for the first time -- going through moveStock rather than
            // writing a starting count directly means this arrives on the
            // shelf exactly the way any other delivery does: as a recorded
            // movement, not a number that appeared from nowhere.
            const startingStock = Number(panel.querySelector('#stock')?.value || 0);
            if (startingStock > 0) {
              await api.moveStock(variant.id, 'add', startingStock, 'Starting stock');
            }
          }
          close();
          toast(editing ? 'Product updated' : 'Product added', 'ok');
          onDone && onDone();
        } catch (ex) {
          e.currentTarget.disabled = false;
          err.textContent = ex.message;
        }
      };

      const del = panel.querySelector('#del');
      if (del) {
        // Closed first, then confirmed: two full-screen sheets stacked on
        // top of each other has never been exercised anywhere else in this
        // app, so this does not become the first place it is tried.
        del.onclick = async () => {
          close();
          const ok = await confirmSheet({
            title: 'Delete this variant?',
            body: 'It comes off the showcase and the till immediately. Stock history stays in the record.',
            confirmLabel: 'Delete', danger: true,
          });
          if (!ok) return;
          try {
            await api.deleteVariant(row.variant_id);
            toast('Variant deleted', 'ok');
            onDone && onDone();
          } catch (ex) { toast(ex.message, 'err'); }
        };
      }
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
          <input class="input" id="code" placeholder="e.g. AML-GHEE-500 or 8901234500396" autocomplete="off">
        </label>
        <button class="btn block" id="go" style="margin-top:10px">Look up</button>
        <div class="chips" style="margin-top:10px">
          <button class="chip" data-demo="AML-GHEE-500">Demo: Desi Cow Ghee</button>
          <button class="chip" data-demo="8901234500424">Demo: Sunflower oil</button>
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
              <div style="font-weight:800">${svgIcon('check-circle')} ${h(v.product_name)}</div>
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
        ? empty({ icon: svgIcon('question'), title: 'No product matches that code', body: `Nothing in this store uses "${code}".` })
        : errorBox(err.message);
    }
  }

  async function lookupReservation(code) {
    try {
      const r = await api.reservationByCode(code);
      out.innerHTML = `
        <div class="card pad">
          ${['accepted', 'ready_for_pickup'].includes(r.status)
            ? '<div style="font-weight:800;color:var(--ok);font-size:1rem;margin-bottom:10px">RESERVATION VERIFIED &#9989;</div>'
            : ''}
          <div class="row between"><span class="badge ${h(r.status)}">${h(r.status.replace(/_/g, ' '))}</span><span class="rescode" style="font-size:.95rem">${h(r.code)}</span></div>
          <div style="font-weight:800;margin-top:10px">${h(r.customer_name)}</div>
          <div style="font-size:.85rem;color:var(--ink-2)">${h(r.product_name)} · ${h(r.variant_label)} · qty ${r.quantity}</div>
          ${['accepted', 'ready_for_pickup'].includes(r.status)
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
        ? empty({ icon: svgIcon('ticket'), title: 'No reservation with that code', body: 'Check the code and try again.' })
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
          const open = rows.find((r) => ['accepted', 'ready_for_pickup'].includes(r.status)) || rows[0];
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

/* ---------- inventory history ---------- */

export async function historyView(mount) {
  if (!guard()) return;
  mount.innerHTML = `
    <div class="wrap" style="padding-top:16px">
      <h2 style="margin-bottom:6px">Inventory history</h2>
      <p style="color:var(--muted);font-size:.85rem;margin-bottom:14px">
        Every event that moved a count, newest first.
      </p>
      <div class="chips" id="f"></div>
      <div id="list" style="margin-top:14px">${skeletonLines(4)}</div>
    </div>`;

  let kind = 'all';
  const KINDS = [
    ['all', 'All'], ['RESERVATION', 'Reservations'], ['PICKUP', 'Pickups'],
    ['SALE', 'Sales'], ['STOCK_RECEIVED', 'Received'], ['STOCK_ADJUSTMENT', 'Adjustments'],
  ];

  const drawFilters = () => {
    mount.querySelector('#f').innerHTML = KINDS.map(([k, l]) =>
      `<button class="chip ${kind === k ? 'on' : ''}" data-f="${k}">${l}</button>`).join('');
    mount.querySelectorAll('[data-f]').forEach((b) => {
      b.onclick = () => { kind = b.dataset.f; drawFilters(); load(); };
    });
  };

  async function load() {
    const list = mount.querySelector('#list');
    try {
      const rows = await api.movements({ limit: 80 });
      // Reservation lifecycle rows group under the Reservations filter, since
      // a shopkeeper thinks of them as one thread rather than five kinds.
      const shown = kind === 'all' ? rows
        : kind === 'RESERVATION'
          ? rows.filter((r) => r.kind.startsWith('RESERVATION'))
          : rows.filter((r) => r.kind === kind);
      list.innerHTML = `<div class="card pad">${timeline(shown, {
        emptyText: kind === 'all' ? 'No activity recorded yet.' : 'Nothing of that kind yet.',
      })}</div>`;
    } catch (err) {
      if (err.status === 401) return navigate('/store/login', { replace: true });
      list.innerHTML = errorBox(err.message);
    }
  }

  drawFilters();
  load();
}

/* ---------- audit log ---------- */

export async function auditView(mount) {
  if (!guard()) return;
  mount.innerHTML = `
    <div class="wrap" style="padding-top:16px">
      <h2 style="margin-bottom:6px">Audit log</h2>
      <p style="color:var(--muted);font-size:.85rem;margin-bottom:14px">
        Who did what, and when. Refused attempts are recorded too.
      </p>
      <div class="chips" id="f"></div>
      <div id="list" style="margin-top:14px">${skeletonLines(5)}</div>
    </div>`;

  let outcome = '';
  const drawFilters = () => {
    mount.querySelector('#f').innerHTML = [['', 'All'], ['ok', 'Actions'], ['denied', 'Refused']]
      .map(([k, l]) => `<button class="chip ${outcome === k ? 'on' : ''}" data-f="${k}">${l}</button>`).join('');
    mount.querySelectorAll('[data-f]').forEach((b) => {
      b.onclick = () => { outcome = b.dataset.f; drawFilters(); load(); };
    });
  };

  async function load() {
    const list = mount.querySelector('#list');
    try {
      const rows = await api.auditLog(outcome ? { outcome, limit: 100 } : { limit: 100 });
      if (!rows.length) {
        list.innerHTML = empty({ icon: svgIcon('shield'), title: 'Nothing logged yet' });
        return;
      }
      list.innerHTML = `<div class="card pad"><ul class="tl">${rows.map((r) => `
        <li>
          <span class="tl-ic">${r.outcome === 'denied' ? svgIcon('blocked') : svgIcon('check-circle')}</span>
          <span class="tl-body">
            <span class="tl-top">
              <span class="tl-label">${h(r.action)}</span>
              <span class="tl-time">${h((r.created_at || '').slice(5, 16))}</span>
            </span>
            <span class="tl-sub">${h(r.actor_name)} (${h(r.actor_role)})${
              r.entity_type ? ` · ${h(r.entity_type)} ${h(r.entity_id)}` : ''}</span>
            ${r.detail ? `<span class="tl-sub" style="font-family:ui-monospace,monospace;font-size:.72rem">${h(r.detail)}</span>` : ''}
          </span>
        </li>`).join('')}</ul></div>`;
    } catch (err) {
      if (err.status === 401) return navigate('/store/login', { replace: true });
      list.innerHTML = errorBox(err.message);
    }
  }

  drawFilters();
  load();
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
        <div class="card pad">${o.top_products.length ? rankedBars(o.top_products) : empty({ icon: svgIcon('chart-bar'), title: 'No sales yet' })}</div>
      </div>

      <div class="sec">
        <div class="sec-head"><h2>Low stock</h2><a class="link" href="#/store/inventory">Manage</a></div>
        <div class="stack">${o.low_stock.length ? o.low_stock.map((r) => `
          <div class="line" style="cursor:default">
            <div class="thumb">${r.image_url ? `<img src="${h(r.image_url)}" alt="">` : ''}</div>
            <div class="meta"><span class="name">${h(r.product_name)}</span><span class="sku">${h(r.sku)}</span></div>
            ${statusLine(r)}
          </div>`).join('') : empty({ icon: svgIcon('check-circle'), title: 'Everything is well stocked' })}</div>
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

/* ---------- settings ---------- */

// Labels for the store types the backend knows about (services/store.py's
// SHOWCASE_TYPES). A type the client has never heard of still shows, just
// under its raw name, so a newer server never breaks an older client here.
const TYPE_INFO = {
  general: { icon: svgIcon('bag'), label: 'General store', blurb: 'A flat product grid — the default showcase.' },
  grocery: { icon: svgIcon('cart'), label: 'Grocery', blurb: 'Products grouped into aisles by category.' },
  mall: { icon: svgIcon('mall'), label: 'Mall', blurb: 'Products grouped into wings by brand/shop.' },
};

export async function settingsView(mount) {
  if (!guard()) return;
  if (!may('settings.view')) {
    mount.innerHTML = `<div class="wrap" style="padding-top:16px">${
      errorBox('You do not have access to store settings.')
    }</div>`;
    return;
  }

  mount.innerHTML = `<div class="wrap" style="padding-top:16px"><div id="body">${skeletonLines(4)}</div></div>`;
  const body = mount.querySelector('#body');
  const editable = may('settings.edit');
  const s = state.store;
  const types = Object.keys(TYPE_INFO).includes(s.type) ? Object.keys(TYPE_INFO) : [...Object.keys(TYPE_INFO), s.type];

  body.innerHTML = `
    <h2 style="margin-bottom:4px">Store settings</h2>
    <p style="color:var(--muted);font-size:.86rem;margin-bottom:18px">
      ${editable ? 'Changes apply to the customer showcase immediately.' : 'Read-only — ask an owner to make changes.'}
    </p>

    <div class="sec-head"><h2>Shop type</h2></div>
    <p style="color:var(--muted);font-size:.82rem;margin-bottom:10px">Sets the whole layout customers browse — pick the one that matches this shop.</p>
    <div class="stack" id="types" style="gap:8px;margin-bottom:22px"></div>

    <div class="sec-head"><h2>Profile</h2></div>
    <div class="card pad" style="margin-bottom:18px">
      <label class="field" style="margin-bottom:12px">
        <span class="lbl">Shop name</span>
        <input class="input" id="f_name" value="${h(s.name)}" ${editable ? '' : 'disabled'}>
      </label>
      <label class="field" style="margin-bottom:12px">
        <span class="lbl">Tagline</span>
        <input class="input" id="f_tagline" value="${h(s.tagline || '')}" ${editable ? '' : 'disabled'}>
      </label>
      <div class="row" style="gap:10px;margin-bottom:12px">
        <label class="field" style="flex:1">
          <span class="lbl">Opens</span>
          <input class="input" id="f_opens" type="time" value="${h(s.opens_at || '')}" ${editable ? '' : 'disabled'}>
        </label>
        <label class="field" style="flex:1">
          <span class="lbl">Closes</span>
          <input class="input" id="f_closes" type="time" value="${h(s.closes_at || '')}" ${editable ? '' : 'disabled'}>
        </label>
      </div>
      <label class="field" style="margin-bottom:12px">
        <span class="lbl">Phone</span>
        <input class="input" id="f_phone" value="${h(s.phone || '')}" ${editable ? '' : 'disabled'}>
      </label>
      <label class="field" style="margin-bottom:12px">
        <span class="lbl">Email</span>
        <input class="input" id="f_email" value="${h(s.email || '')}" ${editable ? '' : 'disabled'}>
      </label>
      <label class="field" style="margin-bottom:12px">
        <span class="lbl">Address</span>
        <input class="input" id="f_address" value="${h(s.address || '')}" ${editable ? '' : 'disabled'}>
      </label>
      <label class="field">
        <span class="lbl">Accent colour</span>
        <input class="input" id="f_color" type="color" value="${h(s.accent_color || '#3d5afe')}" style="height:42px;padding:4px" ${editable ? '' : 'disabled'}>
      </label>
    </div>

    ${editable ? '<button class="btn lg block" id="save">Save changes</button>' : ''}`;

  let selectedType = s.type;
  const drawTypes = () => {
    body.querySelector('#types').innerHTML = types.map((t) => {
      const info = TYPE_INFO[t] || { icon: svgIcon('question'), label: t, blurb: '' };
      return `
        <button class="modecard ${selectedType === t ? 'on' : ''}" data-type="${h(t)}" ${editable ? '' : 'disabled'}
                style="${selectedType === t ? 'border-color:var(--accent);background:var(--info-bg)' : ''}">
          <span class="ic">${info.icon}</span>
          <span style="flex:1">
            <span class="t">${h(info.label)}</span>
            <span class="d">${h(info.blurb)}</span>
          </span>
          ${selectedType === t ? `<span style="color:var(--accent);font-weight:800">${svgIcon('check')}</span>` : ''}
        </button>`;
    }).join('');
    if (editable) {
      body.querySelectorAll('[data-type]').forEach((b) => {
        b.onclick = () => { selectedType = b.dataset.type; drawTypes(); };
      });
    }
  };
  drawTypes();

  const saveBtn = body.querySelector('#save');
  if (saveBtn) {
    saveBtn.onclick = async () => {
      saveBtn.disabled = true;
      saveBtn.textContent = 'Saving…';
      try {
        const updated = await api.updateStore({
          type: selectedType,
          name: body.querySelector('#f_name').value,
          tagline: body.querySelector('#f_tagline').value,
          opens_at: body.querySelector('#f_opens').value,
          closes_at: body.querySelector('#f_closes').value,
          phone: body.querySelector('#f_phone').value,
          email: body.querySelector('#f_email').value,
          address: body.querySelector('#f_address').value,
          accent_color: body.querySelector('#f_color').value,
        });
        state.store = updated;
        if (updated.accent_color) {
          document.documentElement.style.setProperty('--accent', updated.accent_color);
        }
        toast('Settings saved', 'ok');
      } catch (err) {
        toast(err.message, 'err');
      } finally {
        saveBtn.disabled = false;
        saveBtn.textContent = 'Save changes';
      }
    };
  }
}
