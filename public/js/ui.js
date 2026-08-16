// Presentation primitives: escaping, formatting, toasts, sheets, skeletons,
// charts. No knowledge of products, stock or reservations lives here.

export const h = (s) => String(s ?? '').replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

let currency = '₹';
export const setCurrency = (c) => { currency = c || '₹'; };
export const money = (n) => currency + Number(n || 0).toLocaleString('en-IN', {
  minimumFractionDigits: Number.isInteger(Number(n)) ? 0 : 2,
  maximumFractionDigits: 2,
});

export const el = (html) => {
  const t = document.createElement('template');
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
};

/* ---------- stock presentation ----------
   The service decides the status; this only chooses words and colour, so the
   two modes can never disagree about what "limited" means. */
const STATUS_WORD = { available: 'Available', limited: 'Limited stock', out: 'Out of stock' };

export function statusLine(stock, { showUnits = true } = {}) {
  const s = stock || {};
  const word = STATUS_WORD[s.status] || 'Unknown';
  const units = s.available === 1 ? '1 unit' : `${s.available || 0} units`;
  return `
    <div class="stack" style="gap:3px">
      <span class="stat ${h(s.status)}"><span class="dot"></span>${word}</span>
      ${showUnits && s.status !== 'out' ? `<span class="units">${units}</span>` : ''}
      ${s.freshness ? `<span class="fresh ${s.freshness.stale ? 'stale' : ''}">${h(s.freshness.label)}</span>` : ''}
    </div>`;
}

export function staleWarning(stock) {
  if (!stock || !stock.freshness || !stock.freshness.stale) return '';
  return `<div class="stalewarn"><span>⚠️</span><span>Stock may be outdated — ${h(stock.freshness.label.toLowerCase())}. Please confirm with the store.</span></div>`;
}

/* ---------- toasts ---------- */
function toastHost() {
  let host = document.querySelector('.toasts');
  if (!host) {
    host = el('<div class="toasts" role="status" aria-live="polite"></div>');
    document.body.appendChild(host);
  }
  return host;
}

export function toast(message, kind = '') {
  const node = el(`<div class="toast ${kind}">${h(message)}</div>`);
  toastHost().appendChild(node);
  setTimeout(() => {
    node.style.transition = 'opacity .2s';
    node.style.opacity = '0';
    setTimeout(() => node.remove(), 220);
  }, 2600);
}

/* ---------- bottom sheet ---------- */
export function sheet(innerHtml, { onMount } = {}) {
  const bg = el(`<div class="sheet-bg"><div class="sheet" role="dialog" aria-modal="true"><div class="grip"></div>${innerHtml}</div></div>`);
  const close = () => { bg.remove(); document.removeEventListener('keydown', onKey); };
  const onKey = (e) => { if (e.key === 'Escape') close(); };

  bg.addEventListener('click', (e) => { if (e.target === bg) close(); });
  document.addEventListener('keydown', onKey);
  document.body.appendChild(bg);

  const panel = bg.querySelector('.sheet');
  if (onMount) onMount(panel, close);
  const focusable = panel.querySelector('input, select, button');
  if (focusable) setTimeout(() => focusable.focus(), 60);
  return { close, panel };
}

export function confirmSheet({ title, body, confirmLabel = 'Confirm', danger = false }) {
  return new Promise((resolve) => {
    sheet(
      `<h3>${h(title)}</h3><p style="color:var(--muted);font-size:.88rem;margin:6px 0 18px">${h(body || '')}</p>
       <div class="row" style="gap:10px">
         <button class="btn ghost" data-no style="flex:1">Cancel</button>
         <button class="btn ${danger ? 'danger' : ''}" data-yes style="flex:1">${h(confirmLabel)}</button>
       </div>`,
      {
        onMount(panel, close) {
          panel.querySelector('[data-no]').onclick = () => { close(); resolve(false); };
          panel.querySelector('[data-yes]').onclick = () => { close(); resolve(true); };
        },
      }
    );
  });
}

/* ---------- states ---------- */
export const empty = ({ icon = '📦', title, body = '', action = '' }) =>
  `<div class="empty"><div class="ic">${icon}</div><h3>${h(title)}</h3><p>${h(body)}</p>${action}</div>`;

export const errorBox = (message, retryId = '') =>
  `<div class="errbox">${h(message)}${retryId ? ` <button class="btn sm ghost" id="${retryId}" style="margin-left:8px">Try again</button>` : ''}</div>`;

export const skeletonGrid = (n = 6) =>
  `<div class="prodgrid">${'<div class="sk card"></div>'.repeat(n)}</div>`;

export const skeletonLines = (n = 4) =>
  `<div class="stack">${'<div class="sk line"></div>'.repeat(n)}</div>`;

/* ---------- charts (hand-drawn SVG; no library) ---------- */
export function barChart(points, { valueKey = 'revenue', labelKey = 'day' } = {}) {
  if (!points || !points.length) return '';
  // Deliberately not named h/w: `h` is the escape helper in this module.
  const VIEW_W = 100, gap = 2.6;
  const max = Math.max(...points.map((p) => p[valueKey]), 1);
  const bw = (VIEW_W - gap * (points.length - 1)) / points.length;

  const bars = points.map((p, i) => {
    const bh = (p[valueKey] / max) * 78;
    const x = i * (bw + gap);
    const label = new Date(p[labelKey] + 'T00:00:00').toLocaleDateString('en-IN', { weekday: 'short' })[0];
    return `<rect class="bar" x="${x.toFixed(2)}" y="${(82 - bh).toFixed(2)}" width="${bw.toFixed(2)}" height="${Math.max(bh, 1.2).toFixed(2)}"><title>${h(p[labelKey])}: ${money(p[valueKey])}</title></rect>
            <text class="lbl" x="${(x + bw / 2).toFixed(2)}" y="95" text-anchor="middle">${h(label)}</text>`;
  }).join('');

  return `<svg class="chart" viewBox="0 0 ${VIEW_W} 100" preserveAspectRatio="none" role="img" aria-label="Sales for the last ${points.length} days">
    <line class="grid" x1="0" y1="82" x2="100" y2="82" vector-effect="non-scaling-stroke"/>
    ${bars}
  </svg>`;
}

export function rankedBars(rows, { nameKey = 'product_name', valueKey = 'revenue' } = {}) {
  if (!rows || !rows.length) return '';
  const max = Math.max(...rows.map((r) => r[valueKey]), 1);
  return `<div class="bars">${rows.map((r) => `
    <div>
      <div class="barrow">
        <div class="nm">${h(r[nameKey])}</div>
        <div class="amt">${money(r[valueKey])}</div>
      </div>
      <div class="barrow">
        <div class="track"><div class="fill" style="width:${((r[valueKey] / max) * 100).toFixed(1)}%"></div></div>
        <div class="amt" style="color:var(--muted);font-weight:600">${r.units ?? ''}${r.units ? ' pcs' : ''}</div>
      </div>
    </div>`).join('')}</div>`;
}

/* ---------- theme ---------- */
const THEME_KEY = 'theme';
export function initTheme() {
  const saved = localStorage.getItem(THEME_KEY);
  if (saved) document.documentElement.dataset.theme = saved;
  else if (matchMedia('(prefers-color-scheme: dark)').matches) document.documentElement.dataset.theme = 'dark';
}
export function toggleTheme() {
  const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  localStorage.setItem(THEME_KEY, next);
  return next;
}
