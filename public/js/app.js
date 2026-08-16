import { api, auth } from './api.js';
import {
  bootstrap, exitMode, navigate, refreshCustomerBadges, refreshStaffBadges,
  resolve, route, setMode, startRouter, state,
} from './state.js';
import { confirmSheet, errorBox, h, initTheme, setCurrency, toast, toggleTheme } from './ui.js';
import * as C from './views/customer.js';
import * as S from './views/store.js';

const app = document.getElementById('app');

/* ---------- chrome ---------- */

const CUSTOMER_TABS = [
  ['/home', '🏠', 'Home'],
  ['/search/', '🔍', 'Search'],
  ['/wishlist', '❤️', 'Wishlist'],
  ['/reservations', '🎟️', 'Orders'],
];

const STORE_TABS = [
  ['/store/dashboard', '📊', 'Dashboard'],
  ['/store/inventory', '📦', 'Inventory'],
  ['/store/scan', '📷', 'Scan'],
  ['/store/reservations', '🎟️', 'Requests'],
  ['/store/analytics', '📈', 'Sales'],
];

function shell({ title, sub, back = false, mode }) {
  const tabs = mode === 'store' ? STORE_TABS : CUSTOMER_TABS;
  const path = (location.hash || '#/').slice(1);

  return `
    <header class="appbar">
      <div class="wrap">
        ${back ? '<button class="iconbtn" id="back" aria-label="Back">←</button>' : ''}
        <div style="flex:1;min-width:0">
          <h1>${h(title)}</h1>
          ${sub ? `<div class="sub">${h(sub)}</div>` : ''}
        </div>
        <span class="modepill"><span class="mode-full">${mode === 'store' ? 'Store' : 'Customer'} · </span>Demo</span>
        <button class="iconbtn" id="theme" aria-label="Toggle theme">◐</button>
        <button class="iconbtn" id="reset" aria-label="Reset demo" title="Reset demo data">↺</button>
        <button class="iconbtn" id="exit" aria-label="Switch mode">⇄</button>
      </div>
    </header>
    <main class="screen" id="screen"></main>
    <nav class="tabbar">
      ${tabs.map(([to, icon, label]) => {
        const on = path === to || (to !== '/home' && path.startsWith(to.replace(/\/$/, '')));
        const badge = to === '/store/reservations' && state.pendingReservations
          ? `<span class="dot">${state.pendingReservations}</span>` : '';
        return `<button class="${on ? 'on' : ''}" data-to="${to}">
                  <span class="ic">${icon}</span>${label}${badge}
                </button>`;
      }).join('')}
    </nav>`;
}

/** Renders chrome once, then hands the inner element to the view. */
function frame(opts, render) {
  app.innerHTML = shell(opts);
  const screen = app.querySelector('#screen');

  app.querySelector('#theme').onclick = () => toggleTheme();
  app.querySelector('#exit').onclick = () => exitMode();
  app.querySelector('#reset').onclick = () => resetDemo();
  const back = app.querySelector('#back');
  if (back) back.onclick = () => history.back();

  app.querySelectorAll('[data-to]').forEach((b) => {
    b.onclick = () => navigate(b.dataset.to);
  });

  render(screen);
}

/** Put the showcase back to its opening state so it can be given again. */
async function resetDemo() {
  const yes = await confirmSheet({
    title: 'Reset the demo?',
    body: 'Stock, reservations, sales and wishlists all go back to how they started. Nothing real is affected.',
    confirmLabel: 'Reset demo',
  });
  if (!yes) return;
  try {
    await api.resetDemo();
    // The reseeded database issues new ids, so anything the browser remembered
    // about who it was now points at a row that no longer exists.
    localStorage.removeItem('customerId');
    await bootstrap();
    toast('Demo restored to its original state', 'ok');
    resolve();
  } catch (err) {
    toast(err.message, 'err');
  }
}

/* ---------- landing ---------- */

