import { api, auth } from './api.js';
import { cart } from './cart.js';
import {
  bootstrap, exitMode, navigate, refreshCustomerBadges, refreshStaffBadges,
  may, resolve, restoreSession, route, setMode, startRouter, state,
} from './state.js';
import { confirmSheet, errorBox, h, initTheme, setCurrency, toast, toggleTheme } from './ui.js';
import { svgIcon } from './icons.js';
import * as C from './views/customer.js';
import * as S from './views/store.js';

const app = document.getElementById('app');

/* ---------- installable app ---------- */

// Chrome/Android holds the install prompt back until asked; this captures it
// so the landing screen can offer "Install app" instead of it appearing
// unprompted in the browser's own UI (or never, on browsers that skip it).
let installPrompt = null;

window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  installPrompt = e;
  syncInstallButton();
});

window.addEventListener('appinstalled', () => {
  installPrompt = null;
  syncInstallButton();
});

function syncInstallButton() {
  const btn = document.getElementById('install');
  if (!btn) return;
  btn.style.display = installPrompt ? '' : 'none';
  btn.onclick = async () => {
    if (!installPrompt) return;
    installPrompt.prompt();
    await installPrompt.userChoice;
    // A prompt is single-use regardless of the answer.
    installPrompt = null;
    syncInstallButton();
  };
}

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {
      // Offline shell caching is a nicety, not a requirement -- a failed
      // registration (unsupported browser, blocked storage) should never
      // stop the showcase itself from working.
    });
  });
}

/* ---------- offline banner ----------
   navigator.onLine is only ever a first guess -- it can misreport at boot,
   and even when right it only reflects the network interface (a Wi-Fi
   router with no internet still reads "online"). A real request completing
   (see connectivity in api.js) is the one signal that is actually proven,
   so every 'connectivitychange' overrides the guess outright rather than
   being merged with it -- otherwise a bad initial guess of "offline" could
   never be corrected once api.js had nothing left to prove it wrong about
   (it only fires when something changes, not when it stays the same). The
   browser's own online/offline events still get to show or hide the banner
   instantly, ahead of the next request confirming it either way. */
const offlineBanner = document.getElementById('offlineBanner');
let showBanner = !navigator.onLine;

function syncOfflineBanner() {
  if (!offlineBanner) return;
  offlineBanner.hidden = !showBanner;
}

window.addEventListener('online', () => { showBanner = false; syncOfflineBanner(); });
window.addEventListener('offline', () => { showBanner = true; syncOfflineBanner(); });
window.addEventListener('connectivitychange', (e) => { showBanner = e.detail.offline; syncOfflineBanner(); });
syncOfflineBanner();

/* ---------- chrome ---------- */

// Five slots with a raised scanner in the middle, matching the storefront
// design. The centre button is not a route -- it opens the code lookup
// sheet over whatever screen you are on.
const CUSTOMER_TABS = [
  ['/home', svgIcon('home'), 'Home'],
  ['/categories', svgIcon('folder'), 'Aisles'],
  ['scan', svgIcon('scan'), 'Scan'],
  ['/cart', svgIcon('basket'), 'Basket'],
  ['/reservations', svgIcon('ticket'), 'Orders'],
];

const SIDEBAR_LINKS = [
  ['/home', svgIcon('home'), 'Home'],
  ['/showcase', svgIcon('folder'), 'Showcase'],
  ['/search/', svgIcon('search'), 'Search'],
  ['/reservations', svgIcon('ticket'), 'My orders'],
  ['/wishlist', svgIcon('heart-outline'), 'Wishlist'],
  ['/recently-viewed', svgIcon('clock'), 'Recently viewed'],
  ['/store-info', svgIcon('store'), 'Store info'],
];

const STORE_TABS = [
  ['/store/dashboard', svgIcon('chart-bar'), 'Dashboard'],
  ['/store/inventory', svgIcon('box'), 'Inventory'],
  ['/store/scan', svgIcon('scan'), 'Scan'],
  ['/store/reservations', svgIcon('ticket'), 'Requests'],
  ['/store/analytics', svgIcon('chart-line'), 'Sales'],
];

