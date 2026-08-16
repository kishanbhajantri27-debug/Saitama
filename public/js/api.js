// The single seam between this app and its backend.
//
// Every network call in the app goes through here. When the parent platform
// exposes the real API, this file changes and nothing else does -- which is
// why views never call fetch() themselves.

const BASE = '/api';

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

// Store-mode token. Kept in sessionStorage so a refresh keeps staff signed in
// but closing the tab does not leave a till unlocked.
const TOKEN_KEY = 'staffToken';
export const auth = {
  get token() { return sessionStorage.getItem(TOKEN_KEY) || ''; },
  set token(v) { v ? sessionStorage.setItem(TOKEN_KEY, v) : sessionStorage.removeItem(TOKEN_KEY); },
  get isStaff() { return Boolean(this.token); },
};

async function call(path, { method = 'GET', body, staff = false } = {}) {
  const headers = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (staff || auth.isStaff) headers['X-Staff-Token'] = auth.token;

  let res;
  try {
    res = await fetch(BASE + path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError('Cannot reach the store. Check your connection.', 0);
  }

  if (res.status === 204) return null;

  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = null; }

  if (!res.ok) {
    throw new ApiError((data && data.error) || `Request failed (${res.status})`, res.status);
  }
  return data;
}

export const api = {
  config: () => call('/config'),
  store: () => call('/store'),
  me: () => call('/me'),

  products: (params = {}) => {
    const q = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
    ).toString();
    return call(`/products${q ? '?' + q : ''}`);
  },
  product: (id) => call(`/products/${id}`),
  categories: () => call('/categories'),
  lookup: (code) => call(`/lookup?code=${encodeURIComponent(code)}`),
  checkMany: (items) => call('/check-many', { method: 'POST', body: { items } }),

  wishlist: (customerId) => call(`/customers/${customerId}/wishlist`),
  addWishlist: (customerId, productId) =>
    call(`/customers/${customerId}/wishlist`, { method: 'POST', body: { product_id: productId } }),
  removeWishlist: (customerId, productId) =>
    call(`/customers/${customerId}/wishlist/${productId}`, { method: 'DELETE' }),

  notifyMe: (customerId, variantId) =>
    call(`/customers/${customerId}/notify`, { method: 'POST', body: { variant_id: variantId } }),
  notifications: (customerId, unseen = false) =>
    call(`/customers/${customerId}/notifications${unseen ? '?unseen=1' : ''}`),
  seenNotifications: (customerId) =>
    call(`/customers/${customerId}/notifications/seen`, { method: 'POST' }),

  reserve: (payload) => call('/reservations', { method: 'POST', body: payload }),
  reservations: (params = {}) => {
    const q = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
    ).toString();
    return call(`/reservations${q ? '?' + q : ''}`);
  },
  reservation: (id) => call(`/reservations/${id}`),
  reservationByCode: (code) => call(`/reservations/code/${encodeURIComponent(code)}`),
  cancelReservation: (id) => call(`/reservations/${id}/cancel`, { method: 'POST' }),
  reservationAction: (id, action) => call(`/reservations/${id}/${action}`, { method: 'POST', staff: true }),

  staffLogin: (username, password) =>
    call('/session/staff', { method: 'POST', body: { username, password } }),
  staffLogout: () => call('/session/staff/logout', { method: 'POST', staff: true }),
  sessionMe: () => call('/session/me', { staff: true }),
  staffList: () => call('/staff', { staff: true }),
  auditLog: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return call(`/audit${q ? '?' + q : ''}`, { staff: true });
  },

  inventory: (params = {}) => {
    const q = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
    ).toString();
    return call(`/inventory${q ? '?' + q : ''}`, { staff: true });
  },
  moveStock: (variantId, kind, quantity, note = '') =>
    call(`/inventory/${variantId}/movement`, { method: 'POST', staff: true, body: { kind, quantity, note } }),
  touchStock: (variantId) => call(`/inventory/${variantId}/touch`, { method: 'POST', staff: true }),
  movements: (params = {}) => {
    const q = new URLSearchParams({ limit: 40, ...params }).toString();
    return call(`/inventory/movements?${q}`, { staff: true });
  },
  productHistory: (productId) => call(`/products/${productId}/history`),
  resetDemo: () => call('/demo/reset', { method: 'POST' }),

  inventorySummary: () => call('/inventory/summary', { staff: true }),
  today: () => call('/analytics/today', { staff: true }),
  overview: () => call('/analytics/overview', { staff: true }),
};
