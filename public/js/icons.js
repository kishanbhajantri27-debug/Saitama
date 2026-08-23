// A small hand-drawn line-icon set, replacing the emoji this app used to
// render directly. Emoji are drawn by the OS -- different weight, different
// colour, different glyph entirely between an iPhone, a Pixel and a phone
// with a thin emoji font installed -- so the same screen looked different on
// every device. These are plain vector paths: identical everywhere, and they
// pick up `currentColor`, so an icon inside amber status text is amber
// without a second copy.
//
// Every body below is inserted into a 24x24 viewBox. Most rely on the base
// `.icon` rule in app.css (fill:none, stroke:currentColor) and only carry
// their own markup when a shape needs to be filled instead of stroked, or
// -- for the small status dots -- always the same colour regardless of the
// text colour around them.

const ICONS = {
  // ---- navigation ----
  home: '<path d="M4 11.5 12 4l8 7.5"/><path d="M6 10v9a1 1 0 0 0 1 1h4v-6h2v6h4a1 1 0 0 0 1-1v-9"/>',
  folder: '<path d="M4 6.5A1.5 1.5 0 0 1 5.5 5h4l1.7 2H18.5A1.5 1.5 0 0 1 20 8.5v9A1.5 1.5 0 0 1 18.5 19h-13A1.5 1.5 0 0 1 4 17.5Z"/>',
  basket: '<path d="M4 9h16l-1.6 9.3a2 2 0 0 1-2 1.7H7.6a2 2 0 0 1-2-1.7Z"/><path d="M8 9 9.3 4h5.4L16 9"/><path d="M9.5 13v3M12 13v3M14.5 13v3"/>',
  ticket: '<path d="M4.5 8A1.5 1.5 0 0 1 6 6.5h12A1.5 1.5 0 0 1 19.5 8v1.8a2 2 0 0 0 0 4.4V16a1.5 1.5 0 0 1-1.5 1.5H6A1.5 1.5 0 0 1 4.5 16v-1.8a2 2 0 0 0 0-4.4Z"/><path d="M14 6.8v10.4" stroke-dasharray="1.8 2"/>',
  search: '<circle cx="10.5" cy="10.5" r="6"/><path d="M19.5 19.5 15 15"/>',
  menu: '<path d="M4 6.5h16M4 12h16M4 17.5h16"/>',
  close: '<path d="M6 6l12 12M18 6 6 18"/>',
  'chevron-left': '<path d="M15 5 8 12l7 7"/>',
  'chevron-right': '<path d="M9 5l7 7-7 7"/>',
  refresh: '<path d="M4.5 12a7.5 7.5 0 0 1 13-5.1M19.5 12a7.5 7.5 0 0 1-13 5.1"/><path d="M17.3 6.9h2.4V4.5M6.7 17.1H4.3v2.4"/>',
  swap: '<path d="M6 8h12l-3-3M18 16H6l3 3"/>',
  person: '<circle cx="12" cy="8.2" r="3.4"/><path d="M5.3 19.5a6.7 6.7 0 0 1 13.4 0"/>',

  // ---- actions ----
  'heart-filled': '<path fill="currentColor" stroke="none" d="M12 20.2s-6.9-4.4-9.1-8.6C1.4 8.5 2.8 5.5 5.8 5c1.9-.3 3.5.5 4.5 1.9C11.3 5.5 13 4.7 14.9 5c3 .5 4.4 3.5 2.9 6.6-2.2 4.2-9.1 8.6-9.1 8.6Z"/>',
  'heart-outline': '<path d="M12 20.2s-6.9-4.4-9.1-8.6C1.4 8.5 2.8 5.5 5.8 5c1.9-.3 3.5.5 4.5 1.9C11.3 5.5 13 4.7 14.9 5c3 .5 4.4 3.5 2.9 6.6-2.2 4.2-9.1 8.6-9.1 8.6Z"/>',
  lock: '<rect x="5" y="10.5" width="14" height="8.5" rx="2"/><path d="M8 10.5V7.8a4 4 0 0 1 8 0v2.7"/>',
  bell: '<path d="M6.2 10.2a5.8 5.8 0 0 1 11.6 0c0 3.8 1.4 5.3 1.4 5.3H4.8s1.4-1.5 1.4-5.3Z"/><path d="M10.2 18.6a1.8 1.8 0 0 0 3.6 0"/>',
  phone: '<path d="M6.3 4.3h2.8l1.3 3.6-1.8 1.4a11.4 11.4 0 0 0 5.8 5.8l1.4-1.8 3.6 1.3v2.8a1.8 1.8 0 0 1-2 1.8A15.6 15.6 0 0 1 4.5 6.3a1.8 1.8 0 0 1 1.8-2Z"/>',
  edit: '<path d="M4.5 19.5 5.4 16 16 5.4l3 3L8.4 19l-3.9.9Z"/><path d="M13.6 6.8l3 3"/>',
  inbox: '<path d="M4 12.5h4.2l1.6 2.6h4.4l1.6-2.6H20"/><path d="M4 12.5V6.8a1.5 1.5 0 0 1 1.5-1.5h13a1.5 1.5 0 0 1 1.5 1.5v5.7"/><path d="M4 12.5v5.2a1.5 1.5 0 0 0 1.5 1.5h13a1.5 1.5 0 0 0 1.5-1.5v-5.2"/>',
  money: '<circle cx="12" cy="12" r="8"/><path d="M12 7.2v9.6"/><path d="M9.4 9.2h3.3a1.9 1.9 0 1 1 0 3.8h-1.6a1.9 1.9 0 1 0 0 3.8h3.3"/>',
  undo: '<path d="M9 8.2 4.2 13 9 17.8"/><path d="M4.2 13h11a4 4 0 0 0 0-8h-2"/>',
  'check-circle': '<circle cx="12" cy="12" r="8.5"/><path d="M8 12.3l2.6 2.6L16.2 9"/>',
  check: '<path d="M4.5 12.5 9.5 17.5 19.5 6.5"/>',
  question: '<circle cx="12" cy="12" r="8.5"/><path d="M9.6 9.4a2.4 2.4 0 1 1 3.5 2.1c-.9.5-1.3 1-1.3 2.1"/><circle cx="12" cy="16.9" r="0.65" fill="currentColor" stroke="none"/>',
  warning: '<path d="M12 3.8 21 20.2H3Z"/><path d="M12 10v3.6"/><circle cx="12" cy="16.6" r="0.7" fill="currentColor" stroke="none"/>',
  blocked: '<circle cx="12" cy="12" r="8.5"/><path d="M6.5 6.5l11 11"/>',
  shield: '<path d="M12 3.5 18.5 6v5.5c0 4.6-3.2 7.4-6.5 8.3-3.3-.9-6.5-3.7-6.5-8.3V6Z"/>',
  gear: '<circle cx="12" cy="12" r="2.8"/><path d="M12 3.8v2M12 18.2v2M5 6.6l1.4 1.4M17.6 16l1.4 1.4M3.8 12h2M18.2 12h2M5 17.4l1.4-1.4M17.6 8l1.4-1.4"/>',
  wrench: '<path d="M14.9 6.4a3.9 3.9 0 0 0-5.3 4.9l-5.6 5.6 2.1 2.1 5.6-5.6a3.9 3.9 0 0 0 4.9-5.3l-2.5 2.5-2-2Z"/>',
  install: '<rect x="7.5" y="3" width="9" height="18" rx="2"/><path d="M11.2 18h1.6"/><path d="M12 7.5v6M9.3 11l2.7 2.7L14.7 11"/>',
  compass: '<circle cx="12" cy="12" r="8.5"/><path d="M15.2 8.8 13.4 14 8.8 15.2 10.6 10Z"/>',
  navigate: '<path d="M4 20 12 4l8 16-8-4Z"/>',
  scan: '<path d="M4 8V5.5A1.5 1.5 0 0 1 5.5 4H8"/><path d="M16 4h2.5A1.5 1.5 0 0 1 20 5.5V8"/><path d="M20 16v2.5a1.5 1.5 0 0 1-1.5 1.5H16"/><path d="M8 20H5.5A1.5 1.5 0 0 1 4 18.5V16"/><path d="M4 12h16" stroke-dasharray="1.6 2"/>',
  camera: '<path d="M4 8.3a1.8 1.8 0 0 1 1.8-1.8h1.6L8.6 4.8h6.8l1.2 1.7h1.6A1.8 1.8 0 0 1 20 8.3v8.4a1.8 1.8 0 0 1-1.8 1.8H5.8A1.8 1.8 0 0 1 4 16.7Z"/><circle cx="12" cy="12.3" r="3.3"/>',

  // ---- status / movement ----
  'dot-ok': '<circle cx="12" cy="12" r="7" fill="var(--ok)" stroke="none"/>',
  'dot-warn': '<circle cx="12" cy="12" r="7" fill="var(--warn)" stroke="none"/>',
  'dot-bad': '<circle cx="12" cy="12" r="7" fill="var(--bad)" stroke="none"/>',
  'dot-info': '<circle cx="12" cy="12" r="7" fill="var(--accent)" stroke="none"/>',
  'dot-neutral': '<circle cx="12" cy="12" r="7" fill="var(--muted)" stroke="none"/>',
  star: '<path fill="currentColor" stroke="none" d="M12 3.2 14.6 9l6.4.6-4.8 4.3 1.4 6.3L12 16.9 6.4 20.2l1.4-6.3-4.8-4.3L9 9Z"/>',
  sparkle: '<path fill="currentColor" stroke="none" d="M12 3 13.3 9.7 20 11 13.3 12.3 12 19 10.7 12.3 4 11 10.7 9.7Z"/>',
  clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.2v5l3.6 2"/>',
  hourglass: '<path d="M6.8 4h10.4M6.8 20h10.4"/><path d="M7.8 4c0 4.1 2 5.6 4.2 6.5-2.2 1-4.2 2.4-4.2 6.5M16.2 4c0 4.1-2 5.6-4.2 6.5 2.2 1 4.2 2.4 4.2 6.5"/>',
  contrast: '<circle cx="12" cy="12" r="8.5"/><path fill="currentColor" stroke="none" d="M12 3.5a8.5 8.5 0 0 1 0 17Z"/>',

  // ---- category / product fallback art ----
  grain: '<path d="M12 3.5c-1.4 1.4-2.2 2.5-2.2 3.4 0 .4.1.7.4 1C7.6 9.3 5.8 12.3 5.8 15.3c0 3 2.7 5.2 6.2 5.2s6.2-2.2 6.2-5.2c0-3-1.8-6-4.4-7.4.3-.3.4-.6.4-1 0-.9-.8-2-2.2-3.4Z"/><path d="M9.3 8.4c.8.5 1.7.7 2.7.7s1.9-.2 2.7-.7"/>',
  pulse: '<path d="M12 20.5V9"/><path d="M12 9c-.3-1.7-1.3-2.7-3-3 .3 1.9 1.3 2.9 3 3ZM12 9c.3-1.7 1.3-2.7 3-3-.3 1.9-1.3 2.9-3 3Z" fill="currentColor" stroke="none"/><path d="M12 12.2c-.3-1.7-1.3-2.7-3-3 .3 1.9 1.3 2.9 3 3ZM12 12.2c.3-1.7 1.3-2.7 3-3-.3 1.9-1.3 2.9-3 3Z" fill="currentColor" stroke="none"/><path d="M12 15.4c-.3-1.7-1.3-2.7-3-3 .3 1.9 1.3 2.9 3 3ZM12 15.4c.3-1.7 1.3-2.7 3-3-.3 1.9-1.3 2.9-3 3Z" fill="currentColor" stroke="none"/>',
  nut: '<path d="M12 3.8c-3.6 1.6-5.8 5.4-5.8 9 0 4 2.6 7.2 5.8 7.2s5.8-3.2 5.8-7.2c0-3.6-2.2-7.4-5.8-9Z"/><path d="M12 6.5c-1.6 2-2.4 4-2.4 6"/>',
  jar: '<path d="M9.2 3.3h5.6v2.2H9.2Z"/><path d="M8.6 4.7h6.8"/><path d="M7.5 6.6h9l1 2.8v9.7a1.9 1.9 0 0 1-1.9 1.9H8.4a1.9 1.9 0 0 1-1.9-1.9V9.4Z"/><path d="M12 11.6c1 1.3 1.5 2.2 1.5 3a1.5 1.5 0 0 1-3 0c0-.8.5-1.7 1.5-3Z" fill="currentColor" stroke="none"/>',
  milk: '<path d="M9.3 3.4h5.4v2h1a1 1 0 0 1 1 1v2l1.1 1.9v10.5a1.7 1.7 0 0 1-1.7 1.7H9.9a1.7 1.7 0 0 1-1.7-1.7V10.2l1.1-1.9v-2a1 1 0 0 1 1-1h1Z"/><path d="M8.6 13.6c.8-.6 1.6-.6 2.4 0s1.6.6 2.4 0 1.6-.6 2.4 0"/>',
  chili: '<path d="M5 13h14l-1.3 3.4a3 3 0 0 1-2.8 2H9.1a3 3 0 0 1-2.8-2Z"/><path d="M14.3 12.2 17.8 5"/><circle cx="18.1" cy="4.4" r="1.3" fill="currentColor" stroke="none"/><circle cx="9.6" cy="11.7" r=".7" fill="currentColor" stroke="none"/><circle cx="12" cy="11.2" r=".7" fill="currentColor" stroke="none"/>',
  coffee: '<path d="M5.3 9h11v5.6a4 4 0 0 1-4 4H9.3a4 4 0 0 1-4-4Z"/><path d="M16.3 10.4h1.6a2 2 0 0 1 0 4h-1.6"/><path d="M8.4 4.4c0 .9-.9.9-.9 1.9s.9 1 .9 1.9M12.4 4.4c0 .9-.9.9-.9 1.9s.9 1 .9 1.9"/>',
  honey: '<path d="M9.2 3.3h5.6v2.2H9.2Z"/><path d="M8.6 4.7h6.8"/><path d="M7.5 6.6h9l1 2.8v9.7a1.9 1.9 0 0 1-1.9 1.9H8.4a1.9 1.9 0 0 1-1.9-1.9V9.4Z"/><path d="M14.6 4.3 18 1.8"/><circle cx="18.3" cy="1.6" r="1" fill="currentColor" stroke="none"/>',
  gift: '<rect x="4.5" y="10.5" width="15" height="8.5" rx="1"/><path d="M4.5 10.5h15v3.2h-15Z" fill="currentColor" stroke="none"/><path d="M12 10.5v8.5" stroke-width="2.3"/><path d="M12 10.2c-1.7-3.7-5.3-4.5-5.3-1.7 0 1.3 1.7 1.7 5.3 1.7ZM12 10.2c1.7-3.7 5.3-4.5 5.3-1.7 0 1.3-1.7 1.7-5.3 1.7Z" fill="currentColor" stroke="none"/>',
  bottle: '<rect x="8.3" y="10.5" width="7.4" height="10" rx="1.3"/><path d="M10.3 10.5V7.8a1 1 0 0 1 1-1h1.4a1 1 0 0 1 1 1v2.7"/><path d="M13.7 7.3 16.8 5.6a1.1 1.1 0 0 1 1.5.4 1.1 1.1 0 0 1-.4 1.5l-2.9 1.6"/><path d="M6.3 9.2l1 1M18.3 6.4l-1.3.3" opacity=".6"/>',
  'baby-bottle': '<rect x="8.8" y="9" width="6.4" height="10.5" rx="2"/><path d="M9.9 9V6.2a2.1 2.1 0 0 1 4.2 0V9"/><path d="M8.9 12h6.2M8.9 14.6h6.2M8.9 17.2h6.2"/>',
  leaf: '<path d="M6.5 19c-1.8-5.6.8-11.8 10-13.6-.8 7.8-5 11.6-10 13.6Z"/><path d="M6.5 19c.8-3.6 2.6-6.2 5.3-8"/><path d="M4.3 17.5c-1-3-.2-6 2.6-7.6-.1 3.6-1 5.9-2.6 7.6Z" fill="currentColor" stroke="none"/>',
  tag: '<path d="M10.8 4h6.7a1.5 1.5 0 0 1 1.5 1.5v6.7a1.5 1.5 0 0 1-.4 1L11 20.8l-7.8-7.8L10.8 4.4Z"/><circle cx="15" cy="8.5" r="1.3" fill="currentColor" stroke="none"/>',
  cart: '<circle cx="9.6" cy="19.5" r="1.4"/><circle cx="17" cy="19.5" r="1.4"/><path d="M3.5 4.5h2.3l2 11.2h10.9l1.8-8H7.2"/>',
  mall: '<path d="M4.5 9.6 5.3 5h13.4l.8 4.6"/><path d="M5.5 9.6v9a1 1 0 0 0 1 1h3v-5.4h5V19.6h3a1 1 0 0 0 1-1v-9"/>',
  bag: '<path d="M4.5 9.4h15l-1 9.2a1.6 1.6 0 0 1-1.6 1.5H7.1a1.6 1.6 0 0 1-1.6-1.5Z"/><path d="M5.7 13.2h12.6"/><path d="M9.3 9.4V7.4a2.7 2.7 0 0 1 5.4 0v2"/>',
  store: '<path d="M4.3 10.2 5.2 5h13.6l.9 5.2"/><path d="M5.3 10.2v8.6a1 1 0 0 0 1 1h2.9v-4.9h5.6v4.9h2.9a1 1 0 0 0 1-1v-8.6"/>',
  box: '<path d="M4 8.2 12 4l8 4.2v7.6L12 20l-8-4.2Z"/><path d="M4 8.2 12 12l8-4"/><path d="M12 12v8"/>',
  'chart-line': '<path d="M4.3 15.8 9 10.2l3.6 2.7L20 5.4"/><path d="M4 20h16"/>',
  'chart-bar': '<path d="M5.5 20V10.4M11.7 20V4.4M18 20v-7.6"/><path d="M3.5 20h17"/>',
  crown: '<path d="M4.5 16.7 3.4 8.9l5 3.9 3.6-6.3 3.6 6.3 5-3.9-1.1 7.8Z"/><path d="M4.5 16.7h15v2h-15Z"/>',
  'search-x': '<circle cx="10" cy="10.5" r="6"/><path d="M19 19 15 15"/><path d="M7.7 8.2l4.6 4.6M12.3 8.2l-4.6 4.6"/>',
};

/**
 * name -> inline <svg>, ready to drop straight into a template string.
 * Sizing follows `.icon`'s width/height:1em rule (app.css), so it slots into
 * every place that used to size the emoji with font-size -- .tabbar .ic,
 * .thumb-default span, .cat-thumb-ic and so on -- with no changes there.
 */
export function svgIcon(name, { className = '' } = {}) {
  const body = ICONS[name];
  if (!body) return '';
  return `<svg class="icon${className ? ` ${className}` : ''}" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${body}</svg>`;
}