function shell({ title, sub, back = false, mode }) {
  const tabs = mode === 'store' ? STORE_TABS : CUSTOMER_TABS;
  const path = (location.hash || '#/').slice(1);

  return `
    <header class="appbar">
      <div class="wrap">
        ${mode === 'customer' && !back
          ? `<button class="iconbtn" id="menu" aria-label="Open menu">${svgIcon('menu')}</button>`
          : ''}
        ${back ? `<button class="iconbtn" id="back" aria-label="Back">${svgIcon('chevron-left')}</button>` : ''}
        <div class="appbar-title">
          <h1>${h(title)}</h1>
          ${sub ? `<div class="sub">${h(sub)}</div>` : ''}
        </div>
        ${mode === 'customer' ? headerSearchAndActions() : ''}
        <span class="modepill"><span class="mode-full">${
          mode === 'store' ? h(state.user?.role || 'Store') : 'Customer'} · </span>Demo</span>
        <button class="iconbtn" id="theme" aria-label="Toggle theme">${svgIcon('contrast')}</button>
        ${mode === 'store' && may('demo.reset')
          ? `<button class="iconbtn" id="reset" aria-label="Reset demo" title="Reset demo data">${svgIcon('refresh')}</button>`
          : ''}
        <button class="iconbtn" id="exit" aria-label="Switch mode">${svgIcon('swap')}</button>
      </div>
    </header>
    <main class="screen" id="screen"></main>
    <nav class="tabbar">
      ${tabs.map(([to, icon, label]) => {
        if (to === 'scan') {
          return `<button class="tab-scan" id="tabscan" aria-label="Scan a code">
                    <span class="ic">${icon}</span>${label}
                  </button>`;
        }
        const on = path === to || (to !== '/home' && path.startsWith(to.replace(/\/$/, '')));
        const count = to === '/store/reservations' ? state.pendingReservations
          : to === '/cart' ? cart.count()
          : 0;
        const badge = count ? `<span class="dot">${count}</span>` : '';
        return `<button class="${on ? 'on' : ''}" data-to="${to}">
                  <span class="ic">${icon}</span>${label}${badge}
                </button>`;
      }).join('')}
    </nav>
    ${mode === 'customer' ? sidebar(path) : ''}`;
}

/** Search box + wishlist/orders/account -- only ever shown at desktop widths
    (see .header-search / .header-actions in app.css); the phone layout keeps
    using the hamburger drawer and bottom tabbar instead. */
function headerSearchAndActions() {
  return `
    <div class="header-search desktop-only">
      <span class="ic">${svgIcon('search')}</span>
      <input id="hsearch" type="search" placeholder="Search ${h(state.store?.name ? 'at ' + state.store.name : 'products')}…" autocomplete="off">
    </div>
    <div class="header-actions desktop-only">
      <button class="header-action" data-to="/wishlist" aria-label="Wishlist">
        <span class="ic">${svgIcon('heart-outline')}</span>Wishlist
        ${state.wishlistIds.size ? `<span class="count-badge">${state.wishlistIds.size}</span>` : ''}
      </button>
      <button class="header-action" data-to="/cart" aria-label="Your basket">
        <span class="ic">${svgIcon('basket')}</span>Basket
        ${cart.count() ? `<span class="count-badge">${cart.count()}</span>` : ''}
      </button>
      <button class="header-action" data-to="/reservations" aria-label="Your orders">
        <span class="ic">${svgIcon('ticket')}</span>Orders
        ${state.openReservations ? `<span class="count-badge">${state.openReservations}</span>` : ''}
      </button>
      <button class="header-account" data-to="/account">
        <span class="avatar">${svgIcon('person')}</span>
        <span>
          <b>Hi, ${h(state.me?.name || 'there')}</b>
          <small>Guest · no account needed</small>
        </span>
      </button>
    </div>`;
}

/** Navigation order mirrors the storefront design: browse (home + the real
    categories) first, then the personal shelves, then the help card. */