function landing() {
  app.innerHTML = `
    <div class="wrap landing">
      <div class="logo">🛍️</div>
      <h1>${h(state.store?.name || 'Store')}</h1>
      <p class="lede">${h(state.store?.tagline || '')} — a showcase of the store experience, from finding an item to collecting it.</p>

      <div class="stack" style="margin-top:26px;gap:12px">
        <button class="modecard" data-mode="customer">
          <span class="ic">🛒</span>
          <span style="flex:1">
            <span class="t">Continue as Customer</span>
            <span class="d">Search the shelf, check live stock, reserve an item</span>
          </span>
          <span style="color:var(--muted)">›</span>
        </button>
        <button class="modecard" data-mode="store">
          <span class="ic">🏪</span>
          <span style="flex:1">
            <span class="t">Continue as Store Manager</span>
            <span class="d">Dashboard, inventory, reservations, scanner, sales</span>
          </span>
          <span style="color:var(--muted)">›</span>
        </button>
      </div>

      <p class="demonote">Demo data only. No account, no payment, no real customer details.</p>
    </div>`;

  app.querySelector('[data-mode="customer"]').onclick = () => {
    setMode('customer');
    navigate('/home');
  };
  app.querySelector('[data-mode="store"]').onclick = () => {
    setMode('store');
    navigate(auth.isStaff ? '/store/dashboard' : '/store/login');
  };
}

/* ---------- routes ---------- */

const customerTitle = () => state.store?.name || 'Store';

route('/', () => landing());

route('/home', () => frame(
  { title: customerTitle(), sub: state.store?.city, mode: 'customer' },
  (s) => C.homeView(s)));

route(/^\/search\/?(.*)$/, (_p, [term]) => {
  const q = decodeURIComponent(term || '');
  frame({ title: 'Search', mode: 'customer' }, (s) => C.searchView(s, q));
});

route(/^\/p\/(\d+)$/, (_p, [id]) => frame(
  { title: 'Product', back: true, mode: 'customer' },
  (s) => C.productView(s, id)));

route(/^\/reservation\/(\d+)$/, (_p, [id]) => frame(
  { title: 'Reservation', back: true, mode: 'customer' },
  (s) => C.reservationView(s, id)));

route('/reservations', () => frame(
  { title: 'Your reservations', mode: 'customer' },
  (s) => C.myReservationsView(s)));

route('/wishlist', () => frame(
  { title: 'Wishlist', mode: 'customer' },
  (s) => C.wishlistView(s)));

route('/find', () => frame(
  { title: 'Find everything', back: true, mode: 'customer' },
  (s) => C.findView(s)));

route('/store-info', () => frame(
  { title: 'Store', back: true, mode: 'customer' },
  (s) => C.storeInfoView(s)));

route('/store/login', () => { app.innerHTML = '<div id="screen"></div>'; S.staffLoginView(app.querySelector('#screen')); });

const storeFrame = (title, render) => frame(
  { title, sub: state.store?.name, mode: 'store' }, render);

route('/store/dashboard', () => storeFrame('Dashboard', (s) => S.dashboardView(s)));
route('/store/inventory', () => storeFrame('Inventory', (s) => S.inventoryView(s)));
route('/store/reservations', () => storeFrame('Reservations', (s) => S.reservationsView(s)));
route('/store/scan', () => storeFrame('Scanner', (s) => S.scanView(s)));
route('/store/analytics', () => storeFrame('Sales', (s) => S.analyticsView(s)));
route('/store/history', () => storeFrame('History', (s) => S.historyView(s)));

/* ---------- boot ---------- */

(async function start() {
  initTheme();
  app.innerHTML = '<div class="wrap" style="padding-top:80px;text-align:center;color:var(--muted)">Loading store…</div>';

  try {
    await bootstrap();
  } catch (err) {
    app.innerHTML = `<div class="wrap" style="padding-top:60px">${
      errorBox(`Could not load the store: ${err.message}`, 'retry')}</div>`;
    const btn = app.querySelector('#retry');
    if (btn) btn.onclick = () => location.reload();
    return;
  }

  setCurrency(state.config?.currency);
  if (auth.isStaff) await refreshStaffBadges();

  // A returning visitor lands back in the mode they chose.
  if (!location.hash || location.hash === '#/') {
    if (state.mode === 'customer') location.replace('#/home');
    else if (state.mode === 'store') location.replace(auth.isStaff ? '#/store/dashboard' : '#/store/login');
  }

  startRouter();

  // Keep the customer's badge counts honest as they move around.
  window.addEventListener('hashchange', () => {
    if (state.mode === 'customer') refreshCustomerBadges();
    else refreshStaffBadges();
  });
})();
