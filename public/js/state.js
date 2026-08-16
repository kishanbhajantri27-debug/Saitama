// Shared client state and the router.
//
// Views read from `state`, call `api`, then re-render. State that must survive
// a refresh (which mode you picked, who you are) goes to localStorage; the
// rest is cache and may be thrown away at any time.

import { api, auth } from './api.js';

const MODE_KEY = 'mode';

export const state = {
  mode: localStorage.getItem(MODE_KEY) || null,   // 'customer' | 'store' | null
  config: null,
  store: null,
  me: null,
  wishlistIds: new Set(),
  unseenNotifications: 0,
  pendingReservations: 0,
};

export function setMode(mode) {
  state.mode = mode;
  if (mode) localStorage.setItem(MODE_KEY, mode);
  else localStorage.removeItem(MODE_KEY);
}

export function exitMode() {
  setMode(null);
  auth.token = '';
  location.hash = '#/';
}

/** Loaded once at boot: things every screen needs before it can render. */
export async function bootstrap() {
  const [config, store, me] = await Promise.all([api.config(), api.store(), api.me()]);
  state.config = config;
  state.store = store;
  state.me = me;
  if (store && store.accent_color) {
    document.documentElement.style.setProperty('--accent', store.accent_color);
  }
  await refreshCustomerBadges();
}

export async function refreshCustomerBadges() {
  if (!state.me) return;
  try {
    const [wl, notes] = await Promise.all([
      api.wishlist(state.me.id),
      api.notifications(state.me.id, true),
    ]);
    state.wishlistIds = new Set(wl.map((p) => p.id));
    state.unseenNotifications = notes.length;
  } catch {
    /* badges are decoration; never block a screen on them */
  }
}

export async function refreshStaffBadges() {
  if (!auth.isStaff) return;
  try {
    const t = await api.today();
    state.pendingReservations = t.pending_reservations || 0;
  } catch {
    state.pendingReservations = 0;
  }
}

/* ---------- hash router ---------- */
const routes = [];
export const route = (pattern, handler) => routes.push({ pattern, handler });

export function navigate(path, { replace = false } = {}) {
  const target = '#' + path;
  if (location.hash === target) return resolve();
  if (replace) location.replace(target);
  else location.hash = target;
}

function match(path) {
  for (const r of routes) {
    if (typeof r.pattern === 'string') {
      if (r.pattern === path) return { handler: r.handler, params: {} };
      continue;
    }
    const m = path.match(r.pattern);
    if (m) return { handler: r.handler, params: m.groups || {}, groups: m.slice(1) };
  }
  return null;
}

let current = null;

export function resolve() {
  const path = (location.hash || '#/').slice(1) || '/';
  const found = match(path);
  if (!found) return navigate('/', { replace: true });
  current = path;
  window.scrollTo(0, 0);
  found.handler(found.params, found.groups || []);
  return undefined;
}

export const currentPath = () => current;

export function startRouter() {
  window.addEventListener('hashchange', resolve);
  resolve();
}