function sidebar(path) {
  // Only ever one entry lit, and it is the most specific one that matches.
  // A plain prefix test lit two at once: picking a category navigates to
  // /search/cat:<name>, which also starts with the generic Search entry's
  // /search, so both glowed. The longest matching target wins instead.
  const targets = [
    '/home', '/showcase', '/search/',
    ...state.categories.map((c) => `/search/cat:${encodeURIComponent(c)}`),
    '/cart', '/reservations', '/wishlist', '/recently-viewed', '/store-info',
  ];
  const active = targets
    .filter((to) => path === to || (to !== '/home' && path.startsWith(to.replace(/\/$/, ''))))
    .sort((a, b) => b.length - a.length)[0];
  const isOn = (to) => to === active;
  const link = ([to, icon, label]) =>
    `<button class="${isOn(to) ? 'on' : ''}" data-to="${to}">
       <span class="ic">${icon}</span>${label}
     </button>`;

  return `
    <div class="drawer-bg" id="drawerBg">
      <aside class="drawer" role="dialog" aria-label="Menu">
        <div class="drawer-head">
          <span class="drawer-logo">${TYPE_LOGO[state.store?.type] || TYPE_LOGO.general}</span>
          <span class="drawer-name">${h(state.store?.name || 'Store')}</span>
          <button class="iconbtn" id="drawerClose" aria-label="Close menu">${svgIcon('close')}</button>
        </div>

        <nav class="drawer-nav">
          ${[['/home', svgIcon('home'), 'Home'], ['/showcase', svgIcon('folder'), 'Showcase'], ['/search/', svgIcon('search'), 'Search']].map(link).join('')}
          ${C.inAisleOrder(state.categories).map((c) => {
            const to = `/search/cat:${encodeURIComponent(c)}`;
            return `<button class="${isOn(to) ? 'on' : ''}" data-to="${to}">
                      <span class="ic">${C.categoryIcon(c)}</span>${h(c)}
                    </button>`;
          }).join('')}
        </nav>

        <div class="drawer-divider"></div>
        <nav class="drawer-nav">
          ${[
            ['/cart', svgIcon('basket'), 'My basket'],
            ['/reservations', svgIcon('ticket'), 'My orders'],
            ['/wishlist', svgIcon('heart-outline'), 'Wishlist'],
            ['/recently-viewed', svgIcon('clock'), 'Recently viewed'],
            ['/store-info', svgIcon('store'), 'Store info'],
          ].map(link).join('')}
        </nav>

        <div class="drawer-foot">
          <div class="help-card">
            <b>Need help?</b>
            <small>${h(state.store?.hours_label || 'We are here during store hours')}</small>
            ${state.store?.phone
              ? `<a class="btn ghost sm block" href="tel:${h(state.store.phone.replace(/\s/g, ''))}">${svgIcon('phone')} Contact us</a>`
              : ''}
          </div>
        </div>
      </aside>
    </div>`;
}

/** Renders chrome once, then hands the inner element to the view. */
function frame(opts, render) {
  app.innerHTML = shell(opts);
  const screen = app.querySelector('#screen');

  app.querySelector('#theme').onclick = () => toggleTheme();
  app.querySelector('#exit').onclick = () => exitMode();
  const resetBtn = app.querySelector('#reset');
  if (resetBtn) resetBtn.onclick = () => resetDemo();
  const back = app.querySelector('#back');
  if (back) back.onclick = () => history.back();

  app.querySelectorAll('[data-to]').forEach((b) => {
    b.onclick = () => { closeDrawer(); navigate(b.dataset.to); };
  });

  const hsearch = app.querySelector('#hsearch');
  if (hsearch) hsearch.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && hsearch.value.trim()) navigate(`/search/${encodeURIComponent(hsearch.value.trim())}`);
  });

  const tabscan = app.querySelector('#tabscan');
  if (tabscan) tabscan.onclick = () => C.openLookupSheet();

  const menu = app.querySelector('#menu');
  if (menu) menu.onclick = () => openDrawer();
  const drawerClose = app.querySelector('#drawerClose');
  if (drawerClose) drawerClose.onclick = () => closeDrawer();
  const drawerBg = app.querySelector('#drawerBg');
  if (drawerBg) drawerBg.onclick = (e) => { if (e.target === drawerBg) closeDrawer(); };

  render(screen);
}

function openDrawer() {
  const bg = app.querySelector('#drawerBg');
  if (bg) bg.classList.add('open');
}

function closeDrawer() {
  const bg = app.querySelector('#drawerBg');
  if (bg) bg.classList.remove('open');
}

document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeDrawer(); });

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

const TYPE_LOGO = { grocery: svgIcon('cart'), mall: svgIcon('mall'), general: svgIcon('bag') };

function landing() {
  const logo = TYPE_LOGO[state.store?.type] || TYPE_LOGO.general;
  app.innerHTML = `
    <div class="wrap landing">
      <div class="logo">${logo}</div>
      <h1>${h(state.store?.name || 'Store')}</h1>
      <p class="lede">${h(state.store?.tagline || '')} — a showcase of the store experience, from finding an item to collecting it.</p>

      <div class="stack" style="margin-top:26px;gap:12px">
        <button class="modecard" data-mode="customer">
          <span class="ic">${svgIcon('cart')}</span>
          <span style="flex:1">
            <span class="t">Continue as Customer</span>
            <span class="d">Search the shelf, check live stock, reserve an item</span>
          </span>
          <span style="color:var(--muted)">›</span>
        </button>
        <button class="modecard" data-mode="store">
          <span class="ic">${svgIcon('store')}</span>
          <span style="flex:1">
            <span class="t">Continue as Store Manager</span>
            <span class="d">Dashboard, inventory, reservations, scanner, sales</span>
          </span>
          <span style="color:var(--muted)">›</span>
        </button>
      </div>

      <button class="btn ghost block" id="install" style="margin-top:14px;display:none">${svgIcon('install')} Install app</button>
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
  syncInstallButton();
}

/* ---------- routes ---------- */

const customerTitle = () => state.store?.name || 'Store';

route('/', () => landing());

route('/home', () => frame(
  { title: customerTitle(), sub: state.store?.city, mode: 'customer' },
  (s) => C.homeView(s)));

route('/showcase', () => frame(
  { title: 'Showcase', sub: 'Everything in the store', mode: 'customer' },
  (s) => C.showcaseView(s)));

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

route('/recently-viewed', () => frame(
  { title: 'Recently viewed', mode: 'customer' },
  (s) => C.recentlyViewedView(s)));

route('/categories', () => frame(
  { title: 'Categories', mode: 'customer' },
  (s) => C.categoriesView(s)));

route('/cart', () => frame(
  { title: 'Basket', mode: 'customer' },
  (s) => C.cartView(s)));

route('/account', () => frame(
  { title: 'Account', mode: 'customer' },
  (s) => C.accountView(s)));

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
route('/store/refunds', () => storeFrame('Refunds', (s) => S.refundsView(s)));
route('/store/audit', () => storeFrame('Audit log', (s) => S.auditView(s)));
route('/store/settings', () => storeFrame('Settings', (s) => S.settingsView(s)));

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
  await restoreSession();
  if (auth.isStaff) await refreshStaffBadges();

  // A returning visitor lands back in the mode they chose.
  if (!location.hash || location.hash === '#/') {
    if (state.mode === 'customer') location.replace('#/home');
    else if (state.mode === 'store') location.replace(auth.isStaff ? '#/store/dashboard' : '#/store/login');
  }

  startRouter();

  // One clock for the whole app: any "reserved for you" countdown that any
  // screen renders is ticked from here.
  C.startClocks();

  // Keep the customer's badge counts honest as they move around.
  window.addEventListener('hashchange', () => {
    if (state.mode === 'customer') refreshCustomerBadges();
    else refreshStaffBadges();
  });

  // Adding to the basket from a shelf must move the counter in the header
  // and the tab bar without reloading the screen underneath it.
  window.addEventListener('cartchange', () => {
    const n = cart.count();
    document.querySelectorAll('[data-to="/cart"]').forEach((node) => {
      const badge = node.querySelector('.count-badge, .dot');
      if (badge) {
        if (n) badge.textContent = n;
        else badge.remove();
      } else if (n) {
        const isTab = node.closest('.tabbar');
        node.insertAdjacentHTML('beforeend',
          `<span class="${isTab ? 'dot' : 'count-badge'}">${n}</span>`);
      }
    });
  });
})();
